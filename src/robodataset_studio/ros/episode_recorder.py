from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
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

        recording = config.get("recording", {})
        sample_rate = float(recording.get("sample_rate_hz") or 10)
        duration = float(duration_sec or recording.get("episode_duration_sec") or 2.0)
        steps = max(int(sample_rate * duration), int(recording.get("min_episode_steps") or 1))

        frames = self._capture_image_streams(image_streams, steps, sample_rate)
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
            "warnings": warnings,
        }
        episodes_dir.mkdir(parents=True, exist_ok=True)
        path = episodes_dir / f"episode_{episode_index:07d}.npz"
        np.savez_compressed(path, **arrays, episode_metadata=np.array(json.dumps(metadata, ensure_ascii=False)))
        return RosEpisodeResult(path=path, steps=actual_steps, streams=list(arrays), warnings=warnings)

    def _capture_image_streams(
        self,
        image_streams: list[dict],
        steps: int,
        sample_rate: float,
    ) -> dict[str, list[np.ndarray]]:
        import rclpy
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import Image

        context = rclpy.Context()
        rclpy.init(context=context)
        node = rclpy.create_node(f"robodataset_episode_recorder_{uuid4().hex[:8]}", context=context)
        executor = SingleThreadedExecutor(context=context)
        executor.add_node(node)
        latest: dict[str, tuple[bytes, dict[str, object]]] = {}
        captured: dict[str, list[np.ndarray]] = {str(stream.get("name") or stream.get("topic")): [] for stream in image_streams}

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

        try:
            for stream in image_streams:
                stream_name = str(stream.get("name") or stream.get("topic"))
                topic = str(stream.get("topic") or "")
                if topic:
                    node.create_subscription(Image, topic, make_callback(stream_name), qos_profile_sensor_data)

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
                if all(len(values) >= steps for values in captured.values() if values is not None):
                    break
                next_sample_at = now + 1.0 / max(sample_rate, 1.0)
        finally:
            try:
                executor.remove_node(node)
            except Exception:
                pass
            node.destroy_node()
            context.try_shutdown()

        return captured
