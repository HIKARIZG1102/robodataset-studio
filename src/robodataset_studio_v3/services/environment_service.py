from __future__ import annotations

import importlib
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

from robodataset_studio_v3.core.runtime_env import available_rmw_implementations, default_ros_setup, select_rmw


class EnvironmentService:
    def diagnostics(self) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        issues: list[dict[str, str]] = []

        def add(name: str, value: object, status: str = "ok", *, detail: str = "", impact: str = "") -> None:
            items.append({"name": name, "value": value, "status": status, "detail": detail, "impact": impact})
            if status in {"warning", "error"}:
                issues.append({"severity": status, "name": name, "detail": detail, "impact": impact})

        py_version = ".".join(str(part) for part in sys.version_info[:3])
        add("Python executable", sys.executable)
        add("Python version", py_version, "ok" if sys.version_info[:2] == (3, 10) else "error", detail="ROS Humble Python packages require Python 3.10 ABI.", impact="ROS graph, image monitor, and real recording may fail if not running under Python 3.10.")
        add("Platform", platform.platform())
        add("Working directory", str(Path.cwd()))

        package_names = [
            "PySide6",
            "fastapi",
            "uvicorn",
            "pydantic",
            "yaml",
            "httpx",
            "websockets",
            "numpy",
            "h5py",
            "paramiko",
            "PIL",
            "cv2",
            "rclpy",
            "rosidl_runtime_py",
            "sensor_msgs",
            "std_msgs",
            "geometry_msgs",
            "nav_msgs",
            "tf2_msgs",
            "interbotix_xs_msgs",
            "realsense2_camera_msgs",
            "orbbec_camera_msgs",
            "cv_bridge",
        ]
        for package in package_names:
            status, value, detail, impact = self._import_status(package)
            add(f"Python package: {package}", value, status, detail=detail, impact=impact)

        numpy_version = tuple(int(part) for part in np.__version__.split(".")[:2] if part.isdigit())
        if numpy_version >= (2, 0):
            add(
                "NumPy ABI compatibility",
                np.__version__,
                "warning",
                detail="NumPy 2.x can conflict with ROS/OpenCV/cv_bridge modules compiled against NumPy 1.x.",
                impact="Compressed image preview, cv_bridge-based tools, or OpenCV paths may fail. Raw sensor_msgs/Image recording is less affected.",
            )
        else:
            add("NumPy ABI compatibility", np.__version__, "ok")

        ros_setup = default_ros_setup()
        add("ROS setup", ros_setup, "ok" if Path(ros_setup).is_file() else "error", detail="ROS setup file is required for ROS Python packages and ros2 CLI.", impact="ROS graph, monitor, and real recording cannot run without ROS setup.")
        add("ROS_DISTRO", os.environ.get("ROS_DISTRO", ""))
        add("ROS_DOMAIN_ID", os.environ.get("ROS_DOMAIN_ID", "(unset)"))
        add("AMENT_PREFIX_PATH", os.environ.get("AMENT_PREFIX_PATH", ""))
        add("PYTHONPATH", os.environ.get("PYTHONPATH", ""))
        add("RMW_IMPLEMENTATION", os.environ.get("RMW_IMPLEMENTATION", "(auto)"))
        add("ROBODATASET_RMW_IMPLEMENTATION", os.environ.get("ROBODATASET_RMW_IMPLEMENTATION", "(auto)"))
        available_rmw = available_rmw_implementations()
        add("Available RMW implementations", available_rmw, "ok" if available_rmw else "warning", detail="At least one ROS 2 RMW implementation should be available.", impact="ROS discovery and subscriptions require a working RMW implementation.")
        selected_rmw = select_rmw(probe_graph=True)
        add("Auto-selected RMW", selected_rmw)
        graph_scores = self._rmw_graph_scores(available_rmw)
        add("RMW graph probe scores", graph_scores)

        topic_count = self._topic_count(selected_rmw)
        add(
            "ROS graph topic count",
            topic_count,
            "ok" if topic_count > 0 else "warning",
            detail="No ROS topics were discovered with the selected RMW." if topic_count <= 0 else "",
            impact="Config topic discovery, image monitor, and real recording need visible ROS topics.",
        )

        for command in ["ros2", "ssh", "rsync", "sftp", "python3"]:
            path = shutil.which(command)
            add(f"System command: {command}", path or "missing", "ok" if path else "warning", detail=f"{command} command not found." if not path else "", impact=self._command_impact(command) if not path else "")

        return {
            "summary": {
                "python": py_version,
                "python_executable": sys.executable,
                "ros_setup": ros_setup,
                "selected_rmw": selected_rmw,
                "topic_count": topic_count,
                "issue_count": len(issues),
            },
            "items": items,
            "issues": issues,
        }

    def _import_status(self, package: str) -> tuple[str, str, str, str]:
        if package in {"cv2", "cv_bridge"}:
            return self._subprocess_import_status(package)
        try:
            module = importlib.import_module(package)
            version = getattr(module, "__version__", "")
            return "ok", str(version or "available"), "", ""
        except Exception as exc:
            status = "warning"
            impact = ""
            detail = str(exc)
            if package in {"rclpy", "rosidl_runtime_py", "sensor_msgs"}:
                status = "error"
                detail = f"{exc}. ROS setup may not be sourced, or the Python ABI may not match ROS."
                impact = "ROS graph, image monitor, and real recording cannot run."
            elif package in {"cv2", "cv_bridge"}:
                impact = "OpenCV/cv_bridge image conversion paths may fail; Pillow/QImage/raw image paths may still work."
            elif package == "paramiko":
                impact = "Password/key based SFTP upload is unavailable; rsync/ssh may still work."
            return status, "missing or failed", detail, impact

    def _subprocess_import_status(self, package: str) -> tuple[str, str, str, str]:
        script = f"import importlib; m=importlib.import_module({package!r}); print(getattr(m, '__version__', 'available'))"
        try:
            completed = subprocess.run([sys.executable, "-c", script], check=False, capture_output=True, text=True, timeout=2, env=os.environ.copy())
        except Exception as exc:
            return "warning", "missing or failed", str(exc), "OpenCV/cv_bridge image conversion paths may fail; Pillow/QImage/raw image paths may still work."
        if completed.returncode == 0:
            return "ok", completed.stdout.strip() or "available", "", ""
        detail = (completed.stderr or completed.stdout).strip()
        return "warning", "missing or failed", detail, "OpenCV/cv_bridge image conversion paths may fail; Pillow/QImage/raw image paths may still work."

    def _rmw_graph_scores(self, rmw_names: list[str]) -> dict[str, int]:
        scores: dict[str, int] = {}
        for name in rmw_names:
            scores[name] = self._topic_count(name)
        return scores

    def _topic_count(self, rmw: str) -> int:
        env = os.environ.copy()
        if rmw:
            env["RMW_IMPLEMENTATION"] = rmw
            env["ROBODATASET_RMW_IMPLEMENTATION"] = rmw
        try:
            completed = subprocess.run(["ros2", "topic", "list", "-t", "--no-daemon"], check=False, capture_output=True, text=True, timeout=1.5, env=env)
        except Exception:
            return 0
        if completed.returncode != 0:
            return 0
        return len([line for line in completed.stdout.splitlines() if line.strip()])

    def _command_impact(self, command: str) -> str:
        return {
            "ros2": "ROS graph discovery and CLI fallback checks cannot run.",
            "ssh": "SSH upload, remote browsing, and remote verification cannot run.",
            "rsync": "Rsync upload/repair-resume cannot run; SFTP may still work.",
            "sftp": "Manual SFTP tooling unavailable; Paramiko upload may still work.",
            "python3": "Remote verification scripts may fail on upload targets if python3 is missing remotely.",
        }.get(command, "")


environment_service = EnvironmentService()
