from __future__ import annotations

import subprocess
import sys
import time
import base64
import os
import re
import signal
import shlex
from pathlib import Path
from typing import Any
from uuid import uuid4

from robodataset_studio_v3.ros.image_conversion import compressed_image_to_rgb, image_bytes_to_rgb
from robodataset_studio_v3.core.runtime_env import apply_ros_environment, available_rmw_implementations, default_ros_setup, select_rmw
from robodataset_studio_v3.services.task_service import task_service


class RosService:
    def graph(self) -> dict[str, Any]:
        topics_result = self._sample_ros_graph(
            ["ros2", "topic", "list", "--no-daemon", "-t"],
            ["ros2", "topic", "list", "-t"],
            parser=self._parse_name_type_lines,
            timeout=4,
            samples=3,
        )
        nodes_result = self._sample_ros_graph(
            ["ros2", "node", "list", "--no-daemon"],
            ["ros2", "node", "list"],
            parser=self._parse_name_lines,
            timeout=3,
            samples=1,
        )
        services_result = self._sample_ros_graph(
            ["ros2", "service", "list", "--no-daemon", "-t"],
            ["ros2", "service", "list", "-t"],
            parser=self._parse_name_type_lines,
            timeout=3,
            samples=1,
        )
        available = bool(topics_result.get("ok") or nodes_result.get("ok") or services_result.get("ok"))
        return {
            "available": available,
            "topics": topics_result.get("items", []),
            "nodes": nodes_result.get("items", []),
            "services": services_result.get("items", []),
            "runtime": {
                "topics_rmw": topics_result.get("rmw", ""),
                "nodes_rmw": nodes_result.get("rmw", ""),
                "services_rmw": services_result.get("rmw", ""),
                "topics_samples": topics_result.get("samples", 0),
                "nodes_samples": nodes_result.get("samples", 0),
                "services_samples": services_result.get("samples", 0),
                "ros_domain_id": os.environ.get("ROS_DOMAIN_ID", "(unset)"),
                "ros_localhost_only": os.environ.get("ROS_LOCALHOST_ONLY", "(unset)"),
                "rmw_implementation": os.environ.get("RMW_IMPLEMENTATION", "(auto)"),
                "robodataset_rmw_implementation": os.environ.get("ROBODATASET_RMW_IMPLEMENTATION", "(auto)"),
                "ros_setup": os.environ.get("ROS_SETUP", ""),
            },
            "errors": {
                "topics": "" if topics_result.get("ok") else str(topics_result.get("stderr") or ""),
                "nodes": "" if nodes_result.get("ok") else str(nodes_result.get("stderr") or ""),
                "services": "" if services_result.get("ok") else str(services_result.get("stderr") or ""),
            },
        }

    def _sample_ros_graph(
        self,
        primary: list[str],
        fallback: list[str],
        *,
        parser: Any,
        timeout: int,
        samples: int = 3,
    ) -> dict[str, Any]:
        merged: dict[str, dict[str, str]] = {}
        best_result: dict[str, Any] | None = None
        errors: list[str] = []
        for index in range(max(samples, 1)):
            result = self._run_ros_with_fallback(primary, fallback, timeout=timeout)
            if result.get("ok"):
                rows = parser(str(result.get("stdout") or ""))
                if best_result is None or len(rows) > len(best_result.get("items", [])):
                    best_result = {**result, "items": rows}
                for row in rows:
                    key = str(row.get("topic") or row.get("name") or "")
                    if key:
                        merged[key] = row
            else:
                errors.append(str(result.get("stderr") or ""))
            if index < samples - 1:
                time.sleep(0.25)
        if merged:
            items = [merged[key] for key in sorted(merged)]
            result = best_result or {"ok": True, "stdout": "", "stderr": "", "returncode": 0}
            return {**result, "ok": True, "items": items, "samples": samples}
        result = best_result or {"ok": False, "stdout": "", "stderr": "\n".join(error for error in errors if error), "returncode": 1}
        return {**result, "items": [], "samples": samples}

    def topic_info(self, topic: str) -> dict[str, Any]:
        rclpy_result = self._topic_info_rclpy(topic)
        if rclpy_result.get("ok"):
            return rclpy_result
        cli_result = self._run_ros_with_fallback(["ros2", "topic", "info", "--no-daemon", topic], ["ros2", "topic", "info", topic], timeout=8)
        if not cli_result.get("ok") and rclpy_result.get("stderr"):
            cli_result["stderr"] = f"{rclpy_result.get('stderr')}\n{cli_result.get('stderr', '')}".strip()
        return cli_result

    def echo_once(self, topic: str) -> dict[str, Any]:
        rclpy_result = self._echo_once_rclpy(topic)
        if rclpy_result.get("ok"):
            return rclpy_result
        cli_result = self._run_ros_with_fallback(
            ["ros2", "topic", "echo", "--no-daemon", "--once", "--truncate-length", "512", topic],
            ["ros2", "topic", "echo", "--once", "--truncate-length", "512", topic],
            timeout=8,
        )
        if not cli_result.get("ok") and rclpy_result.get("stderr"):
            cli_result["stderr"] = f"{rclpy_result.get('stderr')}\n{cli_result.get('stderr', '')}".strip()
        return cli_result

    def topic_hz(self, topic: str) -> dict[str, Any]:
        rclpy_result = self._topic_hz_rclpy(topic)
        if rclpy_result.get("ok"):
            return rclpy_result
        cli_result = self._run_ros(["ros2", "topic", "hz", topic, "--window", "10"], timeout=8)
        if not cli_result.get("ok") and rclpy_result.get("stderr"):
            cli_result["stderr"] = f"{rclpy_result.get('stderr')}\n{cli_result.get('stderr', '')}".strip()
        return cli_result

    def node_info(self, node: str) -> dict[str, Any]:
        return self._run_ros_with_fallback(["ros2", "node", "info", "--no-daemon", node], ["ros2", "node", "info", node], timeout=8)

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
            from sensor_msgs.msg import CompressedImage
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
                    "message_type": "sensor_msgs/msg/Image",
                    "height": int(msg.height),
                    "width": int(msg.width),
                    "encoding": str(msg.encoding),
                    "is_bigendian": int(msg.is_bigendian),
                    "step": int(msg.step),
                }

            def on_compressed_image(msg: CompressedImage) -> None:
                captured["data"] = bytes(msg.data)
                captured["meta"] = {
                    "message_type": "sensor_msgs/msg/CompressedImage",
                    "format": str(msg.format),
                    "compressed_size": len(msg.data),
                }

            message_type = self._discover_topic_type(node, executor, topic, timeout=1.5)
            if message_type == "sensor_msgs/msg/CompressedImage":
                node.create_subscription(CompressedImage, topic, on_compressed_image, qos_profile_sensor_data)
            else:
                node.create_subscription(Image, topic, on_image, qos_profile_sensor_data)
            deadline = time.time() + timeout
            while time.time() < deadline and "data" not in captured:
                executor.spin_once(timeout_sec=0.1)
            if "data" not in captured:
                return {"ok": False, "error": f"no image received from {topic} before timeout"}
            meta = captured["meta"]
            frame = (
                compressed_image_to_rgb(captured["data"], meta)
                if meta.get("message_type") == "sensor_msgs/msg/CompressedImage"
                else image_bytes_to_rgb(captured["data"], meta)
            )
            if frame is None:
                return {"ok": False, "error": f"unsupported image encoding: {meta.get('encoding') or meta.get('format')}", "meta": meta}
            height, width = int(frame.shape[0]), int(frame.shape[1])
            ppm = f"P6\n{width} {height}\n255\n".encode("ascii") + frame.tobytes()
            meta["rgb_width"] = width
            meta["rgb_height"] = height
            meta["mean_brightness"] = float(frame.mean())
            return {
                "ok": True,
                "topic": topic,
                "meta": meta,
                "image_rgb_base64": base64.b64encode(frame.tobytes()).decode("ascii"),
                "image_ppm_base64": base64.b64encode(ppm).decode("ascii"),
            }
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

    def _topic_info_rclpy(self, topic: str, *, timeout: float = 3.0) -> dict[str, Any]:
        try:
            self._prepare_ros_process_env()
            import rclpy
            from rclpy.executors import SingleThreadedExecutor
        except Exception as exc:
            return {"ok": False, "stdout": "", "stderr": f"rclpy topic info unavailable: {exc}", "returncode": 1, "backend": "rclpy"}

        context = rclpy.Context()
        node = None
        executor = None
        try:
            rclpy.init(context=context)
            node = rclpy.create_node(f"robodataset_v3_topic_info_{uuid4().hex[:8]}", context=context)
            executor = SingleThreadedExecutor(context=context)
            executor.add_node(node)
            deadline = time.time() + timeout
            msg_types: list[str] = []
            publishers = []
            subscriptions = []
            while time.time() < deadline:
                executor.spin_once(timeout_sec=0.1)
                topic_map = dict(node.get_topic_names_and_types())
                msg_types = [str(item) for item in topic_map.get(topic, [])]
                publishers = node.get_publishers_info_by_topic(topic)
                subscriptions = node.get_subscriptions_info_by_topic(topic)
                if msg_types or publishers or subscriptions:
                    break
            msg_type = msg_types[0] if msg_types else "unknown"
            stdout = "\n".join(
                [
                    f"Type: {msg_type}",
                    f"Publisher count: {len(publishers)}",
                    f"Subscription count: {len(subscriptions)}",
                ]
            )
            return {
                "ok": bool(msg_types or publishers or subscriptions),
                "stdout": stdout,
                "stderr": "" if msg_types or publishers or subscriptions else f"topic not discovered before timeout: {topic}",
                "returncode": 0 if msg_types or publishers or subscriptions else 1,
                "rmw": os.environ.get("RMW_IMPLEMENTATION", ""),
                "backend": "rclpy",
                "message_type": msg_type,
                "structured": {
                    "topic": topic,
                    "message_type": msg_type,
                    "publisher_count": len(publishers),
                    "subscription_count": len(subscriptions),
                },
            }
        except Exception as exc:
            return {"ok": False, "stdout": "", "stderr": f"rclpy topic info failed: {exc}", "returncode": 1, "backend": "rclpy"}
        finally:
            self._shutdown_rclpy(context, node, executor)

    def _echo_once_rclpy(self, topic: str, *, timeout: float = 5.0) -> dict[str, Any]:
        try:
            self._prepare_ros_process_env()
            import rclpy
            from rclpy.executors import SingleThreadedExecutor
            from rclpy.qos import qos_profile_sensor_data
            from rosidl_runtime_py.utilities import get_message
        except Exception as exc:
            return {"ok": False, "stdout": "", "stderr": f"rclpy echo unavailable: {exc}", "returncode": 1, "backend": "rclpy"}

        context = rclpy.Context()
        node = None
        executor = None
        try:
            rclpy.init(context=context)
            node = rclpy.create_node(f"robodataset_v3_topic_echo_{uuid4().hex[:8]}", context=context)
            executor = SingleThreadedExecutor(context=context)
            executor.add_node(node)
            msg_type = self._discover_topic_type(node, executor, topic, timeout=min(timeout, 2.0))
            if not msg_type:
                return {"ok": False, "stdout": "", "stderr": f"cannot discover message type for {topic}", "returncode": 1, "backend": "rclpy"}
            msg_cls = get_message(msg_type)
            captured: dict[str, Any] = {}

            def on_message(msg: Any) -> None:
                captured["message"] = msg

            node.create_subscription(msg_cls, topic, on_message, qos_profile_sensor_data)
            deadline = time.time() + timeout
            while time.time() < deadline and "message" not in captured:
                executor.spin_once(timeout_sec=0.1)
            if "message" not in captured:
                return {"ok": False, "stdout": "", "stderr": f"no message received from {topic} before timeout", "returncode": 124, "backend": "rclpy", "message_type": msg_type}
            stdout = self._message_summary(captured["message"], msg_type)
            return {
                "ok": True,
                "stdout": stdout,
                "stderr": "",
                "returncode": 0,
                "rmw": os.environ.get("RMW_IMPLEMENTATION", ""),
                "backend": "rclpy",
                "message_type": msg_type,
                "structured": self._message_structured(captured["message"], msg_type),
            }
        except Exception as exc:
            return {"ok": False, "stdout": "", "stderr": f"rclpy echo failed: {exc}", "returncode": 1, "backend": "rclpy"}
        finally:
            self._shutdown_rclpy(context, node, executor)

    def _topic_hz_rclpy(self, topic: str, *, timeout: float = 5.0, window: int = 10) -> dict[str, Any]:
        try:
            self._prepare_ros_process_env()
            import rclpy
            from rclpy.executors import SingleThreadedExecutor
            from rclpy.qos import qos_profile_sensor_data
            from rosidl_runtime_py.utilities import get_message
        except Exception as exc:
            return {"ok": False, "stdout": "", "stderr": f"rclpy hz unavailable: {exc}", "returncode": 1, "backend": "rclpy"}

        context = rclpy.Context()
        node = None
        executor = None
        try:
            rclpy.init(context=context)
            node = rclpy.create_node(f"robodataset_v3_topic_hz_{uuid4().hex[:8]}", context=context)
            executor = SingleThreadedExecutor(context=context)
            executor.add_node(node)
            msg_type = self._discover_topic_type(node, executor, topic, timeout=min(timeout, 2.0))
            if not msg_type:
                return {"ok": False, "stdout": "", "stderr": f"cannot discover message type for {topic}", "returncode": 1, "backend": "rclpy"}
            msg_cls = get_message(msg_type)
            timestamps: list[float] = []

            def on_message(msg: Any) -> None:
                del msg
                timestamps.append(time.time())

            node.create_subscription(msg_cls, topic, on_message, qos_profile_sensor_data)
            deadline = time.time() + timeout
            while time.time() < deadline and len(timestamps) < window:
                executor.spin_once(timeout_sec=0.1)
            if len(timestamps) < 2:
                return {"ok": False, "stdout": "", "stderr": f"not enough messages received from {topic} before timeout", "returncode": 124, "backend": "rclpy", "message_type": msg_type}
            intervals = [later - earlier for earlier, later in zip(timestamps, timestamps[1:]) if later > earlier]
            average_rate = (len(timestamps) - 1) / max(timestamps[-1] - timestamps[0], 1e-9)
            min_delta = min(intervals) if intervals else 0.0
            max_delta = max(intervals) if intervals else 0.0
            stdout = "\n".join(
                [
                    f"average rate: {average_rate:.3f}",
                    f"min: {min_delta:.3f}s max: {max_delta:.3f}s window: {len(timestamps)}",
                ]
            )
            return {
                "ok": True,
                "stdout": stdout,
                "stderr": "",
                "returncode": 0,
                "rmw": os.environ.get("RMW_IMPLEMENTATION", ""),
                "backend": "rclpy",
                "message_type": msg_type,
                "structured": {
                    "topic": topic,
                    "message_type": msg_type,
                    "average_rate_hz": round(average_rate, 3),
                    "min_delta_sec": round(min_delta, 6),
                    "max_delta_sec": round(max_delta, 6),
                    "window": len(timestamps),
                },
            }
        except Exception as exc:
            return {"ok": False, "stdout": "", "stderr": f"rclpy hz failed: {exc}", "returncode": 1, "backend": "rclpy"}
        finally:
            self._shutdown_rclpy(context, node, executor)

    def _discover_topic_type(self, node: Any, executor: Any, topic: str, *, timeout: float) -> str:
        deadline = time.time() + timeout
        while time.time() < deadline:
            executor.spin_once(timeout_sec=0.1)
            topic_map = dict(node.get_topic_names_and_types())
            types = topic_map.get(topic, [])
            if types:
                return str(types[0])
        return ""

    def _message_summary(self, msg: Any, msg_type: str) -> str:
        if msg_type == "sensor_msgs/msg/Image":
            data = list(bytes(getattr(msg, "data", b""))[:32])
            return "\n".join(
                [
                    "header:",
                    f"  stamp: {getattr(getattr(msg, 'header', None), 'stamp', '')}",
                    f"  frame_id: {getattr(getattr(msg, 'header', None), 'frame_id', '')}",
                    f"height: {getattr(msg, 'height', '')}",
                    f"width: {getattr(msg, 'width', '')}",
                    f"encoding: {getattr(msg, 'encoding', '')}",
                    f"is_bigendian: {getattr(msg, 'is_bigendian', '')}",
                    f"step: {getattr(msg, 'step', '')}",
                    f"data_length: {len(getattr(msg, 'data', []))}",
                    f"data_preview: {data}",
                ]
            )
        if msg_type == "sensor_msgs/msg/CompressedImage":
            data = list(bytes(getattr(msg, "data", b""))[:32])
            return "\n".join(
                [
                    "header:",
                    f"  stamp: {getattr(getattr(msg, 'header', None), 'stamp', '')}",
                    f"  frame_id: {getattr(getattr(msg, 'header', None), 'frame_id', '')}",
                    f"format: {getattr(msg, 'format', '')}",
                    f"data_length: {len(getattr(msg, 'data', []))}",
                    f"data_preview: {data}",
                ]
            )
        try:
            from rosidl_runtime_py import message_to_yaml

            return self._truncate_ros_text(str(message_to_yaml(msg)), limit=12000)
        except Exception:
            return self._truncate_ros_text(repr(msg), limit=12000)

    def _message_structured(self, msg: Any, msg_type: str) -> dict[str, Any]:
        if msg_type == "sensor_msgs/msg/Image":
            return {
                "message_type": msg_type,
                "header": self._header_structured(getattr(msg, "header", None)),
                "height": int(getattr(msg, "height", 0) or 0),
                "width": int(getattr(msg, "width", 0) or 0),
                "encoding": str(getattr(msg, "encoding", "") or ""),
                "is_bigendian": int(getattr(msg, "is_bigendian", 0) or 0),
                "step": int(getattr(msg, "step", 0) or 0),
                "data_length": len(getattr(msg, "data", []) or []),
            }
        if msg_type == "sensor_msgs/msg/CompressedImage":
            return {
                "message_type": msg_type,
                "header": self._header_structured(getattr(msg, "header", None)),
                "format": str(getattr(msg, "format", "") or ""),
                "data_length": len(getattr(msg, "data", []) or []),
            }
        if msg_type == "sensor_msgs/msg/JointState":
            names = [str(item) for item in list(getattr(msg, "name", []) or [])]
            positions = [float(item) for item in list(getattr(msg, "position", []) or [])]
            velocities = [float(item) for item in list(getattr(msg, "velocity", []) or [])]
            efforts = [float(item) for item in list(getattr(msg, "effort", []) or [])]
            return {
                "message_type": msg_type,
                "header": self._header_structured(getattr(msg, "header", None)),
                "joint_order": names,
                "joint_count": len(names),
                "position_dim": len(positions),
                "velocity_dim": len(velocities),
                "effort_dim": len(efforts),
                "position": positions,
                "velocity": velocities,
                "effort": efforts,
            }
        try:
            from rosidl_runtime_py.convert import message_to_ordereddict

            converted = message_to_ordereddict(msg)
            return {"message_type": msg_type, "sample": self._json_safe_truncate(converted)}
        except Exception:
            return {"message_type": msg_type, "sample": self._truncate_ros_text(repr(msg), limit=4000)}

    def _header_structured(self, header: Any) -> dict[str, Any]:
        if header is None:
            return {}
        stamp = getattr(header, "stamp", None)
        return {
            "stamp": {
                "sec": int(getattr(stamp, "sec", 0) or 0),
                "nanosec": int(getattr(stamp, "nanosec", 0) or 0),
            },
            "frame_id": str(getattr(header, "frame_id", "") or ""),
        }

    def _json_safe_truncate(self, value: Any, *, depth: int = 0, max_items: int = 24) -> Any:
        if depth > 4:
            return str(value)
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(key): self._json_safe_truncate(item, depth=depth + 1, max_items=max_items) for key, item in list(value.items())[:max_items]}
        if isinstance(value, (list, tuple)):
            items = [self._json_safe_truncate(item, depth=depth + 1, max_items=max_items) for item in list(value)[:max_items]]
            if len(value) > max_items:
                items.append(f"... truncated {len(value) - max_items} items")
            return items
        return str(value)

    def _truncate_ros_text(self, text: str, *, limit: int) -> str:
        if len(text) <= limit:
            return text
        keep = max(int((limit - 80) / 2), 1)
        return f"{text[:keep]}\n...[truncated {len(text) - keep * 2} chars]...\n{text[-keep:]}"

    def _prepare_ros_process_env(self) -> None:
        apply_ros_environment(os.environ)
        if os.environ.get("ROBODATASET_DISABLE_FASTDDS_SHM", "1") == "1":
            profile = Path(__file__).resolve().parents[3] / "config" / "fastdds_no_shm.xml"
            if profile.exists():
                os.environ.setdefault("FASTDDS_DEFAULT_PROFILES_FILE", str(profile))
                os.environ.setdefault("FASTRTPS_DEFAULT_PROFILES_FILE", str(profile))
        self._ensure_ros_pythonpath()

    def _ensure_ros_pythonpath(self) -> None:
        ros_setup = os.environ.get("ROS_SETUP", default_ros_setup())
        ros_root = str(Path(ros_setup).resolve().parent) if ros_setup else "/opt/ros/humble"
        major_minor = f"python{sys.version_info.major}.{sys.version_info.minor}"
        candidates = [
            str(Path(ros_root) / "lib" / major_minor / "site-packages"),
            str(Path(ros_root) / "local" / "lib" / major_minor / "dist-packages"),
        ]
        existing = [path for path in os.environ.get("PYTHONPATH", "").split(os.pathsep) if path]
        prepend = [path for path in candidates if Path(path).is_dir() and path not in existing]
        if prepend:
            os.environ["PYTHONPATH"] = os.pathsep.join([*prepend, *existing])
        for path in reversed(prepend):
            if path not in sys.path:
                sys.path.insert(0, path)

    def _shutdown_rclpy(self, context: Any, node: Any, executor: Any) -> None:
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
            try:
                import rclpy

                rclpy.shutdown(context=context)
            except Exception:
                pass

    def _run_ros(self, command: list[str], timeout: int, *, rmw: str | None = None) -> dict[str, Any]:
        ros_setup = os.environ.get("ROS_SETUP", default_ros_setup())
        quoted = " ".join(shlex.quote(item) for item in command)
        shell_command = f"source {shlex.quote(ros_setup)} >/dev/null 2>&1 || true; exec {quoted}"
        env = os.environ.copy()
        selected_rmw = select_rmw(rmw or env.get("RMW_IMPLEMENTATION") or os.environ.get("ROBODATASET_RMW_IMPLEMENTATION"))
        env["RMW_IMPLEMENTATION"] = selected_rmw
        ros_log_dir = env.get("ROS_LOG_DIR") or "/tmp/robodataset_ros_logs"
        try:
            Path(ros_log_dir).mkdir(parents=True, exist_ok=True)
        except Exception:
            ros_log_dir = "/tmp"
        env["ROS_LOG_DIR"] = ros_log_dir
        try:
            process = subprocess.Popen(
                ["/bin/bash", "-lc", shell_command],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                start_new_session=True,
            )
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                self._terminate_process_group(process)
                stdout, stderr = process.communicate(timeout=1)
                return {
                    "ok": bool((stdout or "").strip()),
                    "stdout": (stdout or "").strip(),
                    "stderr": (stderr or "").strip() or "command timed out",
                    "returncode": 124,
                    "rmw": selected_rmw,
                }
        except FileNotFoundError:
            return {"ok": False, "stdout": "", "stderr": "ros2 command not found", "returncode": 127, "rmw": selected_rmw}
        return {
            "ok": process.returncode == 0,
            "stdout": (stdout or "").strip(),
            "stderr": (stderr or "").strip(),
            "returncode": process.returncode,
            "rmw": selected_rmw,
        }

    def _terminate_process_group(self, process: subprocess.Popen[str]) -> None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except Exception:
            try:
                process.terminate()
            except Exception:
                return
        try:
            process.wait(timeout=0.5)
        except Exception:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass

    def _run_ros_with_fallback(self, primary: list[str], fallback: list[str], timeout: int) -> dict[str, Any]:
        errors = []
        for rmw in self._rmw_candidates():
            result = self._run_ros(primary, timeout=timeout, rmw=rmw)
            if result.get("ok"):
                return result
            fallback_result = self._run_ros(fallback, timeout=timeout, rmw=rmw)
            if fallback_result.get("ok"):
                stderr = str(result.get("stderr") or "").strip()
                if stderr:
                    fallback_result["fallback_from"] = stderr
                return fallback_result
            errors.append(self._combined_error(result, fallback_result))
        last = fallback_result if "fallback_result" in locals() else {"ok": False, "stdout": "", "stderr": "", "returncode": 1}
        last["stderr"] = "\n\n".join(error for error in errors if error).strip()
        return last

    def _rmw_candidates(self) -> list[str]:
        configured = select_rmw(os.environ.get("RMW_IMPLEMENTATION") or os.environ.get("ROBODATASET_RMW_IMPLEMENTATION"))
        candidates = [configured, *available_rmw_implementations(), "rmw_fastrtps_cpp", "rmw_cyclonedds_cpp"]
        unique = []
        for item in candidates:
            if item and item not in unique:
                unique.append(item)
        return unique

    def _combined_error(self, primary: dict[str, Any], fallback: dict[str, Any]) -> str:
        rmw = str(primary.get("rmw") or fallback.get("rmw") or "")
        primary_stderr = str(primary.get("stderr") or "").strip()
        fallback_stderr = str(fallback.get("stderr") or "").strip()
        if primary_stderr and fallback_stderr and primary_stderr != fallback_stderr:
            return f"[{rmw}] {primary_stderr}\nfallback failed:\n{fallback_stderr}"
        if primary_stderr:
            return f"[{rmw}] {primary_stderr}"
        if fallback_stderr:
            return f"[{rmw}] {fallback_stderr}"
        return f"[{rmw}] ros2 command failed"

    def _parse_name_type_lines(self, text: str) -> list[dict[str, str]]:
        items = []
        for line in text.splitlines():
            line = self._clean_ros_output_line(line)
            if not line or not line.startswith("/"):
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
        return [{"name": line} for raw in text.splitlines() if (line := self._clean_ros_output_line(raw)) and line.startswith("/")]

    def _clean_ros_output_line(self, line: str) -> str:
        return re.sub(r"\x1b\[[0-9;]*m", "", line).strip()


ros_service = RosService()
