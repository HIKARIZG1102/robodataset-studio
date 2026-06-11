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
        joint_candidates = [t for t in topics if "JointState" in t.get("type", "") or "joint" in t.get("name", "").lower()]
        joint_topic = next((t["name"] for t in joint_candidates), None)
        action_topic = next((t["name"] for t in topics if "action" in t.get("name", "").lower()), None)
        gripper_topic = next((t["name"] for t in topics if "gripper" in t.get("name", "").lower()), None)
        if not joint_topic:
            joint_topic = "/wx250s/joint_states"

        cameras = []
        streams = []
        used_image_names: set[str] = set()
        static_assigned = False
        for idx, topic in enumerate(image_topics[:4]):
            role, name, static_assigned = self._image_role_and_key(topic["name"], idx, static_assigned)
            name = self._unique_stream_name(name, used_image_names)
            used_image_names.add(name)
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
                "calvin_key": name,
                "required": True,
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
                    "calvin_key": cam["name"],
                    "required": True,
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
            "environment": {
                "type": state.environment,
                "description": "physical WidowX + RealSense scene; external control nodes provide motion and sensor streams",
                "workspace": "robotarm_control_ws",
                "lighting": "unspecified",
                "objects": [],
                "notes": "",
            },
            "robot": {
                "name": "widowx",
                "model": "wx250s",
                "description": "6-dof WidowX arm with gripper",
                "joint_count": 6,
                "joint_order": ["waist", "shoulder", "elbow", "forearm_roll", "wrist_angle", "wrist_rotate"],
                "base_frame": "wx250s/base_link",
                "end_effector_frame": "wx250s/ee_gripper_link",
                "joint_state_topic": joint_topic,
                "action_topic": action_topic,
                "gripper_state_topic": gripper_topic,
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
                        "output_dim": 6,
                        "fields": ["joint_position"],
                        "joint_order": ["waist", "shoulder", "elbow", "forearm_roll", "wrist_angle", "wrist_rotate"],
                    }
                ]
                if joint_topic
                else []
            },
            "action": {
                "name": "rel_actions",
                "source": "derived_from_robot_obs",
                "source_topic": joint_topic,
                "source_action_topic": action_topic,
                "gripper_state_topic": gripper_topic,
                "format": "delta_joint_position_gripper",
                "dim": 7,
                "fields": ["djoint_0", "djoint_1", "djoint_2", "djoint_3", "djoint_4", "djoint_5", "gripper"],
                "default_gripper": 1.0,
            },
            "runtime": {
                "mode": "listener_only",
                "starts_external_nodes": False,
                "publishes_robot_commands": False,
            },
            "dataset": {
                "output_format": ["npz", "hdf5"],
                "npz_schema": "calvin_style",
                "calvin_like_transition_files": True,
                "hdf5_schema": "pi05_calvin_hdf5",
                "cache_root": str(state.raw_session_dir),
                "merged_root": str(state.merged_dir),
                "split": "training",
                "episode_prefix": "episode_",
                "write_language_annotations": True,
                "language_annotation_file": "lang_annotations/auto_lang_ann.npy",
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
        state_keys = config.get("state", {}).get("keys", [])
        if not any(key.get("type") == "sensor_msgs/msg/JointState" and key.get("source_topic") for key in state_keys):
            errors.append("missing required JointState state key for robot_obs")
        runtime = config.get("runtime", {})
        if runtime.get("publishes_robot_commands") is True:
            errors.append("runtime.publishes_robot_commands must stay false for listener-only recording")
        return errors

    def save(self, path: Path, config: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.dumps(config), encoding="utf-8")

    def clone(self, config: dict[str, Any]) -> dict[str, Any]:
        return deepcopy(config)

    def _image_role_and_key(self, topic_name: str, idx: int, static_assigned: bool) -> tuple[str, str, bool]:
        lowered = topic_name.lower()
        if "wrist" in lowered or "hand" in lowered or "ee" in lowered:
            return "wrist", "rgb_wrist", static_assigned
        if "overhead" in lowered or "top" in lowered or "ceiling" in lowered:
            return "overhead", "rgb_overhead", static_assigned
        if not static_assigned:
            return "base", "rgb_static", True
        return "external", f"rgb_{idx}", static_assigned

    def _unique_stream_name(self, name: str, used: set[str]) -> str:
        if name not in used:
            return name
        suffix = 2
        while f"{name}_{suffix}" in used:
            suffix += 1
        return f"{name}_{suffix}"
