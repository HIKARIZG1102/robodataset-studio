from __future__ import annotations

import subprocess
from typing import Any

from robodataset_studio_v3.services.task_service import task_service


class RosService:
    def graph(self) -> dict[str, Any]:
        command = ["ros2", "topic", "list", "-t"]
        try:
            completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=8)
        except FileNotFoundError:
            return {"available": False, "topics": [], "error": "ros2 command not found"}
        except subprocess.TimeoutExpired:
            return {"available": False, "topics": [], "error": "ros2 topic list timed out"}
        if completed.returncode != 0:
            return {"available": False, "topics": [], "error": completed.stderr.strip()}
        topics = []
        for line in completed.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            if "[" in line and "]" in line:
                topic, msg_type = line.rsplit("[", 1)
                topics.append({"topic": topic.strip(), "message_type": msg_type.rstrip("]").strip()})
            else:
                topics.append({"topic": line, "message_type": ""})
        return {"available": True, "topics": topics, "error": ""}

    def topic_info(self, topic: str) -> dict[str, Any]:
        return self._run_ros(["ros2", "topic", "info", topic], timeout=8)

    def echo_once(self, topic: str) -> dict[str, Any]:
        return self._run_ros(["ros2", "topic", "echo", "--once", topic], timeout=8)

    def topic_hz(self, topic: str) -> dict[str, Any]:
        return self._run_ros(["ros2", "topic", "hz", topic, "--window", "10"], timeout=8)

    def check_topic_task(self, topic: str) -> dict[str, Any]:
        result = {
            "info": self.topic_info(topic),
            "echo_once": self.echo_once(topic),
            "hz": self.topic_hz(topic),
        }
        task = task_service.run_instant("ros_check", f"checked ROS topic {topic}", result)
        return {"task_id": task.task_id, "result": result}

    def _run_ros(self, command: list[str], timeout: int) -> dict[str, Any]:
        try:
            completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError:
            return {"ok": False, "stdout": "", "stderr": "ros2 command not found", "returncode": 127}
        except subprocess.TimeoutExpired:
            return {"ok": False, "stdout": "", "stderr": "command timed out", "returncode": 124}
        return {
            "ok": completed.returncode == 0,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
            "returncode": completed.returncode,
        }


ros_service = RosService()
