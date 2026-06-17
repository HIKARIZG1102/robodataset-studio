from __future__ import annotations

import subprocess
import time
import base64
import os
import re
import shlex
from pathlib import Path
from typing import Any
from uuid import uuid4

from robodataset_studio_v3.ros.image_conversion import image_bytes_to_rgb
from robodataset_studio_v3.services.task_service import task_service


class RosService:
    def graph(self) -> dict[str, Any]:
        topics_result = self._run_ros_with_fallback(["ros2", "topic", "list", "-t", "--no-daemon"], ["ros2", "topic", "list", "-t"], timeout=8)
        nodes_result = self._run_ros_with_fallback(["ros2", "node", "list", "--no-daemon"], ["ros2", "node", "list"], timeout=8)
        services_result = self._run_ros_with_fallback(["ros2", "service", "list", "-t", "--no-daemon"], ["ros2", "service", "list", "-t"], timeout=8)
        available = bool(topics_result.get("ok") or nodes_result.get("ok") or services_result.get("ok"))
        return {
            "available": available,
            "topics": self._parse_name_type_lines(str(topics_result.get("stdout") or "")),
            "nodes": self._parse_name_lines(str(nodes_result.get("stdout") or "")),
            "services": self._parse_name_type_lines(str(services_result.get("stdout") or "")),
            "runtime": {
                "topics_rmw": topics_result.get("rmw", ""),
                "nodes_rmw": nodes_result.get("rmw", ""),
                "services_rmw": services_result.get("rmw", ""),
            },
            "errors": {
                "topics": "" if topics_result.get("ok") else str(topics_result.get("stderr") or ""),
                "nodes": "" if nodes_result.get("ok") else str(nodes_result.get("stderr") or ""),
                "services": "" if services_result.get("ok") else str(services_result.get("stderr") or ""),
            },
        }

    def topic_info(self, topic: str) -> dict[str, Any]:
        return self._run_ros_with_fallback(["ros2", "topic", "info", topic, "--no-daemon"], ["ros2", "topic", "info", topic], timeout=8)

    def echo_once(self, topic: str) -> dict[str, Any]:
        return self._run_ros(["ros2", "topic", "echo", "--once", topic], timeout=8)

    def topic_hz(self, topic: str) -> dict[str, Any]:
        return self._run_ros(["ros2", "topic", "hz", topic, "--window", "10"], timeout=8)

    def node_info(self, node: str) -> dict[str, Any]:
        return self._run_ros_with_fallback(["ros2", "node", "info", node, "--no-daemon"], ["ros2", "node", "info", node], timeout=8)

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

    def _run_ros(self, command: list[str], timeout: int, *, rmw: str | None = None) -> dict[str, Any]:
        ros_setup = os.environ.get("ROS_SETUP", "/opt/ros/humble/setup.bash")
        quoted = " ".join(shlex.quote(item) for item in command)
        shell_command = f"source {shlex.quote(ros_setup)} >/dev/null 2>&1 || true; exec {quoted}"
        env = os.environ.copy()
        selected_rmw = rmw or env.get("RMW_IMPLEMENTATION") or os.environ.get("ROBODATASET_RMW_IMPLEMENTATION") or "rmw_cyclonedds_cpp"
        env["RMW_IMPLEMENTATION"] = selected_rmw
        ros_log_dir = env.get("ROS_LOG_DIR") or "/tmp/robodataset_ros_logs"
        try:
            Path(ros_log_dir).mkdir(parents=True, exist_ok=True)
        except Exception:
            ros_log_dir = "/tmp"
        env["ROS_LOG_DIR"] = ros_log_dir
        try:
            completed = subprocess.run(
                ["/bin/bash", "-lc", shell_command],
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
        except FileNotFoundError:
            return {"ok": False, "stdout": "", "stderr": "ros2 command not found", "returncode": 127, "rmw": selected_rmw}
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            return {"ok": bool(stdout.strip()), "stdout": stdout.strip(), "stderr": stderr.strip() or "command timed out", "returncode": 124, "rmw": selected_rmw}
        return {
            "ok": completed.returncode == 0,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
            "returncode": completed.returncode,
            "rmw": selected_rmw,
        }

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
        configured = os.environ.get("RMW_IMPLEMENTATION") or os.environ.get("ROBODATASET_RMW_IMPLEMENTATION") or "rmw_cyclonedds_cpp"
        candidates = [configured, "rmw_fastrtps_cpp", "rmw_cyclonedds_cpp"]
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
