from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys


class EnvironmentService:
    def snapshot(self) -> dict[str, str]:
        return {
            "os": platform.platform(),
            "python": sys.version.split()[0],
            "ros_distro": os.environ.get("ROS_DISTRO", ""),
            "ros_domain_id": os.environ.get("ROS_DOMAIN_ID", "0"),
            "rmw_implementation": os.environ.get("RMW_IMPLEMENTATION", ""),
            "conda_prefix": os.environ.get("CONDA_PREFIX", ""),
            "ros2_bin": shutil.which("ros2") or "",
            "nvidia_smi": shutil.which("nvidia-smi") or "",
        }

    def report_text(self) -> str:
        snap = self.snapshot()
        lines = [f"{k}: {v or '<not set>'}" for k, v in snap.items()]
        if snap["nvidia_smi"]:
            try:
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                if result.stdout.strip():
                    lines.append(f"gpu: {result.stdout.strip()}")
            except Exception as exc:  # pragma: no cover - diagnostic only
                lines.append(f"gpu_check_error: {exc}")
        return "\n".join(lines)

