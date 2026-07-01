from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable, Sequence
from threading import Event
from uuid import uuid4

import numpy as np

from robodataset_studio.core.runtime_env import apply_ros_environment, select_rmw
from robodataset_studio.ros.image_conversion import compressed_image_to_rgb, image_bytes_to_array, is_image_message_type
from robodataset_studio.ros.message_conversion import (
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

        warnings: list[str] = []
        dataset_cfg = config.get("dataset", {})
        requires_actions = bool(dataset_cfg.get("requires_actions", True))
        primary_state_name = self._action_source_state_name(config, joint_streams, [str(stream.get("name") or "robot_obs") for stream in joint_streams])
        if requires_actions and not primary_state_name:
            state_dim = int(config.get("action", {}).get("dim") or 0)
            primary_state_name = "robot_obs"
            warnings.append("no JointState state stream configured; placeholder robot_obs/actions were generated")

        metadata = self._metadata_payload(config, 0, image_streams, joint_streams, generic_streams, warnings)
        metadata["source"] = "ros2_listener"
        metadata["mock"] = False
        metadata["runtime"] = config.get("runtime", {})
        legacy_metadata = {
            "mock": False,
            "steps": 0,
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
            "diagnostics": {},
        }
        metadata.setdefault("legacy", legacy_metadata)

        episodes_dir.mkdir(parents=True, exist_ok=True)
        first_path = episodes_dir / f"episode_{episode_index:07d}.npz"
        written_count = 0
        captured_stream_names: set[str] = set()
        previous_sample: dict[str, np.ndarray] | None = None

        def sample_to_transition(sample: dict[str, np.ndarray], next_sample: dict[str, np.ndarray] | None) -> dict[str, np.ndarray] | None:
            nonlocal written_count
            arrays = dict(sample)
            if requires_actions:
                if primary_state_name not in arrays:
                    state_dim = int(config.get("action", {}).get("dim") or 0)
                    arrays[primary_state_name] = np.zeros((max(state_dim, 1),), dtype=np.float32)
                if next_sample is None:
                    return None
                if primary_state_name not in next_sample:
                    state_dim = int(config.get("action", {}).get("dim") or 0)
                    next_state = np.zeros((max(state_dim, 1),), dtype=np.float32)
                else:
                    next_state = next_sample[primary_state_name]
                pair = np.stack([arrays[primary_state_name], next_state], axis=0).astype(np.float32)
                action = self._derive_actions(config, pair, 2)[0]
                arrays["rel_actions"] = action
                arrays["actions"] = action.copy()
            return arrays

        def write_transition(arrays: dict[str, np.ndarray]) -> None:
            nonlocal written_count
            captured_stream_names.update(arrays)
            arrays = {
                name: value
                for name, value in arrays.items()
                if name not in {"rel_actions", "actions"}
            } | {
                name: value
                for name, value in arrays.items()
                if name in {"rel_actions", "actions"}
            }
            metadata["captured_streams"] = list(captured_stream_names)
            metadata["state_topics"] = [stream.get("source_topic", "") for stream in joint_streams]
            metadata["warnings"] = warnings
            metadata["steps"] = written_count + 1
            metadata["stats"]["synchronized_samples"] = written_count + 1
            legacy = metadata.get("legacy")
            if isinstance(legacy, dict):
                legacy["steps"] = written_count + 1
                legacy["warnings"] = warnings
            transition = dict(arrays)
            transition.update(self._metadata_npz_fields(metadata, written_count))
            path = episodes_dir / f"episode_{episode_index + written_count:07d}.npz"
            self._write_npz_atomic(path, transition)
            written_count += 1

        def on_sample(sample: dict[str, np.ndarray]) -> None:
            nonlocal previous_sample
            if requires_actions:
                if previous_sample is not None:
                    transition = sample_to_transition(previous_sample, sample)
                    if transition is not None:
                        write_transition(transition)
                previous_sample = sample
                return
            write_transition(sample)

        diagnostics = self._capture_streams(
            image_streams,
            joint_streams,
            generic_streams,
            steps,
            sample_rate,
            min_steps=min_steps,
            cancel_event=cancel_event,
            on_sample=on_sample,
        )
        warnings.extend(str(item) for item in diagnostics.get("warnings", []) if str(item) not in warnings)
        if written_count <= 0:
            raise RuntimeError("at least 1 synchronized sample is required to write dataset files; " + "; ".join(warnings))
        metadata["steps"] = written_count
        metadata["captured_streams"] = list(captured_stream_names)
        metadata["state_topics"] = [stream.get("source_topic", "") for stream in joint_streams]
        metadata["warnings"] = warnings
        metadata["diagnostics"] = self._json_clean(diagnostics)
        metadata["stats"]["synchronized_samples"] = written_count
        legacy = metadata.get("legacy")
        if isinstance(legacy, dict):
            legacy["steps"] = written_count
            legacy["warnings"] = warnings
            legacy["diagnostics"] = self._json_clean(diagnostics)
        self._write_session_metadata(config, episodes_dir, metadata, episode_index, episode_index + written_count - 1)
        self._write_language_annotations(config, episodes_dir, episode_index, episode_index + written_count - 1)
        return RosEpisodeResult(path=first_path, steps=written_count, streams=list(captured_stream_names), warnings=warnings)

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
        on_sample: Callable[[dict[str, np.ndarray]], None] | None = None,
    ) -> dict[str, object]:
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
        captured_counts: dict[str, int] = {str(stream.get("name") or stream.get("topic")): 0 for stream in image_streams}
        latest_generic: dict[str, object] = {}
        captured_generic_counts: dict[str, int] = {str(stream.get("name") or stream.get("topic")): 0 for stream in generic_streams}
        latest_states: dict[str, np.ndarray] = {}
        captured_state_counts: dict[str, int] = {str(stream.get("name") or "robot_obs"): 0 for stream in joint_streams}
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
                sample: dict[str, np.ndarray] = {}
                sample_ready = True
                for stream in image_streams:
                    stream_name = str(stream.get("name") or stream.get("topic"))
                    output_key = self._stream_output_key(stream)
                    image_sample = latest.get(stream_name)
                    if image_sample is None:
                        sample_ready = False
                        continue
                    data, meta = image_sample
                    frame = (
                        compressed_image_to_rgb(data, meta)
                        if meta.get("message_type") == "sensor_msgs/msg/CompressedImage"
                        else image_bytes_to_array(data, meta)
                    )
                    if frame is not None:
                        sample[output_key] = frame
                    else:
                        sample_ready = False
                        add_decode_error(
                            stream_name,
                            f"image decode failed for encoding={meta.get('encoding') or meta.get('format')} type={meta.get('message_type')}",
                        )
                for stream in generic_streams:
                    stream_name = str(stream.get("name") or stream.get("topic"))
                    output_key = self._stream_output_key(stream)
                    message = latest_generic.get(stream_name)
                    if message is None:
                        sample_ready = False
                        continue
                    result = ros_message_to_array(message, str(stream.get("message_type") or ""))
                    if result.array is not None:
                        sample[output_key] = result.array
                    else:
                        sample_ready = False
                    if result.error:
                        add_decode_error(stream_name, result.error)
                    if result.warning:
                        warn_once(result.warning)
                for stream_name in list(captured_state_counts):
                    state = latest_states.get(stream_name)
                    if state is not None:
                        sample[stream_name] = state.copy()
                    else:
                        sample_ready = False
                if sample_ready and sample:
                    if on_sample is not None:
                        on_sample(sample)
                    for stream_name in captured_counts:
                        captured_counts[stream_name] += 1
                    for stream_name in captured_generic_counts:
                        captured_generic_counts[stream_name] += 1
                    for stream_name in captured_state_counts:
                        captured_state_counts[stream_name] += 1
                target = steps if steps is not None else min_steps
                image_ready = all(count >= target for count in captured_counts.values())
                generic_ready = all(count >= target for count in captured_generic_counts.values())
                state_ready = all(count >= target for count in captured_state_counts.values())
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

        for stream_name, errors in (diagnostics.get("decode_errors", {}) if isinstance(diagnostics.get("decode_errors"), dict) else {}).items():
            if errors:
                warn_once(f"{stream_name}: " + "; ".join(str(item) for item in errors[:3]))
        for stream_name, count in {
            **captured_counts,
            **captured_generic_counts,
            **captured_state_counts,
        }.items():
            if count <= 0:
                warn_once(f"no samples captured for {stream_name}")
        diagnostics["captured_counts"] = {
            **captured_counts,
            **captured_generic_counts,
            **captured_state_counts,
        }
        return diagnostics


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
