from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


RMW_PREFERENCE = ("rmw_cyclonedds_cpp", "rmw_fastrtps_cpp")


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
    for name in RMW_PREFERENCE:
        if _ros_package_exists(name) or _rmw_library_exists(name):
            found.append(name)
    return found


def _ros_package_exists(name: str) -> bool:
    if not shutil.which("ros2"):
        return False
    try:
        completed = subprocess.run(["ros2", "pkg", "prefix", name], check=False, capture_output=True, text=True, timeout=1.5)
        return completed.returncode == 0
    except Exception:
        return False


def select_rmw(explicit: str | None = None, *, probe_graph: bool = True) -> str:
    explicit = explicit or os.environ.get("ROBODATASET_RMW_IMPLEMENTATION") or os.environ.get("RMW_IMPLEMENTATION")
    available = available_rmw_implementations()
    if explicit:
        if explicit in available or not available:
            return explicit
        return available[0]
    if probe_graph and len(available) > 1:
        probed = _select_rmw_by_graph_probe(available)
        if probed:
            return probed
    if available:
        return available[0]
    return "rmw_cyclonedds_cpp"


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


def _select_rmw_by_graph_probe(candidates: list[str]) -> str:
    best = ""
    best_score = -1
    for candidate in candidates:
        score = _rmw_graph_score(candidate)
        if score > best_score:
            best = candidate
            best_score = score
    return best if best_score >= 0 else ""


def _rmw_graph_score(name: str) -> int:
    env = os.environ.copy()
    env["RMW_IMPLEMENTATION"] = name
    env["ROBODATASET_RMW_IMPLEMENTATION"] = name
    env.setdefault("ROS_LOG_DIR", "/tmp/robodataset_ros_logs")
    try:
        Path(env["ROS_LOG_DIR"]).mkdir(parents=True, exist_ok=True)
    except Exception:
        env["ROS_LOG_DIR"] = "/tmp"
    try:
        completed = subprocess.run(
            ["ros2", "topic", "list", "-t", "--no-daemon"],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.5,
            env=env,
        )
    except Exception:
        return -1
    if completed.returncode != 0:
        return -1
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    score = len(lines)
    output = completed.stdout
    if "sensor_msgs/msg/Image" in output:
        score += 1000
    if "sensor_msgs/msg/CompressedImage" in output:
        score += 800
    if "sensor_msgs/msg/JointState" in output:
        score += 1000
    if any(token in output for token in ("camera", "wrist", "wx250s", "joint_states")):
        score += 500
    return score
