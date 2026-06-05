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

        for stream in joint_streams:
            name = str(stream.get("name") or "robot_obs")
            values = states.get(name, [])
            if values:
                arrays[name] = np.stack(values, axis=0).astype(np.float32)
            else:
                warnings.append(f"no JointState messages captured for {stream.get('source_topic')}")

        actual_steps = min(array.shape[0] for array in arrays.values())
        for name, array in list(arrays.items()):
            arrays[name] = array[:actual_steps]

        arrays.setdefault("robot_obs", np.zeros((actual_steps, 32), dtype=np.float32))
        arrays.setdefault("rel_actions", np.zeros((actual_steps, 7), dtype=np.float32))
        arrays.setdefault("actions", np.zeros((actual_steps, 7), dtype=np.float32))

        metadata = {
            "mock": False,
            "steps": actual_steps,
            "source": "ros2_listener",
            "streams": [stream.get("name", "") for stream in image_streams],
            "state_topics": [stream.get("source_topic", "") for stream in joint_streams],
            "warnings": warnings,
        }
        episodes_dir.mkdir(parents=True, exist_ok=True)
        path = episodes_dir / f"episode_{episode_index:07d}.npz"
        np.savez_compressed(path, **arrays, episode_metadata=np.array(json.dumps(metadata, ensure_ascii=False)))
        return RosEpisodeResult(path=path, steps=actual_steps, streams=list(arrays), warnings=warnings)

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

        def make_joint_callback(stream_name: str, output_dim: int):
            def on_joint_state(msg: JointState) -> None:
                latest_states[stream_name] = joint_state_to_robot_obs(
                    msg.position,
                    msg.velocity,
                    msg.effort,
                    output_dim,
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
                output_dim = int(stream.get("output_dim") or 32)
                if topic:
                    node.create_subscription(JointState, topic, make_joint_callback(stream_name, output_dim), qos_profile_sensor_data)

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
    position: Sequence[float],
    velocity: Sequence[float],
    effort: Sequence[float],
    output_dim: int,
) -> np.ndarray:
    values = list(position)
    values.extend(velocity)
    values.extend(effort)
    output = np.zeros((output_dim,), dtype=np.float32)
    if values:
        count = min(len(values), output_dim)
        output[:count] = np.asarray(values[:count], dtype=np.float32)
    return output
