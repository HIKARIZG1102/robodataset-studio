from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from uuid import uuid4

import numpy as np

from robodataset_studio.ros.image_conversion import compressed_image_to_rgb, image_bytes_to_rgb


def emit(payload: dict) -> None:
    try:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    except BrokenPipeError:
        raise SystemExit(0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", required=True)
    parser.add_argument("--message-type", default="sensor_msgs/msg/Image")
    parser.add_argument("--max-fps", type=float, default=15.0)
    parser.add_argument("--include-ppm", action="store_true")
    args = parser.parse_args()

    try:
        import rclpy
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import CompressedImage
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
        node = rclpy.create_node(f"robodataset_image_preview_{uuid4().hex[:8]}", context=context)
        executor = SingleThreadedExecutor(context=context)
        executor.add_node(node)

        def emit_frame(frame: np.ndarray | None, meta: dict[str, object], now: float) -> None:
            nonlocal published, last_emit
            if frame is None:
                emit({"type": "error", "error": f"unsupported image encoding: {meta.get('encoding') or meta.get('format')}", "meta": meta})
                return
            last_emit = now
            contiguous = np.ascontiguousarray(frame)
            h, w, _ = contiguous.shape
            published += 1
            payload = {
                "type": "frame",
                "meta": {**meta, "rgb_width": int(w), "rgb_height": int(h), "published": int(published)},
                "rgb_base64": base64.b64encode(contiguous.tobytes()).decode("ascii"),
            }
            if args.include_ppm:
                ppm = f"P6\n{w} {h}\n255\n".encode("ascii") + contiguous.tobytes()
                payload["ppm_base64"] = base64.b64encode(ppm).decode("ascii")
            emit(payload)

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
            meta = {
                "message_type": "sensor_msgs/msg/Image",
                "encoding": str(msg.encoding),
                "width": int(msg.width),
                "height": int(msg.height),
                "is_bigendian": int(msg.is_bigendian),
                "step": int(msg.step),
                "received": int(received),
            }
            emit_frame(image_bytes_to_rgb(bytes(msg.data), meta), meta, now)

        def on_compressed_image(msg: CompressedImage) -> None:
            nonlocal received, published, last_emit, last_status
            received += 1
            now = time.time()
            if now - last_status >= 1.0:
                last_status = now
                emit(
                    {
                        "type": "status",
                        "text": f"receiving compressed frames={received} format={msg.format} bytes={len(msg.data)}",
                        "received": received,
                    }
                )
            if now - last_emit < min_period:
                return
            meta = {
                "message_type": "sensor_msgs/msg/CompressedImage",
                "format": str(msg.format),
                "received": int(received),
                "compressed_size": len(msg.data),
            }
            emit_frame(compressed_image_to_rgb(bytes(msg.data), meta), meta, now)

        if args.message_type == "sensor_msgs/msg/CompressedImage":
            node.create_subscription(CompressedImage, args.topic, on_compressed_image, qos_profile_sensor_data)
        else:
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
