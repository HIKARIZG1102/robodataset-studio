from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence
from threading import Event
from uuid import uuid4

import numpy as np

from robodataset_studio_v3.core.runtime_env import apply_ros_environment, select_rmw
from robodataset_studio_v3.ros.image_conversion import compressed_image_to_rgb, image_bytes_to_array, is_image_message_type
from robodataset_studio_v3.ros.message_conversion import (
    is_supported_generic_message_type,
    ros_message_to_array,
    unsupported_message_type_warning,
)


@dataclass
class RosEpisodeResult:
    path: Path
    steps: int
    streams: list[str]
    warnings: list[str]


class RosEpisodeRecorder:
    def record_episode(
        self,
        config: dict,
        episodes_dir: Path,
        episode_index: int,
        *,
        duration_sec: float | None = None,
        target_samples: int | None = None,
        cancel_event: Event | None = None,
    ) -> RosEpisodeResult:
        self._sync_core_schema(config)
        image_streams = [
            stream
            for stream in config.get("streams", [])
            if stream.get("source") == "ros2_topic" and is_image_message_type(str(stream.get("message_type") or ""))
        ]
        generic_streams = [
            stream
            for stream in config.get("streams", [])
            if stream.get("source") == "ros2_topic"
            and not is_image_message_type(str(stream.get("message_type") or ""))
            and str(stream.get("message_type") or "") != "sensor_msgs/msg/JointState"
        ]
        unsupported_streams = [
            stream
            for stream in generic_streams
            if not is_supported_generic_message_type(str(stream.get("message_type") or ""))
        ]
        if unsupported_streams:
            details = [
                unsupported_message_type_warning(str(stream.get("topic") or stream.get("name") or ""), str(stream.get("message_type") or ""))
                for stream in unsupported_streams
            ]
            raise RuntimeError("; ".join(details))
        joint_streams = [
            key
            for key in config.get("state", {}).get("keys", [])
            if key.get("type") == "sensor_msgs/msg/JointState" and key.get("source_topic")
        ]
        if not image_streams and not generic_streams and not joint_streams:
            raise RuntimeError("collection_config.yaml has no supported ROS streams")

        recording = config.get("recording", {})
        sample_rate = float(recording.get("sample_rate_hz") or 10)
        min_steps = int(recording.get("min_episode_steps") or 1)
        configured_stop_mode = str(recording.get("stop_mode") or "duration_sec")
        if target_samples is None and configured_stop_mode == "sample_count":
            configured_samples = recording.get("target_samples")
            target_samples = int(configured_samples) if configured_samples else None
        if target_samples is not None:
            steps = max(int(target_samples), min_steps)
        elif configured_stop_mode == "manual" and duration_sec is None:
            steps = None
        else:
            duration = float(duration_sec if duration_sec is not None else recording.get("episode_duration_sec") or 2.0)
            steps = max(int(round(sample_rate * duration)), min_steps)

        frames, states, diagnostics = self._capture_streams(
            image_streams,
            joint_streams,
            generic_streams,
            steps,
            sample_rate,
            min_steps=min_steps,
            cancel_event=cancel_event,
        )
        warnings: list[str] = list(diagnostics.get("warnings", []))
        arrays: dict[str, np.ndarray] = {}
        for stream in image_streams:
            name = str(stream.get("name") or stream.get("topic") or "image").strip("/")
            output_key = self._stream_output_key(stream)
            stream_frames = frames.get(name, [])
            if not stream_frames:
                warnings.append(f"no frames captured for {name}")
                continue
            arrays[output_key] = np.stack(stream_frames, axis=0)
        for stream in generic_streams:
            name = str(stream.get("name") or stream.get("topic") or "stream").strip("/")
            output_key = self._stream_output_key(stream)
            values = frames.get(name, [])
            if not values:
                warnings.append(f"no messages captured for {name} [{stream.get('message_type', '')}]")
                continue
            try:
                arrays[output_key] = np.stack(values, axis=0)
            except ValueError as exc:
                raise RuntimeError(f"inconsistent sample shape for {name} [{stream.get('message_type', '')}]: {exc}") from exc

        captured_state_names: list[str] = []
        for stream in joint_streams:
            name = str(stream.get("name") or "robot_obs")
            values = states.get(name, [])
            if values:
                arrays[name] = np.stack(values, axis=0).astype(np.float32)
                captured_state_names.append(name)
            else:
                warnings.append(f"no JointState messages captured for {stream.get('source_topic')}")

        if not arrays:
            raise RuntimeError("no samples were captured from configured ROS2 streams; " + "; ".join(warnings))

        actual_steps = min(array.shape[0] for array in arrays.values())
        for name, array in list(arrays.items()):
            arrays[name] = array[:actual_steps]

        dataset_cfg = config.get("dataset", {})
        requires_actions = bool(dataset_cfg.get("requires_actions", True))
        primary_state_name = self._action_source_state_name(config, joint_streams, captured_state_names)
        if requires_actions and not primary_state_name:
            state_dim = int(config.get("action", {}).get("dim") or 0)
            arrays["robot_obs"] = np.zeros((actual_steps, max(state_dim, 1)), dtype=np.float32)
            primary_state_name = "robot_obs"
            warnings.append("no JointState state stream captured; placeholder robot_obs/actions were generated")
        if requires_actions and primary_state_name in arrays:
            actions = self._derive_actions(config, arrays[primary_state_name], actual_steps)
            arrays["rel_actions"] = actions
            arrays["actions"] = actions.copy()

        metadata = self._metadata_payload(config, actual_steps, image_streams, joint_streams, generic_streams, warnings)
        metadata["steps"] = actual_steps
        metadata["captured_streams"] = list(arrays)
        metadata["state_topics"] = [stream.get("source_topic", "") for stream in joint_streams]
        metadata["warnings"] = warnings
        metadata["diagnostics"] = self._json_clean(diagnostics)
        metadata["source"] = "ros2_listener"
        metadata["mock"] = False
        metadata["runtime"] = config.get("runtime", {})
        legacy_metadata = {
            "mock": False,
            "steps": actual_steps,
            "source": "ros2_listener",
            "streams": [stream.get("name", "") for stream in image_streams],
            "state_topics": [stream.get("source_topic", "") for stream in joint_streams],
            "runtime": config.get("runtime", {}),
            "project": config.get("project", {}),
            "environment": config.get("environment", {}),
            "robot": config.get("robot", {}),
            "instruction": config.get("instruction", {}),
            "dataset": config.get("dataset", {}),
            "warnings": warnings,
            "diagnostics": self._json_clean(diagnostics),
        }
        metadata.setdefault("legacy", legacy_metadata)
        episodes_dir.mkdir(parents=True, exist_ok=True)
        transition_count = max(actual_steps - 1, 0) if requires_actions else actual_steps
        if transition_count <= 0:
            raise RuntimeError("at least 1 synchronized sample is required to write dataset files")
        first_path = episodes_dir / f"episode_{episode_index:07d}.npz"
        for offset in range(transition_count):
            transition = {
                name: array[offset]
                for name, array in arrays.items()
                if name not in {"rel_actions", "actions"}
            }
            if requires_actions:
                transition["rel_actions"] = arrays["rel_actions"][offset]
                transition["actions"] = arrays["actions"][offset]
            transition.update(self._metadata_npz_fields(metadata, offset))
            path = episodes_dir / f"episode_{episode_index + offset:07d}.npz"
            self._write_npz_atomic(path, transition)
        self._write_session_metadata(config, episodes_dir, metadata, episode_index, episode_index + transition_count - 1)
        self._write_language_annotations(config, episodes_dir, episode_index, episode_index + transition_count - 1)
        return RosEpisodeResult(path=first_path, steps=transition_count, streams=list(arrays), warnings=warnings)

    def _sync_core_schema(self, config: dict) -> None:
        for stream in config.get("streams", []):
            if not isinstance(stream, dict):
                continue
            if not stream.get("name"):
                stream["name"] = stream.get("calvin_key") or str(stream.get("topic", "image")).strip("/").replace("/", "_")
            modality = str(stream.get("modality") or "").lower()
            message_type = str(stream.get("message_type") or "")
            if not stream.get("calvin_key") and is_image_message_type(message_type) and modality not in {"depth", "generic"}:
                stream["calvin_key"] = stream.get("name")
            stream.setdefault("source", "ros2_topic")

    def _action_source_state_name(self, config: dict, joint_streams: list[dict], captured_state_names: list[str]) -> str:
        action_cfg = config.get("action", {}) if isinstance(config.get("action"), dict) else {}
        configured_state = str(action_cfg.get("source_state_key") or "").strip()
        if configured_state and configured_state in captured_state_names:
            return configured_state
        source_topic = str(action_cfg.get("source_topic") or "").strip()
        if source_topic:
            for stream in joint_streams:
                name = str(stream.get("name") or "robot_obs")
                if name in captured_state_names and str(stream.get("source_topic") or "").strip() == source_topic:
                    return name
        if "robot_obs" in captured_state_names:
            return "robot_obs"
        return captured_state_names[0] if captured_state_names else ""

    def _stream_output_key(self, stream: dict) -> str:
        calvin_key = stream.get("calvin_key")
        if calvin_key is not None and str(calvin_key).strip():
            return str(calvin_key).strip()
        return str(stream.get("name") or stream.get("topic") or "image").strip("/").replace("/", "_")

    def _metadata_payload(
        self,
        config: dict,
        actual_steps: int,
        image_streams: list[dict],
        joint_streams: list[dict],
        generic_streams: list[dict],
        warnings: list[str],
    ) -> dict:
        project = self._json_clean(config.get("project", {}))
        environment = self._json_clean(config.get("environment", {}))
        robot = self._json_clean(config.get("robot", {}))
        instruction = self._json_clean(config.get("instruction", {}))
        dataset = self._json_clean(config.get("dataset", {}))
        recording = self._json_clean(config.get("recording", {}))
        action = self._json_clean(config.get("action", {}))
        state = self._json_clean(config.get("state", {}))
        streams = self._json_clean(config.get("streams", []))
        cameras = self._json_clean(config.get("cameras", []))
        return {
            "schema": "robodataset_studio.calvin_metadata.v1",
            "project": project,
            "environment": environment,
            "robot": robot,
            "instruction": instruction,
            "dataset": dataset,
            "recording": recording,
            "action": action,
            "state": state,
            "streams": streams,
            "cameras": cameras,
            "selected": {
                "image_topics": [stream.get("topic", "") for stream in image_streams],
                "state_topics": [stream.get("source_topic", "") for stream in joint_streams],
                "generic_topics": [stream.get("topic", "") for stream in generic_streams],
            },
            "stats": {
                "synchronized_samples": int(actual_steps),
                "warnings": list(warnings),
            },
            "collection_config": self._json_clean(config),
        }

    def _metadata_npz_fields(self, metadata: dict, transition_index: int) -> dict[str, np.ndarray]:
        payload = {**metadata, "transition_index": int(transition_index)}
        task_info = {
            "project": metadata.get("project", {}),
            "instruction": metadata.get("instruction", {}),
        }
        stream_schema = {
            "streams": metadata.get("streams", []),
            "cameras": metadata.get("cameras", []),
            "state": metadata.get("state", {}),
            "action": metadata.get("action", {}),
        }
        return {
            "episode_metadata": self._json_array(payload),
            "collection_config": self._json_array(metadata.get("collection_config", {})),
            "task_info": self._json_array(task_info),
            "environment_info": self._json_array(metadata.get("environment", {})),
            "robot_info": self._json_array(metadata.get("robot", {})),
            "stream_schema": self._json_array(stream_schema),
        }

    def _write_session_metadata(
        self,
        config: dict,
        episodes_dir: Path,
        metadata: dict,
        start_idx: int,
        end_idx: int,
    ) -> None:
        session_root = episodes_dir.parent
        payload = {
            **metadata,
            "episode_range": [int(start_idx), int(end_idx)],
            "split": config.get("dataset", {}).get("split", "training"),
        }
        path = session_root / "session_metadata.json"
        tmp_path = path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            file.flush()
            os.fsync(file.fileno())
        tmp_path.replace(path)

    def _json_array(self, value: object) -> np.ndarray:
        return np.array(json.dumps(self._json_clean(value), ensure_ascii=False))

    def _json_clean(self, value: object) -> object:
        if isinstance(value, dict):
            cleaned: dict[str, object] = {}
            for key, item in value.items():
                if callable(item):
                    continue
                cleaned[str(key)] = self._json_clean(item)
            return cleaned
        if isinstance(value, (list, tuple)):
            return [self._json_clean(item) for item in value]
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    def _derive_actions(self, config: dict, robot_obs: np.ndarray, actual_steps: int) -> np.ndarray:
        action_cfg = config.get("action", {})
        configured_dim = int(action_cfg.get("dim") or 0)
        include_default_gripper = bool(action_cfg.get("include_default_gripper", configured_dim == 7))
        inferred_dim = robot_obs.shape[1] if robot_obs.ndim == 2 else 0
        action_dim = configured_dim or (inferred_dim + 1 if include_default_gripper else inferred_dim)
        default_gripper = float(action_cfg.get("default_gripper", 1.0))
        actions = np.zeros((actual_steps, action_dim), dtype=np.float32)
        if actual_steps <= 1:
            return actions
        delta_dim = max(action_dim - 1, 0) if include_default_gripper else action_dim
        obs_dim = min(delta_dim, robot_obs.shape[1] if robot_obs.ndim == 2 else 0)
        if obs_dim:
            actions[:-1, :obs_dim] = robot_obs[1:, :obs_dim] - robot_obs[:-1, :obs_dim]
        if include_default_gripper and action_dim:
            actions[:, -1] = default_gripper
        return actions

    def _write_npz_atomic(self, path: Path, arrays: dict[str, np.ndarray]) -> None:
        tmp_path = path.with_suffix(".npz.tmp")
        with tmp_path.open("wb") as file:
            np.savez_compressed(file, **arrays)
            file.flush()
            os.fsync(file.fileno())
        tmp_path.replace(path)

    def _write_language_annotations(self, config: dict, episodes_dir: Path, start_idx: int, end_idx: int) -> None:
        dataset = config.get("dataset", {})
        if dataset.get("write_language_annotations", True) is False:
            return
        instruction = str(config.get("instruction", {}).get("text", "")).strip()
        task = self._slugify_task_name(instruction or str(config.get("project", {}).get("name", "")))
        ann_rel = Path(str(dataset.get("language_annotation_file") or "lang_annotations/auto_lang_ann.npy"))
        ann_path = episodes_dir / ann_rel
        annotations = self._load_annotations(ann_path)
        annotations["info"]["indx"].append([start_idx, end_idx])
        annotations["language"]["ann"].append(instruction)
        annotations["language"]["task"].append(task)
        ann_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = ann_path.with_suffix(".npy.tmp")
        with tmp_path.open("wb") as file:
            np.save(file, annotations, allow_pickle=True)
            file.flush()
            os.fsync(file.fileno())
        tmp_path.replace(ann_path)

    def _load_annotations(self, ann_path: Path) -> dict:
        if not ann_path.exists():
            return {"info": {"indx": []}, "language": {"ann": [], "task": []}}
        annotations = np.load(ann_path, allow_pickle=True)
        if isinstance(annotations, np.ndarray) and annotations.shape == ():
            annotations = annotations.item()
        if not isinstance(annotations, dict):
            return {"info": {"indx": []}, "language": {"ann": [], "task": []}}
        annotations.setdefault("info", {})
        annotations.setdefault("language", {})
        annotations["info"].setdefault("indx", [])
        annotations["language"].setdefault("ann", [])
        annotations["language"].setdefault("task", [])
        return annotations

    def _slugify_task_name(self, text: str) -> str:
        task = "".join(ch.lower() if ch.isalnum() else "_" for ch in text).strip("_")
        while "__" in task:
            task = task.replace("__", "_")
        return task or "unnamed_task"

    def _capture_streams(
        self,
        image_streams: list[dict],
        joint_streams: list[dict],
        generic_streams: list[dict],
        steps: int | None,
        sample_rate: float,
        *,
        min_steps: int = 1,
        cancel_event: Event | None = None,
    ) -> tuple[dict[str, list[np.ndarray]], dict[str, list[np.ndarray]], dict[str, object]]:
        if os.environ.get("ROBODATASET_DISABLE_FASTDDS_SHM", "1") == "1":
            profile = Path(__file__).resolve().parents[3] / "config" / "fastdds_no_shm.xml"
            if profile.exists():
                os.environ["RMW_IMPLEMENTATION"] = select_rmw(os.environ.get("ROBODATASET_RMW_IMPLEMENTATION") or os.environ.get("RMW_IMPLEMENTATION"))
                os.environ["ROBODATASET_RMW_IMPLEMENTATION"] = os.environ["RMW_IMPLEMENTATION"]
                os.environ.setdefault("FASTDDS_DEFAULT_PROFILES_FILE", str(profile))
                os.environ.setdefault("FASTRTPS_DEFAULT_PROFILES_FILE", str(profile))
        apply_ros_environment(os.environ)
        import rclpy
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.qos import qos_profile_sensor_data
        from rosidl_runtime_py.utilities import get_message
        from sensor_msgs.msg import CompressedImage
        from sensor_msgs.msg import Image
        from sensor_msgs.msg import JointState

        context = rclpy.Context()
        rclpy.init(context=context)
        node = rclpy.create_node(f"robodataset_episode_recorder_{uuid4().hex[:8]}", context=context)
        executor = SingleThreadedExecutor(context=context)
        executor.add_node(node)
        latest: dict[str, tuple[bytes, dict[str, object]]] = {}
        captured: dict[str, list[np.ndarray]] = {str(stream.get("name") or stream.get("topic")): [] for stream in image_streams}
        latest_generic: dict[str, object] = {}
        captured_generic: dict[str, list[np.ndarray]] = {str(stream.get("name") or stream.get("topic")): [] for stream in generic_streams}
        latest_states: dict[str, np.ndarray] = {}
        captured_states: dict[str, list[np.ndarray]] = {str(stream.get("name") or "robot_obs"): [] for stream in joint_streams}
        diagnostics: dict[str, object] = {"warnings": [], "decode_errors": {}, "subscribed": []}

        def warn_once(text: str) -> None:
            warnings_list = diagnostics.setdefault("warnings", [])
            if isinstance(warnings_list, list) and text not in warnings_list:
                warnings_list.append(text)

        def add_decode_error(stream_name: str, text: str) -> None:
            errors = diagnostics.setdefault("decode_errors", {})
            if isinstance(errors, dict):
                values = errors.setdefault(stream_name, [])
                if isinstance(values, list) and text not in values:
                    values.append(text)

        def make_callback(stream_name: str):
            def on_image(msg: Image) -> None:
                latest[stream_name] = (
                    bytes(msg.data),
                    {
                        "encoding": msg.encoding,
                        "width": int(msg.width),
                        "height": int(msg.height),
                        "step": int(msg.step),
                        "is_bigendian": int(msg.is_bigendian),
                        "message_type": "sensor_msgs/msg/Image",
                    },
                )

            return on_image

        def make_compressed_callback(stream_name: str):
            def on_image(msg: CompressedImage) -> None:
                latest[stream_name] = (
                    bytes(msg.data),
                    {
                        "format": str(msg.format),
                        "compressed_size": len(msg.data),
                        "message_type": "sensor_msgs/msg/CompressedImage",
                    },
                )

            return on_image

        def make_joint_callback(stream_name: str, output_dim: int, fields: list[str], joint_order: list[str]):
            def on_joint_state(msg: JointState) -> None:
                latest_states[stream_name] = joint_state_to_robot_obs(
                    msg.name,
                    msg.position,
                    msg.velocity,
                    msg.effort,
                    output_dim,
                    fields,
                    joint_order,
                )

            return on_joint_state

        def make_generic_callback(stream_name: str):
            def on_message(msg: object) -> None:
                latest_generic[stream_name] = msg

            return on_message

        try:
            for stream in image_streams:
                stream_name = str(stream.get("name") or stream.get("topic"))
                topic = str(stream.get("topic") or "")
                if topic:
                    if stream.get("message_type") == "sensor_msgs/msg/CompressedImage":
                        node.create_subscription(CompressedImage, topic, make_compressed_callback(stream_name), qos_profile_sensor_data)
                    else:
                        node.create_subscription(Image, topic, make_callback(stream_name), qos_profile_sensor_data)
                    diagnostics["subscribed"].append({"stream": stream_name, "topic": topic, "message_type": stream.get("message_type", "")})
            for stream in generic_streams:
                stream_name = str(stream.get("name") or stream.get("topic"))
                topic = str(stream.get("topic") or "")
                message_type = str(stream.get("message_type") or "")
                if not topic:
                    warn_once(f"generic stream {stream_name} has no topic")
                    continue
                try:
                    msg_cls = get_message(message_type)
                except Exception as exc:
                    raise RuntimeError(f"cannot load ROS message class for {topic} [{message_type}]: {exc}") from exc
                node.create_subscription(msg_cls, topic, make_generic_callback(stream_name), qos_profile_sensor_data)
                diagnostics["subscribed"].append({"stream": stream_name, "topic": topic, "message_type": message_type})
            for stream in joint_streams:
                stream_name = str(stream.get("name") or "robot_obs")
                topic = str(stream.get("source_topic") or "")
                output_dim = int(stream.get("output_dim") or 0)
                fields = [str(field) for field in stream.get("fields", ["joint_position"])]
                joint_order = [str(name) for name in stream.get("joint_order", [])]
                if topic:
                    node.create_subscription(
                        JointState,
                        topic,
                        make_joint_callback(stream_name, output_dim, fields, joint_order),
                        qos_profile_sensor_data,
                    )
                    diagnostics["subscribed"].append({"stream": stream_name, "topic": topic, "message_type": "sensor_msgs/msg/JointState"})

            deadline = time.time() + (max(steps / max(sample_rate, 1.0) + 3.0, 5.0) if steps is not None else 24 * 60 * 60)
            next_sample_at = time.time()
            while rclpy.ok(context=context) and time.time() < deadline:
                if cancel_event is not None and cancel_event.is_set():
                    break
                executor.spin_once(timeout_sec=0.02)
                now = time.time()
                if now < next_sample_at:
                    continue
                for stream_name in list(captured):
                    sample = latest.get(stream_name)
                    if sample is None:
                        continue
                    data, meta = sample
                    frame = (
                        compressed_image_to_rgb(data, meta)
                        if meta.get("message_type") == "sensor_msgs/msg/CompressedImage"
                        else image_bytes_to_array(data, meta)
                    )
                    if frame is not None:
                        captured[stream_name].append(frame)
                    else:
                        add_decode_error(
                            stream_name,
                            f"image decode failed for encoding={meta.get('encoding') or meta.get('format')} type={meta.get('message_type')}",
                        )
                for stream in generic_streams:
                    stream_name = str(stream.get("name") or stream.get("topic"))
                    message = latest_generic.get(stream_name)
                    if message is None:
                        continue
                    result = ros_message_to_array(message, str(stream.get("message_type") or ""))
                    if result.array is not None:
                        captured_generic[stream_name].append(result.array)
                    if result.error:
                        add_decode_error(stream_name, result.error)
                    if result.warning:
                        warn_once(result.warning)
                for stream_name in list(captured_states):
                    state = latest_states.get(stream_name)
                    if state is not None:
                        captured_states[stream_name].append(state.copy())
                target = steps if steps is not None else min_steps
                image_ready = all(len(values) >= target for values in captured.values() if values is not None)
                generic_ready = all(len(values) >= target for values in captured_generic.values() if values is not None)
                state_ready = all(len(values) >= target for values in captured_states.values() if values is not None)
                if steps is not None and image_ready and generic_ready and state_ready:
                    break
                next_sample_at = now + 1.0 / max(sample_rate, 1.0)
        finally:
            try:
                executor.remove_node(node)
            except Exception:
                pass
            node.destroy_node()
            context.try_shutdown()

        for stream in generic_streams:
            stream_name = str(stream.get("name") or stream.get("topic"))
            captured[stream_name] = captured_generic.get(stream_name, [])
        for stream_name, errors in (diagnostics.get("decode_errors", {}) if isinstance(diagnostics.get("decode_errors"), dict) else {}).items():
            if errors:
                warn_once(f"{stream_name}: " + "; ".join(str(item) for item in errors[:3]))
        return captured, captured_states, diagnostics


