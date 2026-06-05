from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .models import ProjectState


class ConfigManager:
    def build_default_config(self, state: ProjectState, topics: list[dict[str, str]] | None = None) -> dict[str, Any]:
        topics = topics or []
        image_topics = [t for t in topics if "Image" in t.get("type", "") or "image" in t.get("name", "").lower()]
        joint_topic = next((t["name"] for t in topics if "joint" in t.get("name", "").lower()), None)
        action_topic = next((t["name"] for t in topics if "action" in t.get("name", "").lower()), None)
        if not topics:
            joint_topic = "/wx250s/joint_states"

        cameras = []
        streams = []
        for idx, topic in enumerate(image_topics[:4]):
            role = "wrist" if "wrist" in topic["name"].lower() else "base" if idx == 0 else "external"
            name = "rgb_wrist" if role == "wrist" else "rgb_static" if idx == 0 else f"rgb_{idx}"
            camera = {
                "name": name,
                "role": role,
                "topic": topic["name"],
                "type": topic.get("type", "sensor_msgs/msg/Image"),
                "encoding": "rgb8",
                "fps_target": 10,
                "crop": {"enabled": False, "x": 0, "y": 0, "width": 640, "height": 480},
                "resize": {"enabled": True, "width": 224, "height": 224},
            }
            cameras.append(camera)
            streams.append({
                "name": name,
                "modality": "rgb",
                "source": "ros2_topic",
                "topic": topic["name"],
                "message_type": camera["type"],
                "dtype": "uint8",
                "shape": [480, 640, 3],
                "encoding": "rgb8",
                "training_role": "observation",
                "preview": {"renderer": "image_rgb"},
            })

        if not cameras:
            cameras = [
                {
                    "name": "rgb_static",
                    "role": "base",
                    "topic": "/camera/camera_side/color/image_raw",
                    "type": "sensor_msgs/msg/Image",
                    "encoding": "rgb8",
                    "fps_target": 10,
                    "crop": {"enabled": False, "x": 0, "y": 0, "width": 640, "height": 480},
                    "resize": {"enabled": True, "width": 224, "height": 224},
                },
                {
                    "name": "rgb_wrist",
                    "role": "wrist",
                    "topic": "/camera/camera_wrist/color/image_raw",
                    "type": "sensor_msgs/msg/Image",
                    "encoding": "rgb8",
                    "fps_target": 10,
                    "crop": {"enabled": False, "x": 0, "y": 0, "width": 848, "height": 480},
                    "resize": {"enabled": True, "width": 224, "height": 224},
                },
            ]
            streams = [
                {
                    "name": cam["name"],
                    "modality": "rgb",
                    "source": "ros2_topic",
                    "topic": cam["topic"],
                    "message_type": cam["type"],
                    "dtype": "uint8",
                    "shape": [480, 640, 3],
                    "encoding": "rgb8",
                    "training_role": "observation",
                    "preview": {"renderer": "image_rgb"},
                }
                for cam in cameras
            ]

        config = {
            "project": {
                "name": state.task_name,
                "version": state.version,
                "operator": state.operator,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "environment": state.environment,
            },
            "robot": {
                "name": "widowx",
                "model": "wx250s",
                "description": "6-dof WidowX arm with gripper",
                "base_frame": "wx250s/base_link",
                "end_effector_frame": "wx250s/ee_gripper_link",
                "joint_state_topic": joint_topic,
                "action_topic": action_topic,
                "control": {
                    "enabled": False,
                    "mode": "external_controller_only",
                    "publishes_commands": False,
                },
                "action_format": {
                    "type": "delta_ee_pose_gripper",
                    "dim": 7,
                    "fields": ["dx", "dy", "dz", "droll", "dpitch", "dyaw", "gripper"],
                    "gripper_convention": {
                        "raw_dataset": "widowx_open_high",
                        "train_adapter": "optional_close_high",
                        "deployment": "configurable_invert",
                    },
                },
            },
            "instruction": {
                "text": "catch the satellite",
                "language": "en",
                "task_family": "manipulation",
                "success_condition": "gripper reaches and grasps target object",
            },
            "cameras": cameras,
            "streams": streams,
            "state": {
                "keys": [
                    {
                        "name": "robot_obs",
                        "source_topic": joint_topic,
                        "type": "sensor_msgs/msg/JointState",
                        "output_dim": 32,
                        "fields": ["joint_position", "joint_velocity", "gripper_state"],
                    }
                ]
                if joint_topic
                else []
            },
            "runtime": {
                "mode": "listener_only",
                "starts_external_nodes": False,
                "publishes_robot_commands": False,
            },
            "dataset": {
                "output_format": ["npz", "hdf5"],
                "npz_schema": "calvin_style",
                "hdf5_schema": "pi05_calvin_hdf5",
                "cache_root": str(state.raw_session_dir),
                "merged_root": str(state.merged_dir),
                "split": "training",
                "episode_prefix": "episode_",
                "write_language_annotations": True,
            },
            "recording": {
                "sample_rate_hz": 10,
                "sync_policy": "nearest_timestamp",
                "max_frame_lag_ms": 100,
                "min_episode_steps": 5,
                "auto_drop_empty_frames": True,
                "auto_drop_invalid_actions": True,
            },
            "genesis": {
                "enabled": False,
                "ros_bridge_namespace": "/genesis",
                "scene_file": None,
                "asset_root": None,
            },
            "ai_validation": {
                "enabled": False,
                "provider": "openai_compatible",
                "base_url": "",
                "api_key_env": "ROBOT_DATA_AI_API_KEY",
                "model": "",
            },
        }
        return config

    def dumps(self, config: dict[str, Any]) -> str:
        return yaml.safe_dump(config, allow_unicode=True, sort_keys=False)

    def loads(self, text: str) -> dict[str, Any]:
        loaded = yaml.safe_load(text)
        return loaded or {}

    def validate(self, config: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        for key in ["project", "robot", "instruction", "dataset", "recording"]:
            if key not in config:
                errors.append(f"missing required section: {key}")
        if not config.get("cameras") and not config.get("streams"):
            errors.append("missing cameras or streams")
        runtime = config.get("runtime", {})
        if runtime.get("publishes_robot_commands") is True:
            errors.append("runtime.publishes_robot_commands must stay false for listener-only recording")
        return errors

    def save(self, path: Path, config: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.dumps(config), encoding="utf-8")

    def clone(self, config: dict[str, Any]) -> dict[str, Any]:
        return deepcopy(config)
