from __future__ import annotations

import importlib
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

from robodataset_studio_v3.core.runtime_env import RMW_PREFERENCE, available_rmw_implementations, default_ros_setup, select_rmw


RMW_NOTES = {
    "rmw_fastrtps_cpp": "FastDDS/Fast RTPS. Common ROS2 default; needs matching ROS_DOMAIN_ID, ROS_LOCALHOST_ONLY, multicast, and FastDDS shared libraries.",
    "rmw_fastrtps_dynamic_cpp": "FastDDS dynamic type support. Useful on some systems but not always installed with minimal ROS2 setups.",
    "rmw_cyclonedds_cpp": "CycloneDDS. Often robust on LANs; requires ros-<distro>-rmw-cyclonedds-cpp on the host or mounted ROS tree.",
    "rmw_connextdds": "RTI Connext DDS. Requires vendor SDK/runtime and license; Docker cannot bundle it generically.",
    "rmw_gurumdds_cpp": "GurumDDS. Requires vendor runtime/license and matching ROS RMW package.",
    "rmw_zenoh_cpp": "Zenoh RMW. Requires the Zenoh RMW package and its runtime libraries.",
}

ROS_CLI_SYSTEM_MODULES = ("packaging", "numpy", "netifaces", "yaml")
ROS_PYTHON_PACKAGES = {
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
}


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
        ros_setup = default_ros_setup()
        sourced_env = self._ros_sourced_env(ros_setup)

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
            status, value, detail, impact = self._import_status(package, sourced_env=sourced_env)
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

        add("ROS setup", ros_setup, "ok" if Path(ros_setup).is_file() else "error", detail="ROS setup file is required for ROS Python packages and ros2 CLI.", impact="ROS graph, monitor, and real recording cannot run without ROS setup.")
        add("ROS_DISTRO", os.environ.get("ROS_DISTRO", ""))
        add("ROS_DOMAIN_ID", os.environ.get("ROS_DOMAIN_ID", "(unset)"))
        add("AMENT_PREFIX_PATH", os.environ.get("AMENT_PREFIX_PATH", ""))
        add("PYTHONPATH", os.environ.get("PYTHONPATH", ""))
        add("RMW_IMPLEMENTATION", os.environ.get("RMW_IMPLEMENTATION", "(auto)"))
        add("ROBODATASET_RMW_IMPLEMENTATION", os.environ.get("ROBODATASET_RMW_IMPLEMENTATION", "(auto)"))
        add(
            "ROS sourced environment",
            "ok" if sourced_env else "not available",
            "ok" if sourced_env else "warning",
            detail="Diagnostics could not source ROS setup; checks will use the current process environment." if not sourced_env else "",
            impact="If ROS setup is not sourced, ros2 CLI plugins and Python packages may appear missing.",
        )
        available_rmw = available_rmw_implementations()
        add("Available RMW implementations", available_rmw, "ok" if available_rmw else "warning", detail="At least one ROS 2 RMW implementation should be available.", impact="ROS discovery and subscriptions require a working RMW implementation.")
        selected_rmw = select_rmw(probe_graph=True)
        add("Auto-selected RMW", selected_rmw)
        rmw_diagnostics = self._rmw_diagnostics(sourced_env or os.environ.copy())
        graph_scores = {name: int(info.get("topic_count", 0)) for name, info in rmw_diagnostics.items() if info.get("installed")}
        add("RMW graph probe scores", graph_scores)
        runnable_rmw = [name for name, info in rmw_diagnostics.items() if info.get("installed") and info.get("cli_ok")]
        add(
            "Runnable RMW/DDS implementations",
            runnable_rmw,
            "ok" if runnable_rmw else "error",
            detail="No installed RMW/DDS implementation can run ros2 topic list." if not runnable_rmw else "",
            impact="ROS graph discovery, image monitor, and recording cannot work until at least one RMW/DDS is runnable.",
        )
        for name, info in rmw_diagnostics.items():
            if not info.get("installed"):
                continue
            missing = info.get("missing_libraries", [])
            stderr = str(info.get("stderr") or "").strip()
            status = "ok" if info.get("cli_ok") and not missing else "error"
            detail_parts = []
            if missing:
                detail_parts.append("missing shared libraries: " + ", ".join(str(item) for item in missing))
            if stderr:
                detail_parts.append(stderr.splitlines()[0])
            add(
                f"RMW/DDS runtime: {name}",
                f"topics={info.get('topic_count', 0)} library={info.get('library_path') or 'package-only'}",
                status,
                detail=" | ".join(detail_parts),
                impact=RMW_NOTES.get(name, "ROS2 middleware runtime must match the publisher environment."),
            )
        missing_cli_modules = self._missing_system_python_modules(ROS_CLI_SYSTEM_MODULES, sourced_env or os.environ.copy())
        add(
            "ROS CLI system Python modules",
            "ok" if not missing_cli_modules else "missing: " + ", ".join(missing_cli_modules),
            "ok" if not missing_cli_modules else "error",
            detail="These modules must be importable by system python3 because /opt/ros/bin/ros2 does not run inside the app virtualenv.",
            impact="ros2 topic/node/service commands may fail even if the app Python environment has the same modules.",
        )

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
                "runnable_rmw": runnable_rmw,
            },
            "items": items,
            "issues": issues,
            "rmw_diagnostics": rmw_diagnostics,
            "guidance": self._environment_guidance(rmw_diagnostics, missing_cli_modules),
        }

    def _import_status(self, package: str, *, sourced_env: dict[str, str] | None = None) -> tuple[str, str, str, str]:
        if package in ROS_PYTHON_PACKAGES:
            return self._subprocess_import_status(package, env=sourced_env or os.environ.copy(), ros_package=True)
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

    def _subprocess_import_status(self, package: str, *, env: dict[str, str] | None = None, ros_package: bool = False) -> tuple[str, str, str, str]:
        script = f"import importlib; m=importlib.import_module({package!r}); print(getattr(m, '__version__', 'available'))"
        try:
            completed = subprocess.run([sys.executable, "-c", script], check=False, capture_output=True, text=True, timeout=2, env=env or os.environ.copy())
        except Exception as exc:
            impact = "ROS graph, image monitor, and real recording cannot run." if ros_package else "OpenCV/cv_bridge image conversion paths may fail; Pillow/QImage/raw image paths may still work."
            return "error" if ros_package else "warning", "missing or failed", str(exc), impact
        if completed.returncode == 0:
            return "ok", completed.stdout.strip() or "available", "", ""
        detail = (completed.stderr or completed.stdout).strip()
        if ros_package:
            return "error", "missing or failed", detail, "ROS graph, image monitor, and real recording cannot run."
        return "warning", "missing or failed", detail, "OpenCV/cv_bridge image conversion paths may fail; Pillow/QImage/raw image paths may still work."

    def _topic_count(self, rmw: str) -> int:
        env = self._ros_sourced_env(default_ros_setup()) or os.environ.copy()
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

    def _rmw_diagnostics(self, base_env: dict[str, str]) -> dict[str, dict[str, Any]]:
        diagnostics: dict[str, dict[str, Any]] = {}
        for name in RMW_PREFERENCE:
            package_exists = self._ros_package_exists(name)
            library_path = self._rmw_library_path(name)
            installed = package_exists or bool(library_path)
            info: dict[str, Any] = {
                "installed": installed,
                "package_exists": package_exists,
                "library_path": str(library_path) if library_path else "",
                "missing_libraries": self._missing_shared_libraries(library_path) if library_path else [],
                "note": RMW_NOTES.get(name, ""),
            }
            if installed:
                probe = self._run_ros_topic_list(name, base_env)
                info.update(probe)
            else:
                info.update({"cli_ok": False, "topic_count": 0, "stdout": "", "stderr": "RMW package/library not found"})
            diagnostics[name] = info
        return diagnostics

    def _ros_package_exists(self, name: str) -> bool:
        if not shutil.which("ros2"):
            return False
        try:
            completed = subprocess.run(["ros2", "pkg", "prefix", name], check=False, capture_output=True, text=True, timeout=1.5)
        except Exception:
            return False
        return completed.returncode == 0

    def _rmw_library_path(self, name: str) -> Path | None:
        lib_name = f"lib{name}.so"
        search_roots = []
        ros_setup = default_ros_setup()
        if ros_setup:
            search_roots.append(Path(ros_setup).resolve().parent)
        for root in (Path("/opt/ros/humble"), Path("/opt/ros/jazzy"), Path("/opt/ros/iron")):
            if root not in search_roots:
                search_roots.append(root)
        for root in search_roots:
            if root.exists():
                for path in root.glob(f"**/{lib_name}"):
                    return path
        if shutil.which("ldconfig"):
            try:
                completed = subprocess.run(["ldconfig", "-p"], check=False, capture_output=True, text=True, timeout=3)
            except Exception:
                return None
            for line in completed.stdout.splitlines():
                if lib_name in line and "=>" in line:
                    candidate = Path(line.rsplit("=>", 1)[1].strip())
                    if candidate.exists():
                        return candidate
        return None

    def _missing_shared_libraries(self, library_path: Path | None) -> list[str]:
        if library_path is None or not shutil.which("ldd"):
            return []
        try:
            completed = subprocess.run(["ldd", str(library_path)], check=False, capture_output=True, text=True, timeout=3)
        except Exception:
            return []
        missing = []
        for line in completed.stdout.splitlines():
            match = re.search(r"^\s*(\S+)\s+=>\s+not found", line)
            if match:
                missing.append(match.group(1))
        return sorted(set(missing))

    def _run_ros_topic_list(self, rmw: str, base_env: dict[str, str]) -> dict[str, Any]:
        env = base_env.copy()
        env["RMW_IMPLEMENTATION"] = rmw
        env["ROBODATASET_RMW_IMPLEMENTATION"] = rmw
        env.setdefault("ROS_LOG_DIR", "/tmp/robodataset_ros_logs")
        try:
            Path(env["ROS_LOG_DIR"]).mkdir(parents=True, exist_ok=True)
        except Exception:
            env["ROS_LOG_DIR"] = "/tmp"
        try:
            completed = subprocess.run(["ros2", "topic", "list", "-t", "--no-daemon"], check=False, capture_output=True, text=True, timeout=3, env=env)
        except Exception as exc:
            return {"cli_ok": False, "topic_count": 0, "stdout": "", "stderr": str(exc), "returncode": 1}
        topics = [line for line in completed.stdout.splitlines() if line.strip().startswith("/")]
        return {
            "cli_ok": completed.returncode == 0,
            "topic_count": len(topics),
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
            "returncode": completed.returncode,
        }

    def _missing_system_python_modules(self, module_names: tuple[str, ...], base_env: dict[str, str]) -> list[str]:
        missing = []
        for module_name in module_names:
            script = f"import {module_name}"
            try:
                completed = subprocess.run(["python3", "-c", script], check=False, capture_output=True, text=True, timeout=2, env=base_env)
            except Exception:
                missing.append(module_name)
                continue
            if completed.returncode != 0:
                missing.append(module_name)
        return missing

    def _ros_sourced_env(self, ros_setup: str) -> dict[str, str]:
        if not ros_setup or not Path(ros_setup).is_file():
            return {}
        command = (
            f"source {shlex.quote(ros_setup)} >/dev/null 2>&1 || exit 1; "
            "python3 - <<'PY'\n"
            "import json, os\n"
            "print(json.dumps(dict(os.environ)))\n"
            "PY"
        )
        try:
            completed = subprocess.run(["/bin/bash", "-lc", command], check=False, capture_output=True, text=True, timeout=3)
        except Exception:
            return {}
        if completed.returncode != 0:
            return {}
        try:
            import json

            payload = json.loads(completed.stdout)
        except Exception:
            return {}
        return {str(key): str(value) for key, value in payload.items()}

    def _environment_guidance(self, rmw_diagnostics: dict[str, dict[str, Any]], missing_cli_modules: list[str]) -> list[str]:
        guidance = [
            "For ROS2 Docker use, mount /opt/ros read-only and run with --network host --ipc host.",
            "Publisher and RoboDataset Studio must share ROS_DOMAIN_ID, ROS_LOCALHOST_ONLY, and a compatible RMW/DDS implementation.",
            "FastDDS and CycloneDDS are the main open-source ROS2 paths. Connext/GurumDDS require vendor runtimes and licenses if used.",
        ]
        if missing_cli_modules:
            guidance.append("Install missing system Python modules for ros2 CLI: " + ", ".join(missing_cli_modules))
        for name, info in rmw_diagnostics.items():
            if not info.get("installed"):
                continue
            if info.get("missing_libraries"):
                guidance.append(f"{name} is installed but missing shared libraries: " + ", ".join(str(item) for item in info.get("missing_libraries", [])))
            if not info.get("cli_ok"):
                stderr = str(info.get("stderr") or "").splitlines()
                guidance.append(f"{name} ros2 CLI probe failed: {stderr[0] if stderr else 'unknown error'}")
        return guidance

    def _command_impact(self, command: str) -> str:
        return {
            "ros2": "ROS graph discovery and CLI fallback checks cannot run.",
            "ssh": "SSH upload, remote browsing, and remote verification cannot run.",
            "rsync": "Rsync upload/repair-resume cannot run; SFTP may still work.",
            "sftp": "Manual SFTP tooling unavailable; Paramiko upload may still work.",
            "python3": "Remote verification scripts may fail on upload targets if python3 is missing remotely.",
        }.get(command, "")


environment_service = EnvironmentService()
