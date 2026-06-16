from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from uuid import uuid4

import numpy as np

from robodataset_studio_v3.ros.image_conversion import image_bytes_to_rgb


def emit(payload: dict) -> None:
    try:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    except BrokenPipeError:
        raise SystemExit(0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", required=True)
    parser.add_argument("--max-fps", type=float, default=15.0)
    args = parser.parse_args()

    try:
        import rclpy
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import Image
    except Exception as exc:
        emit({"type": "error", "error": f"cannot import ROS image dependencies: {exc}"})
        return

    context = rclpy.Context()
    node = None
    executor = None
    received = 0
    published = 0
    last_emit = 0.0
    min_period = 1.0 / max(args.max_fps, 1.0)
    last_status = 0.0
    try:
        rclpy.init(context=context)
        node = rclpy.create_node(f"robodataset_v3_image_preview_{uuid4().hex[:8]}", context=context)
        executor = SingleThreadedExecutor(context=context)
        executor.add_node(node)

        def on_image(msg: Image) -> None:
            nonlocal received, published, last_emit, last_status
            received += 1
            now = time.time()
            if now - last_status >= 1.0:
                last_status = now
                emit(
                    {
                        "type": "status",
                        "text": f"receiving frames={received} encoding={msg.encoding} size={msg.width}x{msg.height}",
                        "received": received,
                    }
                )
            if now - last_emit < min_period:
                return
            last_emit = now
            meta = {
                "encoding": str(msg.encoding),
                "width": int(msg.width),
                "height": int(msg.height),
                "step": int(msg.step),
                "received": int(received),
            }
            frame = image_bytes_to_rgb(bytes(msg.data), meta)
            if frame is None:
                emit({"type": "error", "error": f"unsupported image encoding: {msg.encoding}", "meta": meta})
                return
            contiguous = np.ascontiguousarray(frame)
            h, w, _ = contiguous.shape
            ppm = f"P6\n{w} {h}\n255\n".encode("ascii") + contiguous.tobytes()
            published += 1
            emit(
                {
                    "type": "frame",
                    "meta": {**meta, "rgb_width": int(w), "rgb_height": int(h), "published": int(published)},
                    "ppm_base64": base64.b64encode(ppm).decode("ascii"),
                }
            )

        node.create_subscription(Image, args.topic, on_image, qos_profile_sensor_data)
        emit({"type": "status", "text": f"subscribed: {args.topic}", "received": 0})
        while context.ok():
            executor.spin_once(timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        emit({"type": "error", "error": str(exc)})
    finally:
        if executor is not None and node is not None:
            try:
                executor.remove_node(node)
            except Exception:
                pass
        if node is not None:
            try:
                node.destroy_node()
            except Exception:
                pass
        try:
            context.try_shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()
