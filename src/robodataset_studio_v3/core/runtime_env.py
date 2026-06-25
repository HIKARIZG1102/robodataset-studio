from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


RMW_PREFERENCE = ("rmw_fastrtps_cpp", "rmw_cyclonedds_cpp")


def default_ros_setup() -> str:
    for candidate in (
        os.environ.get("ROS_SETUP", ""),
        "/opt/ros/humble/setup.bash",
        "/opt/ros/jazzy/setup.bash",
    ):
        if candidate and Path(candidate).is_file():
            return candidate
    return os.environ.get("ROS_SETUP", "/opt/ros/humble/setup.bash")


def available_rmw_implementations() -> list[str]:
    found: list[str] = []
    try:
        completed = subprocess.run(["ros2", "pkg", "list"], check=False, capture_output=True, text=True, timeout=5)
        if completed.returncode == 0:
            packages = set(completed.stdout.split())
            if "rmw_fastrtps_cpp" in packages:
                found.append("rmw_fastrtps_cpp")
            if "rmw_cyclonedds_cpp" in packages:
                found.append("rmw_cyclonedds_cpp")
    except Exception:
        pass
    for name in RMW_PREFERENCE:
        if name not in found and _rmw_library_exists(name):
            found.append(name)
    return found


def select_rmw(explicit: str | None = None) -> str:
    explicit = explicit or os.environ.get("ROBODATASET_RMW_IMPLEMENTATION") or os.environ.get("RMW_IMPLEMENTATION")
    available = available_rmw_implementations()
    if explicit:
        if explicit in available or not available:
            return explicit
        return available[0]
    if available:
        return available[0]
    return "rmw_fastrtps_cpp"


def apply_ros_environment(env: dict[str, str] | None = None) -> dict[str, str]:
    target = env if env is not None else os.environ
    target.setdefault("ROS_SETUP", default_ros_setup())
    selected = select_rmw(target.get("ROBODATASET_RMW_IMPLEMENTATION") or target.get("RMW_IMPLEMENTATION"))
    target["ROBODATASET_RMW_IMPLEMENTATION"] = selected
    target["RMW_IMPLEMENTATION"] = selected
    target.setdefault("ROS_LOG_DIR", "/tmp/robodataset_ros_logs")
    try:
        Path(target["ROS_LOG_DIR"]).mkdir(parents=True, exist_ok=True)
    except Exception:
        target["ROS_LOG_DIR"] = "/tmp"
    return target


def _rmw_library_exists(name: str) -> bool:
    lib_name = f"lib{name}.so"
    if shutil.which("ldconfig"):
        try:
            completed = subprocess.run(["ldconfig", "-p"], check=False, capture_output=True, text=True, timeout=3)
            if lib_name in completed.stdout:
                return True
        except Exception:
            pass
    for root in ("/opt/ros/humble", "/opt/ros/jazzy"):
        if any(Path(root).glob(f"**/{lib_name}")):
            return True
    return False

