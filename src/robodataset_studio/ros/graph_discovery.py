from __future__ import annotations

import os
import shutil
import subprocess


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
        try:
            env = os.environ.copy()
            env.setdefault("ROS_LOG_DIR", "/tmp/ros_logs")
            env.setdefault("RMW_IMPLEMENTATION", "rmw_cyclonedds_cpp")
            os.makedirs(env["ROS_LOG_DIR"], exist_ok=True)
            result = subprocess.run(
                self._without_daemon(command),
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
                env=env,
            )
        except Exception:
            return []
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

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

    def _without_daemon(self, command: list[str]) -> list[str]:
        if len(command) >= 3 and command[:2] == ["ros2", "topic"] and "--no-daemon" not in command:
            return [*command, "--no-daemon"]
        if len(command) >= 3 and command[:2] == ["ros2", "node"] and "--no-daemon" not in command:
            return [*command, "--no-daemon"]
        return command

    def _parse_count(self, line: str) -> int:
        try:
            return int(line.split(":", 1)[1].strip())
        except Exception:
            return 0