def joint_state_to_robot_obs(
    names: Sequence[str],
    position: Sequence[float],
    velocity: Sequence[float],
    effort: Sequence[float],
    output_dim: int,
    fields: Sequence[str] | None = None,
    joint_order: Sequence[str] | None = None,
) -> np.ndarray:
    fields = fields or ["joint_position"]
    values: list[float] = []
    ordered_names = list(joint_order or [])
    if ordered_names:
        position_map = dict(zip(names, position))
        velocity_map = dict(zip(names, velocity))
        effort_map = dict(zip(names, effort))
        for field in fields:
            if field in {"joint_position", "position"}:
                values.extend(float(position_map.get(name, 0.0)) for name in ordered_names)
            elif field in {"joint_velocity", "velocity"}:
                values.extend(float(velocity_map.get(name, 0.0)) for name in ordered_names)
            elif field == "effort":
                values.extend(float(effort_map.get(name, 0.0)) for name in ordered_names)
    else:
        for field in fields:
            if field in {"joint_position", "position"}:
                values.extend(float(value) for value in position)
            elif field in {"joint_velocity", "velocity"}:
                values.extend(float(value) for value in velocity)
            elif field == "effort":
                values.extend(float(value) for value in effort)
    if output_dim <= 0:
        output_dim = len(values)
    output = np.zeros((output_dim,), dtype=np.float32)
    if values:
        count = min(len(values), output_dim)
        output[:count] = np.asarray(values[:count], dtype=np.float32)
    return output
