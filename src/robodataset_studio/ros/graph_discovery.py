from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys


class RosGraphDiscovery:
    def ros2_available(self) -> bool:
        return shutil.which("ros2") is not None

    def discover(self) -> dict[str, list[dict[str, str]]]:
        if not self.ros2_available():
            return {"nodes": [], "topics": [], "services": [], "warning": [{"name": "ros2 not found", "type": ""}]}
        return {
            "nodes": [{"name": n, "type": ""} for n in self._run(["ros2", "node", "list"])],
            "topics": self._topics(),
            "services": [{"name": s, "type": ""} for s in self._run(["ros2", "service", "list"])],
        }

    def _run(self, command: list[str]) -> list[str]:
        commands = [self._without_daemon(command)]
        if commands[0] != command:
            commands.append(command)
        try:
            env = os.environ.copy()
            env.setdefault("ROS_LOG_DIR", "/tmp/ros_logs")
            env.setdefault("RMW_IMPLEMENTATION", "rmw_cyclonedds_cpp")
            self._ensure_ros_pythonpath(env)
            os.makedirs(env["ROS_LOG_DIR"], exist_ok=True)
            for candidate in commands:
                result = subprocess.run(
                    candidate,
                    capture_output=True,
                    text=True,
                    timeout=8,
                    check=False,
                    env=env,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return [line.strip() for line in result.stdout.splitlines() if line.strip()]
        except Exception:
            return []
        return []

    def _topics(self) -> list[dict[str, str]]:
        lines = self._run(["ros2", "topic", "list", "-t"])
        topics: list[dict[str, str]] = []
        for line in lines:
            if " [" in line and line.endswith("]"):
                name, typ = line.rsplit(" [", 1)
                topics.append({"name": name.strip(), "type": typ[:-1].strip()})
            else:
                topics.append({"name": line, "type": ""})
        return topics

    def topic_info(self, topic_name: str) -> dict[str, str | int] | None:
        lines = self._run(["ros2", "topic", "info", topic_name])
        if not lines:
            return None
        info: dict[str, str | int] = {"name": topic_name, "type": "", "publisher_count": 0, "subscription_count": 0}
        for line in lines:
            if line.startswith("Type:"):
                info["type"] = line.split(":", 1)[1].strip()
            elif line.startswith("Publisher count:"):
                info["publisher_count"] = self._parse_count(line)
            elif line.startswith("Subscription count:"):
                info["subscription_count"] = self._parse_count(line)
        return info

    def node_publishers(self, node_name: str) -> list[dict[str, str]]:
        lines = self._run(["ros2", "node", "info", node_name])
        publishers: list[dict[str, str]] = []
        in_publishers = False
        for line in lines:
            if line == "Publishers:":
                in_publishers = True
                continue
            if re.match(r"^[A-Z][A-Za-z ]+:$", line):
                if in_publishers:
                    break
                continue
            if not in_publishers:
                continue
            match = re.match(r"(?P<name>/\S+):\s+(?P<type>\S+)", line)
            if match:
                publishers.append({"name": match.group("name"), "type": match.group("type")})
        return publishers

    def _without_daemon(self, command: list[str]) -> list[str]:
        if command[:3] == ["ros2", "topic", "list"] and "--no-daemon" not in command:
            return [*command, "--no-daemon"]
        if command[:3] == ["ros2", "node", "list"] and "--no-daemon" not in command:
            return [*command, "--no-daemon"]
        if command[:3] == ["ros2", "node", "info"] and "--no-daemon" not in command:
            return [*command, "--no-daemon"]
        return command

    def _ensure_ros_pythonpath(self, env: dict[str, str]) -> None:
        ros2_path = shutil.which("ros2")
        if not ros2_path or "/opt/ros/" not in ros2_path:
            return
        ros_root = ros2_path.split("/bin/ros2", 1)[0]
        major_minor = f"python{sys.version_info.major}.{sys.version_info.minor}"
        candidates = [
            os.path.join(ros_root, "lib", major_minor, "site-packages"),
            os.path.join(ros_root, "local", "lib", major_minor, "dist-packages"),
        ]
        existing = [path for path in env.get("PYTHONPATH", "").split(os.pathsep) if path]
        prepend = [path for path in candidates if os.path.isdir(path) and path not in existing]
        if prepend:
            env["PYTHONPATH"] = os.pathsep.join([*prepend, *existing])

    def _parse_count(self, line: str) -> int:
        try:
            return int(line.split(":", 1)[1].strip())
        except Exception:
            return 0
