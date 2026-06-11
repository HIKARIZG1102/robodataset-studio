from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .models import ProjectState


class ConfigManager:
    METADATA_EXTENSION_KEYS = [
        "episode_metadata",
        "collection_config",
        "task_info",
        "environment_info",
        "robot_info",
        "stream_schema",
    ]

    def build_default_config(self, state: ProjectState, topics: list[dict[str, str]] | None = None) -> dict[str, Any]:
        topics = topics or []
        image_topics = [t for t in topics if "Image" in t.get("type", "") or "image" in t.get("name", "").lower()]
        joint_candidates = [t for t in topics if self._is_joint_state_topic(t)]
        joint_topic = next((t["name"] for t in joint_candidates), None)
        action_topic = next((t["name"] for t in topics if "action" in t.get("name", "").lower()), None)
        gripper_topic = next((t["name"] for t in topics if "gripper" in t.get("name", "").lower()), None)
        cameras = []
        streams = []
        used_image_names: set[str] = set()
        static_assigned = False
        for idx, topic in enumerate(image_topics):
            role, name, modality, encoding, shape, static_assigned = self._image_role_and_key(topic["name"], idx, static_assigned)
            name = self._unique_stream_name(name, used_image_names)
            used_image_names.add(name)
            camera = {
                "name": name,
                "role": role,
                "topic": topic["name"],
                "type": topic.get("type", "sensor_msgs/msg/Image"),
                "encoding": encoding,
                "fps_target": 10,
                "crop": {"enabled": False, "x": 0, "y": 0, "width": 640, "height": 480},
                "resize": {"enabled": modality == "rgb", "width": 224, "height": 224},
            }
            cameras.append(camera)
            streams.append({
                "name": name,
                "modality": modality,
                "source": "ros2_topic",
                "topic": topic["name"],
                "message_type": camera["type"],
                "dtype": "uint16" if modality == "depth" else "uint8",
                "shape": shape,
                "encoding": encoding,
                "training_role": "observation",
                "calvin_key": name if modality == "rgb" else None,
                "required": True,
                "preview": {"renderer": "image_depth" if modality == "depth" else "image_rgb"},
            })

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
                "description": "",
                "workspace": "",
                "lighting": "",
                "objects": [],
                "notes": "",
            },
            "robot": {
                "name": "",
                "model": "",
                "description": "",
                "joint_count": 0,
                "joint_order": [],
                "base_frame": "",
                "end_effector_frame": "",
                "joint_state_topic": joint_topic,
                "action_topic": action_topic,
                "gripper_state_topic": gripper_topic,
                "control": {
                    "enabled": False,
                    "mode": "external_controller_only",
                    "publishes_commands": False,
                },
                "action_format": {
                    "type": "delta_state",
                    "dim": 0,
                    "fields": [],
                    "gripper_convention": {},
                },
            },
            "instruction": {
                "text": "",
                "language": "",
                "task_family": "",
                "success_condition": "",
            },
            "cameras": cameras,
            "streams": streams,
            "state": {"keys": self._state_keys(joint_topic)},
            "action": {
                "name": "rel_actions",
                "source": "derived_from_robot_obs" if joint_topic else "not_configured",
                "source_topic": joint_topic,
                "source_action_topic": action_topic,
                "gripper_state_topic": gripper_topic,
                "format": "delta_state",
                "dim": 0,
                "fields": [],
                "include_default_gripper": False,
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
                "requires_robot_obs": bool(joint_topic),
                "requires_actions": bool(joint_topic),
                "cache_root": str(state.raw_session_dir),
                "merged_root": str(state.merged_dir),
                "split": "training",
                "episode_prefix": "episode_",
                "write_language_annotations": True,
                "language_annotation_file": "lang_annotations/auto_lang_ann.npy",
                "core_schema": {},
            },
            "recording": {
                "sample_rate_hz": 10,
                "stop_mode": "duration_sec",
                "episode_duration_sec": 2.0,
                "target_samples": 20,
                "sync_policy": "nearest_timestamp",
                "max_frame_lag_ms": 100,
                "min_episode_steps": 5,
                "auto_drop_empty_frames": True,
                "auto_drop_invalid_actions": True,
            },
        }
        self.sync_core_schema(config)
        return config

    def dumps(self, config: dict[str, Any]) -> str:
        return yaml.safe_dump(config, allow_unicode=True, sort_keys=False)

    def loads(self, text: str) -> dict[str, Any]:
        loaded = yaml.safe_load(text)
        if isinstance(loaded, dict):
            loaded.pop("ai_validation", None)
            return loaded
        return {}

    def validate(self, config: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        for key in ["project", "robot", "instruction", "dataset", "recording"]:
            if key not in config:
                errors.append(f"missing required section: {key}")
        if not config.get("cameras") and not config.get("streams"):
            errors.append("missing cameras or streams")
        dataset = config.get("dataset", {})
        if dataset.get("requires_robot_obs", False):
            state_keys = config.get("state", {}).get("keys", [])
            if not isinstance(state_keys, list):
                errors.append("state.keys must be a list")
                state_keys = []
            malformed = [idx for idx, key in enumerate(state_keys) if not isinstance(key, dict)]
            if malformed:
                errors.append("state.keys entries must be mappings")
            valid_state_keys = [key for key in state_keys if isinstance(key, dict)]
            if not any(key.get("type") == "sensor_msgs/msg/JointState" and key.get("source_topic") for key in valid_state_keys):
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

    def sync_core_schema(self, config: dict[str, Any]) -> dict[str, Any]:
        dataset = config.setdefault("dataset", {})
        dataset["core_schema"] = self.build_core_schema(config)
        return config

    def build_core_schema(self, config: dict[str, Any]) -> dict[str, Any]:
        dataset = config.get("dataset", {})
        streams = config.get("streams", [])
        observations: list[dict[str, Any]] = []
        extension_streams: list[dict[str, Any]] = []
        if isinstance(streams, list):
            for stream in streams:
                if not isinstance(stream, dict):
                    continue
                key = str(stream.get("calvin_key") or "").strip()
                stream_name = str(stream.get("name") or stream.get("topic") or "").strip()
                record = {
                    "key": key or stream_name,
                    "stream_name": stream_name,
                    "topic": stream.get("topic", ""),
                    "message_type": stream.get("message_type", ""),
                    "modality": stream.get("modality", ""),
                    "role": stream.get("training_role", "observation"),
                    "dtype": stream.get("dtype", "auto"),
                    "shape": stream.get("shape", ["auto"]),
                    "required": bool(stream.get("required", True)),
                }
                if key:
                    observations.append(record)
                elif stream_name:
                    extension_streams.append(record)
        state_keys = []
        raw_state_keys = config.get("state", {}).get("keys", [])
        if isinstance(raw_state_keys, list):
            for state_key in raw_state_keys:
                if not isinstance(state_key, dict):
                    continue
                state_keys.append(
                    {
                        "key": state_key.get("name", "robot_obs"),
                        "source_topic": state_key.get("source_topic", ""),
                        "message_type": state_key.get("type", ""),
                        "dtype": "float32",
                        "dim": state_key.get("output_dim") or "auto",
                        "fields": state_key.get("fields", []),
                        "joint_order": state_key.get("joint_order", []),
                        "required": bool(dataset.get("requires_robot_obs", False)),
                    }
                )
        action_cfg = config.get("action", {}) if isinstance(config.get("action", {}), dict) else {}
        action_dim = action_cfg.get("dim") or "auto"
        actions = []
        if dataset.get("requires_actions", False):
            actions = [
                {
                    "key": action_cfg.get("name", "rel_actions"),
                    "source": action_cfg.get("source", ""),
                    "source_topic": action_cfg.get("source_topic", ""),
                    "dtype": "float32",
                    "dim": action_dim,
                    "format": action_cfg.get("format", ""),
                    "fields": action_cfg.get("fields", []),
                    "required": True,
                },
                {
                    "key": "actions",
                    "source": action_cfg.get("name", "rel_actions"),
                    "dtype": "float32",
                    "dim": action_dim,
                    "format": action_cfg.get("format", ""),
                    "required": True,
                },
            ]
        timestamp_keys = []
        for item in [*observations, *extension_streams]:
            key = item.get("key")
            if key:
                timestamp_keys.append(f"{key}_timestamp")
        if state_keys:
            timestamp_keys.append("joint_state_timestamp")
        if actions:
            timestamp_keys.append("action_timestamp")
        return {
            "name": "calvin_like_transition_v1",
            "description": "Each episode_*.npz is one synchronized transition. Core keys are configurable through streams/state/action.",
            "core_observation_keys": observations,
            "core_state_keys": state_keys,
            "core_action_keys": actions,
            "optional_core_keys": {
                "timestamps": timestamp_keys,
                "camera_info": [f"camera_info_{item.get('key')}" for item in observations if item.get("message_type") == "sensor_msgs/msg/Image"],
                "episode_metadata": ["episode_metadata"],
            },
            "extension_data_keys": extension_streams,
            "metadata_extension_keys": list(self.METADATA_EXTENSION_KEYS),
            "strict_loader_policy": "consume only configured core_observation_keys/core_state_keys/core_action_keys; ignore or strip extension_data_keys and metadata_extension_keys",
        }

    def dataset_schema_notes(self, config: dict[str, Any]) -> str:
        schema = self.build_core_schema(config)
        return yaml.safe_dump(
            {
                "calvin_core_keys": {
                    "observations": schema["core_observation_keys"],
                    "state": schema["core_state_keys"],
                    "actions": schema["core_action_keys"],
                },
                "extensible_optional_keys": schema["optional_core_keys"],
                "non_core_extensions": {
                    "data_streams": schema["extension_data_keys"],
                    "metadata": schema["metadata_extension_keys"],
                },
                "matching_rules": [
                    "sensor_msgs/msg/Image color/rgb topics with wrist/hand/ee names map to rgb_wrist unless already used.",
                    "sensor_msgs/msg/Image color/rgb topics with overhead/top/ceiling names map to rgb_overhead.",
                    "first other color/rgb image topic maps to rgb_static; additional RGB topics map to rgb_1, rgb_2, etc.",
                    "depth image topics map to depth_* extension streams with calvin_key null unless the user explicitly promotes them.",
                    "sensor_msgs/msg/JointState topics map to robot_obs and define robot.joint_count, state.output_dim, joint_order when echo data reveals joint names.",
                    "rel_actions/actions dimensions should follow config.action.dim or the robot_obs output_dim plus configured gripper convention.",
                    "Do not invent core state/action keys when no selected JointState/action topic exists.",
                ],
            },
            allow_unicode=True,
            sort_keys=False,
        )

    def _state_keys(self, joint_topic: str | None) -> list[dict[str, Any]]:
        if not joint_topic:
            return []
        return [
            {
                "name": "robot_obs",
                "source_topic": joint_topic,
                "type": "sensor_msgs/msg/JointState",
                "output_dim": 0,
                "fields": ["joint_position"],
                "joint_order": [],
            }
        ]

    def _is_joint_state_topic(self, topic: dict[str, str]) -> bool:
        typ = topic.get("type", "")
        name = topic.get("name", "").lower()
        if typ == "sensor_msgs/msg/JointState" or typ.endswith("/JointState"):
            return True
        return name.endswith("/joint_states") or name == "/joint_states"

    def dataset_structure_preview(self, config: dict[str, Any]) -> str:
        schema = self.build_core_schema(config)
        recording = config.get("recording", {})
        sample_rate = float(recording.get("sample_rate_hz") or 10)
        stop_mode = str(recording.get("stop_mode") or "duration_sec")
        min_steps = int(recording.get("min_episode_steps") or 1)
        requires_actions = bool(config.get("dataset", {}).get("requires_actions", False))
        minimum_samples = max(min_steps, 2 if requires_actions else 1)
        if stop_mode == "sample_count":
            requested_samples = int(recording.get("target_samples") or 0)
            sample_count = max(requested_samples, minimum_samples) if requested_samples > 0 else 0
            estimate = f"recording target: {sample_count} synchronized samples"
        else:
            duration = float(recording.get("episode_duration_sec") or 0)
            requested_samples = int(round(sample_rate * duration)) if duration > 0 else 0
            sample_count = max(requested_samples, minimum_samples) if duration > 0 else 0
            estimate = f"recording target: {duration:g}s x {sample_rate:g}Hz ~= {sample_count} synchronized samples"
        if requires_actions and sample_count > 0:
            estimate += f", about {max(sample_count - 1, 0)} transition files"
        lines = [
            "collection_config.yaml",
            estimate,
            "schema source: dataset.core_schema generated from current YAML",
            f"{config.get('dataset', {}).get('split', 'training')}/",
            "  episode_0000000.npz",
            "    CALVIN-compatible core fields:",
        ]
        raw_streams = config.get("streams", [])
        if isinstance(raw_streams, list):
            for stream in raw_streams:
                if not isinstance(stream, dict):
                    lines.append(f"      malformed stream entry: {type(stream).__name__}")
        for item in schema["core_observation_keys"]:
            key = item.get("key")
            if not key:
                continue
            shape = item.get("shape") or ["auto"]
            shape_text = "x".join(str(part) for part in shape)
            dtype = item.get("dtype", "auto")
            topic = item.get("topic", "")
            lines.append(f"      {key}: {shape_text} {dtype} <- {topic}")
        state_keys = config.get("state", {}).get("keys", [])
        if not isinstance(state_keys, list):
            state_keys = []
        for state_key in state_keys:
            if not isinstance(state_key, dict):
                lines.append(f"      malformed state key entry: {type(state_key).__name__}")
        for item in schema["core_state_keys"]:
            lines.append(f"      {item.get('key', 'robot_obs')}: ({item.get('dim', 'auto')},) float32 <- {item.get('source_topic', '')}")
        for item in schema["core_action_keys"]:
            lines.append(f"      {item.get('key')}: ({item.get('dim', 'auto')},) float32")
        extension_streams = schema.get("extension_data_keys", [])
        if extension_streams:
            lines.append("    Configured non-core extension data fields:")
            for item in extension_streams:
                shape = item.get("shape") or ["auto"]
                shape_text = "x".join(str(part) for part in shape)
                lines.append(f"      {item.get('key')}: {shape_text} {item.get('dtype', 'auto')} <- {item.get('topic', '')}")
        optional_keys = schema.get("optional_core_keys", {})
        optional_flat = []
        if isinstance(optional_keys, dict):
            for values in optional_keys.values():
                if isinstance(values, list):
                    optional_flat.extend(str(value) for value in values if value)
        if optional_flat:
            lines.append("    Optional configurable CALVIN-like keys:")
            for key in optional_flat:
                lines.append(f"      {key}")
        lines.extend(
            [
                "    RoboDataset metadata extensions:",
                *[f"      {key}: json scalar" for key in schema["metadata_extension_keys"]],
            ]
        )
        if config.get("dataset", {}).get("write_language_annotations", True):
            ann = config.get("dataset", {}).get("language_annotation_file", "lang_annotations/auto_lang_ann.npy")
            lines.append(f"  {ann}")
        lines.extend(
            [
                "  session_metadata.json",
                "compatibility:",
                "  CALVIN loaders should consume only configured core keys.",
                "  Metadata extension keys are optional sidecar fields and may be ignored or stripped for strict CALVIN loaders.",
            ]
        )
        return "\n".join(lines)

    def _image_role_and_key(self, topic_name: str, idx: int, static_assigned: bool) -> tuple[str, str, str, str, list[int], bool]:
        lowered = topic_name.lower()
        if "depth" in lowered:
            name = "depth_wrist" if "wrist" in lowered else "depth_static" if not static_assigned else f"depth_{idx}"
            role = "wrist" if "wrist" in lowered else "base" if not static_assigned else "external"
            return role, name, "depth", "16UC1", [480, 640], static_assigned
        if "wrist" in lowered or "hand" in lowered or "ee" in lowered:
            return "wrist", "rgb_wrist", "rgb", "rgb8", [480, 640, 3], static_assigned
        if "overhead" in lowered or "top" in lowered or "ceiling" in lowered:
            return "overhead", "rgb_overhead", "rgb", "rgb8", [480, 640, 3], static_assigned
        if not static_assigned:
            return "base", "rgb_static", "rgb", "rgb8", [480, 640, 3], True
        return "external", f"rgb_{idx}", "rgb", "rgb8", [480, 640, 3], static_assigned

    def _unique_stream_name(self, name: str, used: set[str]) -> str:
        if name not in used:
            return name
        suffix = 2
        while f"{name}_{suffix}" in used:
            suffix += 1
        return f"{name}_{suffix}"
