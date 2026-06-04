from __future__ import annotations

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
            result = subprocess.run(command, capture_output=True, text=True, timeout=8, check=False)
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

