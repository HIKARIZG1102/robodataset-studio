from __future__ import annotations

import subprocess
import time
import base64
from typing import Any
from uuid import uuid4

from robodataset_studio_v3.ros.image_conversion import image_bytes_to_rgb
from robodataset_studio_v3.services.task_service import task_service


class RosService:
    def graph(self) -> dict[str, Any]:
        topics_result = self._run_ros(["ros2", "topic", "list", "-t"], timeout=8)
        nodes_result = self._run_ros(["ros2", "node", "list"], timeout=8)
        services_result = self._run_ros(["ros2", "service", "list", "-t"], timeout=8)
        available = bool(topics_result.get("ok") or nodes_result.get("ok") or services_result.get("ok"))
        return {
            "available": available,
            "topics": self._parse_name_type_lines(str(topics_result.get("stdout") or "")),
            "nodes": self._parse_name_lines(str(nodes_result.get("stdout") or "")),
            "services": self._parse_name_type_lines(str(services_result.get("stdout") or "")),
            "errors": {
                "topics": "" if topics_result.get("ok") else str(topics_result.get("stderr") or ""),
                "nodes": "" if nodes_result.get("ok") else str(nodes_result.get("stderr") or ""),
                "services": "" if services_result.get("ok") else str(services_result.get("stderr") or ""),
            },
        }

    def topic_info(self, topic: str) -> dict[str, Any]:
        return self._run_ros(["ros2", "topic", "info", topic], timeout=8)

    def echo_once(self, topic: str) -> dict[str, Any]:
        return self._run_ros(["ros2", "topic", "echo", "--once", topic], timeout=8)

    def topic_hz(self, topic: str) -> dict[str, Any]:
        return self._run_ros(["ros2", "topic", "hz", topic, "--window", "10"], timeout=8)

    def node_info(self, node: str) -> dict[str, Any]:
        return self._run_ros(["ros2", "node", "info", node], timeout=8)

    def node_params(self, node: str, *, max_params: int = 40) -> dict[str, Any]:
        names = self._run_ros(["ros2", "param", "list", node], timeout=8)
        if not names.get("ok"):
            return {"ok": False, "params": [], "stdout": "", "stderr": names.get("stderr", ""), "returncode": names.get("returncode", 1)}
        params = []
        for line in str(names.get("stdout") or "").splitlines():
            param = line.strip()
            if not param or param.startswith("/"):
                continue
            params.append(param)
            if len(params) >= max_params:
                break
        samples = []
        for param in params:
            value = self._run_ros(["ros2", "param", "get", node, param], timeout=3)
            samples.append({"name": param, "value": value.get("stdout", ""), "ok": value.get("ok", False)})
        return {"ok": True, "params": samples, "stderr": "", "returncode": 0}

    def check_topic_task(self, topic: str) -> dict[str, Any]:
        result = {
            "info": self.topic_info(topic),
            "echo_once": self.echo_once(topic),
            "hz": self.topic_hz(topic),
        }
        task = task_service.run_instant("ros_check", f"checked ROS topic {topic}", result)
        return {"task_id": task.task_id, "result": result}

    def node_details(self, node: str) -> dict[str, Any]:
        return {
            "node": node,
            "info": self.node_info(node),
            "params": self.node_params(node),
        }

    def image_snapshot(self, topic: str, *, timeout: float = 5.0) -> dict[str, Any]:
        try:
            import rclpy
            from rclpy.executors import SingleThreadedExecutor
            from rclpy.qos import qos_profile_sensor_data
            from sensor_msgs.msg import Image
        except Exception as exc:
            return {"ok": False, "error": f"ROS image preview requires rclpy and sensor_msgs: {exc}"}

        captured: dict[str, Any] = {}
        context = rclpy.Context()
        node = None
        executor = None
        try:
            rclpy.init(context=context)
            node = rclpy.create_node(f"robodataset_v3_image_snapshot_{uuid4().hex[:8]}", context=context)
            executor = SingleThreadedExecutor(context=context)
            executor.add_node(node)

            def on_image(msg: Image) -> None:
                captured["data"] = bytes(msg.data)
                captured["meta"] = {
                    "height": int(msg.height),
                    "width": int(msg.width),
                    "encoding": str(msg.encoding),
                    "is_bigendian": int(msg.is_bigendian),
                    "step": int(msg.step),
                }

            node.create_subscription(Image, topic, on_image, qos_profile_sensor_data)
            deadline = time.time() + timeout
            while time.time() < deadline and "data" not in captured:
                executor.spin_once(timeout_sec=0.1)
            if "data" not in captured:
                return {"ok": False, "error": f"no image received from {topic} before timeout"}
            meta = captured["meta"]
            frame = image_bytes_to_rgb(captured["data"], meta)
            if frame is None:
                return {"ok": False, "error": f"unsupported image encoding: {meta.get('encoding')}", "meta": meta}
            height, width = int(frame.shape[0]), int(frame.shape[1])
            ppm = f"P6\n{width} {height}\n255\n".encode("ascii") + frame.tobytes()
            meta["rgb_width"] = width
            meta["rgb_height"] = height
            meta["mean_brightness"] = float(frame.mean())
            return {"ok": True, "topic": topic, "meta": meta, "image_ppm_base64": base64.b64encode(ppm).decode("ascii")}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
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
                rclpy.shutdown(context=context)
            except Exception:
                pass

    def _run_ros(self, command: list[str], timeout: int) -> dict[str, Any]:
        try:
            completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError:
            return {"ok": False, "stdout": "", "stderr": "ros2 command not found", "returncode": 127}
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            return {"ok": bool(stdout.strip()), "stdout": stdout.strip(), "stderr": stderr.strip() or "command timed out", "returncode": 124}
        return {
            "ok": completed.returncode == 0,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
            "returncode": completed.returncode,
        }

    def _parse_name_type_lines(self, text: str) -> list[dict[str, str]]:
        items = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if "[" in line and "]" in line:
                name, msg_type = line.rsplit("[", 1)
                item_type = msg_type.rstrip("]").strip()
            else:
                name, item_type = line, ""
            clean_name = name.strip()
            items.append(
                {
                    "name": clean_name,
                    "type": item_type,
                    "topic": clean_name,
                    "message_type": item_type,
                }
            )
        return items

    def _parse_name_lines(self, text: str) -> list[dict[str, str]]:
        return [{"name": line.strip()} for line in text.splitlines() if line.strip()]


ros_service = RosService()
