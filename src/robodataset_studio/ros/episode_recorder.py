from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence
from uuid import uuid4

import numpy as np

from robodataset_studio.ros.image_conversion import image_bytes_to_rgb


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
    ) -> RosEpisodeResult:
        image_streams = [
            stream
            for stream in config.get("streams", [])
            if stream.get("source") == "ros2_topic" and stream.get("message_type") == "sensor_msgs/msg/Image"
        ]
        if not image_streams:
            raise RuntimeError("collection_config.yaml has no sensor_msgs/msg/Image streams")
        joint_streams = [
            key
            for key in config.get("state", {}).get("keys", [])
            if key.get("type") == "sensor_msgs/msg/JointState" and key.get("source_topic")
        ]

        recording = config.get("recording", {})
        sample_rate = float(recording.get("sample_rate_hz") or 10)
        duration = float(duration_sec or recording.get("episode_duration_sec") or 2.0)
        steps = max(int(sample_rate * duration), int(recording.get("min_episode_steps") or 1))

        frames, states = self._capture_streams(image_streams, joint_streams, steps, sample_rate)
        warnings: list[str] = []
        arrays: dict[str, np.ndarray] = {}
        for stream in image_streams:
            name = str(stream.get("name") or stream.get("topic") or "image").strip("/")
            stream_frames = frames.get(name, [])
            if not stream_frames:
                warnings.append(f"no frames captured for {name}")
                continue
            arrays[name] = np.stack(stream_frames, axis=0)

        if not arrays:
            raise RuntimeError("no image frames were captured from configured ROS2 streams")

        primary_state_name = "robot_obs"
        for stream in joint_streams:
            name = str(stream.get("name") or "robot_obs")
            values = states.get(name, [])
            if values:
                arrays[name] = np.stack(values, axis=0).astype(np.float32)
                primary_state_name = name
            else:
                warnings.append(f"no JointState messages captured for {stream.get('source_topic')}")

        actual_steps = min(array.shape[0] for array in arrays.values())
        for name, array in list(arrays.items()):
            arrays[name] = array[:actual_steps]

        dataset_cfg = config.get("dataset", {})
        requires_actions = bool(dataset_cfg.get("requires_actions", True))
        if "robot_obs" not in arrays and requires_actions:
            state_dim = int(config.get("action", {}).get("dim") or 0)
            arrays["robot_obs"] = np.zeros((actual_steps, max(state_dim, 1)), dtype=np.float32)
            primary_state_name = "robot_obs"
        if "robot_obs" in arrays and requires_actions:
            actions = self._derive_actions(config, arrays[primary_state_name], actual_steps)
            arrays["rel_actions"] = actions
            arrays["actions"] = actions.copy()

        metadata = {
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
        }
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
            transition["episode_metadata"] = np.array(json.dumps({**metadata, "transition_index": offset}, ensure_ascii=False))
            path = episodes_dir / f"episode_{episode_index + offset:07d}.npz"
            self._write_npz_atomic(path, transition)
        self._write_language_annotations(config, episodes_dir, episode_index, episode_index + transition_count - 1)
        return RosEpisodeResult(path=first_path, steps=transition_count, streams=list(arrays), warnings=warnings)

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
        steps: int,
        sample_rate: float,
    ) -> tuple[dict[str, list[np.ndarray]], dict[str, list[np.ndarray]]]:
        if os.environ.get("ROBODATASET_DISABLE_FASTDDS_SHM", "1") == "1":
            profile = Path(__file__).resolve().parents[3] / "config" / "fastdds_no_shm.xml"
            if profile.exists():
                os.environ.setdefault("RMW_IMPLEMENTATION", os.environ.get("ROBODATASET_RMW_IMPLEMENTATION", "rmw_cyclonedds_cpp"))
                os.environ.setdefault("FASTDDS_DEFAULT_PROFILES_FILE", str(profile))
                os.environ.setdefault("FASTRTPS_DEFAULT_PROFILES_FILE", str(profile))
        import rclpy
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import Image
        from sensor_msgs.msg import JointState

        context = rclpy.Context()
        rclpy.init(context=context)
        node = rclpy.create_node(f"robodataset_episode_recorder_{uuid4().hex[:8]}", context=context)
        executor = SingleThreadedExecutor(context=context)
        executor.add_node(node)
        latest: dict[str, tuple[bytes, dict[str, object]]] = {}
        captured: dict[str, list[np.ndarray]] = {str(stream.get("name") or stream.get("topic")): [] for stream in image_streams}
        latest_states: dict[str, np.ndarray] = {}
        captured_states: dict[str, list[np.ndarray]] = {str(stream.get("name") or "robot_obs"): [] for stream in joint_streams}

        def make_callback(stream_name: str):
            def on_image(msg: Image) -> None:
                latest[stream_name] = (
                    bytes(msg.data),
                    {
                        "encoding": msg.encoding,
                        "width": int(msg.width),
                        "height": int(msg.height),
                        "step": int(msg.step),
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

        try:
            for stream in image_streams:
                stream_name = str(stream.get("name") or stream.get("topic"))
                topic = str(stream.get("topic") or "")
                if topic:
                    node.create_subscription(Image, topic, make_callback(stream_name), qos_profile_sensor_data)
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

            deadline = time.time() + max(steps / max(sample_rate, 1.0) + 3.0, 5.0)
            next_sample_at = time.time()
            while rclpy.ok(context=context) and time.time() < deadline:
                executor.spin_once(timeout_sec=0.02)
                now = time.time()
                if now < next_sample_at:
                    continue
                for stream_name in list(captured):
                    sample = latest.get(stream_name)
                    if sample is None:
                        continue
                    data, meta = sample
                    frame = image_bytes_to_rgb(data, meta)
                    if frame is not None:
                        captured[stream_name].append(frame)
                for stream_name in list(captured_states):
                    state = latest_states.get(stream_name)
                    if state is not None:
                        captured_states[stream_name].append(state.copy())
                image_ready = all(len(values) >= steps for values in captured.values() if values is not None)
                state_ready = all(len(values) >= steps for values in captured_states.values() if values is not None)
                if image_ready and state_ready:
                    break
                next_sample_at = now + 1.0 / max(sample_rate, 1.0)
        finally:
            try:
                executor.remove_node(node)
            except Exception:
                pass
            node.destroy_node()
            context.try_shutdown()

        return captured, captured_states


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
