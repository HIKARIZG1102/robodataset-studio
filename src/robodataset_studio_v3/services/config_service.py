from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from robodataset_studio_v3.models.config import ConfigPreview, DatasetConfigDraft, ProjectConfigDraft


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


class ConfigService:
    METADATA_EXTENSION_KEYS = [
        "episode_metadata",
        "collection_config",
        "task_info",
        "environment_info",
        "robot_info",
        "stream_schema",
    ]

    def __init__(self, library_root: Path | None = None) -> None:
        self.library_root = library_root or repo_root() / "robodataset" / "configs"

    def default_dataset_config(self) -> dict[str, Any]:
        return {
            "environment": {
                "type": "",
                "workspace": "",
                "scene_description": "",
                "lighting": "",
                "objects": [],
                "notes": "",
            },
            "instruction": {
                "text": "",
                "language": "",
                "task_family": "",
                "success_condition": "",
            },
            "robot": {
                "name": "",
                "model": "",
                "description": "",
                "joint_state_topic": "",
                "joint_count": 0,
                "joint_order": [],
                "base_frame": "",
                "end_effector_frame": "",
                "action_topic": None,
                "gripper_state_topic": None,
            },
            "streams": [],
            "state": {"keys": []},
            "action": {
                "name": "rel_actions",
                "source": "derived_from_robot_obs",
                "source_topic": "",
                "source_action_topic": None,
                "gripper_state_topic": None,
                "format": "delta_state",
                "dim": 0,
                "fields": [],
            },
            "recording": {
                "sample_rate_hz": 10,
                "stop_mode": "manual",
                "episode_duration_sec": 0.0,
                "target_samples": 0,
                "sync_policy": "nearest_timestamp",
                "max_frame_lag_ms": 100,
                "min_episode_steps": 1,
                "auto_drop_empty_frames": True,
                "auto_drop_invalid_actions": True,
            },
            "dataset": {
                "output_format": ["npz", "hdf5"],
                "schema": "calvin_style",
                "split": "training",
                "episode_prefix": "episode_",
                "write_language_annotations": True,
                "language_annotation_file": "lang_annotations/auto_lang_ann.npy",
                "requires_robot_obs": False,
                "requires_actions": False,
                "metadata_extensions": list(self.METADATA_EXTENSION_KEYS),
                "core_schema": {},
                "recording_estimate": {},
            },
            "ai_assist": {
                "config_prompt": "",
                "config_response": "",
                "review_prompt": "",
                "review_response": "",
            },
        }

    def default_project_config(self) -> dict[str, Any]:
        return {
            "config_meta": {
                "id": "",
                "name": "",
                "created_at": "",
                "updated_at": "",
            },
            "paths": {
                "project_root": "",
                "raw_sessions": "raw_sessions",
                "review": "review",
                "exports": "exports",
                "logs": "logs",
            },
            "collection": {
                "default_mode": "manual",
                "preflight_required": True,
                "auto_start_monitor": True,
                "write_session_config_snapshot": True,
            },
            "review": {
                "local_checks_enabled": True,
                "ai_review_enabled": False,
                "marks_file": "review/review_marks.json",
            },
            "convert": {
                "default_output_dir": "exports",
                "write_hdf5": True,
                "merge_selected_sessions": True,
            },
            "upload": {
                "name": "",
                "host": "",
                "lan_host": "",
                "wan_host": "",
                "port": 22,
                "username": "",
                "auth_mode": "password_or_key",
                "key_path": "",
                "use_rsync": True,
                "repair_resume_enabled": True,
                "verify_after_upload": True,
            },
            "ros": {
                "selected_nodes": [],
                "selected_topics": [],
                "discovery_snapshot": [],
            },
            "dataset_config": self.default_dataset_config(),
        }

    def sync_dataset_schema(self, dataset_config: dict[str, Any]) -> dict[str, Any]:
        dataset = dataset_config.setdefault("dataset", {})
        state = dataset_config.get("state", {}) if isinstance(dataset_config.get("state"), dict) else {}
        state_keys = state.get("keys", []) if isinstance(state.get("keys"), list) else []
        action_cfg = dataset_config.get("action", {}) if isinstance(dataset_config.get("action"), dict) else {}
        has_state = bool(state_keys)
        has_action_source = bool(action_cfg.get("source") or action_cfg.get("source_topic") or action_cfg.get("source_state_key"))
        dataset["requires_robot_obs"] = bool(dataset.get("requires_robot_obs", False) or has_state)
        dataset["requires_actions"] = bool(dataset.get("requires_actions", False) or has_action_source or has_state)
        dataset.setdefault("metadata_extensions", list(self.METADATA_EXTENSION_KEYS))
        dataset["core_schema"] = self.build_core_schema(dataset_config)
        dataset["recording_estimate"] = self.recording_estimate(dataset_config)
        return dataset_config

    def build_core_schema(self, dataset_config: dict[str, Any]) -> dict[str, Any]:
        streams = dataset_config.get("streams", []) if isinstance(dataset_config.get("streams"), list) else []
        observations: list[dict[str, Any]] = []
        extension_streams: list[dict[str, Any]] = []
        for stream in streams:
            if not isinstance(stream, dict):
                continue
            name = str(stream.get("name") or stream.get("topic") or "").strip()
            calvin_key = stream.get("calvin_key")
            key = str(calvin_key or "").strip()
            record = {
                "key": key or name,
                "stream_name": name,
                "topic": stream.get("topic", ""),
                "message_type": stream.get("message_type", ""),
                "modality": stream.get("modality", ""),
                "training_role": stream.get("training_role", "observation"),
                "dtype": stream.get("dtype", "auto"),
                "shape": stream.get("shape", ["auto"]),
                "encoding": stream.get("encoding", ""),
                "required": bool(stream.get("required", True)),
            }
            if key:
                observations.append(record)
            elif name:
                extension_streams.append(record)

        state_keys = []
        state = dataset_config.get("state", {}) if isinstance(dataset_config.get("state"), dict) else {}
        for item in state.get("keys", []) if isinstance(state.get("keys"), list) else []:
            if not isinstance(item, dict):
                continue
            state_keys.append(
                {
                    "key": item.get("name", "robot_obs"),
                    "source_topic": item.get("source_topic", ""),
                    "message_type": item.get("type", ""),
                    "dtype": "float32",
                    "dim": item.get("output_dim") or "auto",
                    "fields": item.get("fields", []),
                    "joint_order": item.get("joint_order", []),
                    "required": True,
                }
            )

        action_cfg = dataset_config.get("action", {}) if isinstance(dataset_config.get("action"), dict) else {}
        action_dim = action_cfg.get("dim") or "auto"
        actions = []
        dataset = dataset_config.get("dataset", {}) if isinstance(dataset_config.get("dataset"), dict) else {}
        requires_actions = bool(dataset.get("requires_actions", bool(action_cfg.get("source") or action_cfg.get("source_topic"))))
        if requires_actions:
            action_name = action_cfg.get("name", "rel_actions")
            actions = [
                {
                    "key": action_name,
                    "source": action_cfg.get("source", ""),
                    "source_topic": action_cfg.get("source_topic", ""),
                    "source_state_key": action_cfg.get("source_state_key", ""),
                    "dtype": "float32",
                    "dim": action_dim,
                    "format": action_cfg.get("format", ""),
                    "fields": action_cfg.get("fields", []),
                    "required": True,
                },
                {
                    "key": "actions",
                    "source": action_name,
                    "dtype": "float32",
                    "dim": action_dim,
                    "format": action_cfg.get("format", ""),
                    "required": True,
                },
            ]

        timestamp_keys = [f"{item['key']}_timestamp" for item in [*observations, *extension_streams] if item.get("key")]
        if state_keys:
            timestamp_keys.append("joint_state_timestamp")
        if actions:
            timestamp_keys.append("action_timestamp")
        return {
            "name": "calvin_like_transition_v1",
            "description": "Each episode_*.npz stores one synchronized transition. Core keys are derived from streams/state/action.",
            "core_observation_keys": observations,
            "core_state_keys": state_keys,
            "core_action_keys": actions,
            "optional_core_keys": {
                "timestamps": timestamp_keys,
                "camera_info": [f"camera_info_{item.get('key')}" for item in observations if item.get("message_type") == "sensor_msgs/msg/Image"],
                "episode_metadata": ["episode_metadata"],
            },
            "extension_data_keys": extension_streams,
            "metadata_extension_keys": list(dataset_config.get("dataset", {}).get("metadata_extensions", self.METADATA_EXTENSION_KEYS)),
            "strict_loader_policy": "consume only configured core_observation_keys/core_state_keys/core_action_keys; ignore extension_data_keys and metadata_extension_keys when strict CALVIN compatibility is required",
        }

    def dataset_schema_notes(self, dataset_config: dict[str, Any]) -> str:
        schema = self.build_core_schema(dataset_config)
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
                    "sensor_msgs/msg/JointState topics map to state.keys; one arm usually uses robot_obs, multiple arms use stable robot_obs_* names.",
                    "action.source_state_key selects which state key derives rel_actions/actions; otherwise source_topic or the first captured state key is used.",
                    "Do not invent core state/action keys when no selected JointState/action topic exists.",
                ],
            },
            allow_unicode=True,
            sort_keys=False,
        )

    def recording_estimate(self, dataset_config: dict[str, Any]) -> dict[str, Any]:
        recording = dataset_config.get("recording", {}) if isinstance(dataset_config.get("recording"), dict) else {}
        sample_rate = float(recording.get("sample_rate_hz") or 10)
        stop_mode = str(recording.get("stop_mode") or "manual")
        duration = float(recording.get("episode_duration_sec") or 0)
        target_samples = int(recording.get("target_samples") or 0)
        if stop_mode == "sample_count" and target_samples > 0:
            synchronized_samples = target_samples
        elif duration > 0:
            synchronized_samples = int(round(sample_rate * duration))
        else:
            synchronized_samples = 0
        action_cfg = dataset_config.get("action", {}) if isinstance(dataset_config.get("action"), dict) else {}
        dataset = dataset_config.get("dataset", {}) if isinstance(dataset_config.get("dataset"), dict) else {}
        has_actions = bool(dataset.get("requires_actions", bool(action_cfg.get("source") or action_cfg.get("source_topic"))))
        transition_files = max(synchronized_samples - 1, 0) if has_actions and synchronized_samples else synchronized_samples
        return {
            "sample_rate_hz": sample_rate,
            "stop_mode": stop_mode,
            "estimated_synchronized_samples": synchronized_samples,
            "estimated_transition_files": transition_files,
            "note": "0 means manual or open-ended recording; actual count is decided when collection stops.",
        }

    def write_default_configs(self, project_dir: Path) -> None:
        project_config = self.default_project_config()
        self.sync_dataset_schema(project_config["dataset_config"])
        dataset_config = self._dataset_only(project_config["dataset_config"])
        self.write_yaml(project_dir / "project_config.yaml", project_config)
        self.write_yaml(project_dir / "dataset_config.yaml", dataset_config)

    def ensure_default_library_config(self) -> dict[str, Any]:
        self.library_root.mkdir(parents=True, exist_ok=True)
        config_id = "default_calvin"
        path = self.config_path(config_id)
        if not path.exists():
            payload = self.default_project_config()
            self.sync_dataset_schema(payload["dataset_config"])
            payload.setdefault("config_meta", {})
            payload["config_meta"].update(
                {
                    "id": config_id,
                    "name": "Default CALVIN config",
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                    "note": "Reusable total config. Project name/version are stored only in project.yaml.",
                }
            )
            self.write_yaml(path, payload)
        return self.config_summary(config_id, path)

    def list_library_configs(self) -> list[dict[str, Any]]:
        self.ensure_default_library_config()
        configs = []
        for path in sorted(self.library_root.glob("*.yaml")):
            configs.append(self.config_summary(path.stem, path))
        return configs

    def config_path(self, config_id: str) -> Path:
        safe_id = self._safe_id(config_id or "default_calvin")
        return self.library_root / f"{safe_id}.yaml"

    def config_summary(self, config_id: str, path: Path | None = None) -> dict[str, Any]:
        path = path or self.config_path(config_id)
        payload = self.read_yaml(path)
        meta = payload.get("config_meta", {}) if isinstance(payload.get("config_meta"), dict) else {}
        dataset = payload.get("dataset_config", {}) if isinstance(payload.get("dataset_config"), dict) else {}
        streams = dataset.get("streams", []) if isinstance(dataset, dict) else []
        return {
            "id": self._safe_id(str(meta.get("id") or config_id or path.stem)),
            "name": str(meta.get("name") or path.stem),
            "path": str(path),
            "updated_at": str(meta.get("updated_at") or ""),
            "stream_count": len(streams) if isinstance(streams, list) else 0,
        }

    def read_library_config(self, config_id: str) -> dict[str, Any]:
        path = self.config_path(config_id)
        if not path.exists():
            raise FileNotFoundError(f"config not found: {config_id}")
        payload = self.read_yaml(path)
        if isinstance(payload.get("dataset_config"), dict):
            self.sync_dataset_schema(payload["dataset_config"])
        return payload if payload else self.default_project_config()

    def create_library_config(self, name: str = "", source_config_id: str = "") -> dict[str, Any]:
        self.library_root.mkdir(parents=True, exist_ok=True)
        base = self.read_library_config(source_config_id) if source_config_id else self.default_project_config()
        display_name = name.strip() or "new_config"
        config_id = self._safe_id(display_name)
        candidate = config_id
        suffix = 2
        while self.config_path(candidate).exists():
            candidate = f"{config_id}_{suffix}"
            suffix += 1
        now = datetime.now().isoformat(timespec="seconds")
        payload = dict(base)
        payload.setdefault("config_meta", {})
        payload["config_meta"].update({"id": candidate, "name": display_name, "created_at": now, "updated_at": now})
        if isinstance(payload.get("dataset_config"), dict):
            self.sync_dataset_schema(payload["dataset_config"])
        self.write_yaml(self.config_path(candidate), payload)
        return self.config_summary(candidate)

    def duplicate_library_config(self, config_id: str, name: str = "") -> dict[str, Any]:
        source = self.read_library_config(config_id)
        source_name = str(source.get("config_meta", {}).get("name") or config_id) if isinstance(source.get("config_meta"), dict) else config_id
        copy_name = name.strip() or f"{source_name}_copy"
        return self.create_library_config(copy_name, config_id)

    def rename_library_config(self, config_id: str, new_name: str) -> dict[str, Any]:
        old_id = self._safe_id(config_id)
        new_id = self._safe_id(new_name)
        if not new_name.strip():
            raise ValueError("new config name is empty")
        old_path = self.config_path(old_id)
        new_path = self.config_path(new_id)
        if not old_path.exists():
            raise FileNotFoundError(f"config not found: {config_id}")
        if new_path.exists() and new_id != old_id:
            raise FileExistsError(f"config already exists: {new_id}")
        payload = self.read_yaml(old_path)
        payload.setdefault("config_meta", {})
        payload["config_meta"].update(
            {
                "id": new_id,
                "name": new_name.strip(),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        if isinstance(payload.get("dataset_config"), dict):
            self.sync_dataset_schema(payload["dataset_config"])
        self.write_yaml(new_path, payload)
        if new_path != old_path:
            old_path.unlink()
        return self.config_summary(new_id)

    def delete_library_config(self, config_id: str) -> dict[str, Any]:
        safe_id = self._safe_id(config_id)
        if safe_id == "default_calvin":
            raise ValueError("default_calvin cannot be deleted")
        path = self.config_path(safe_id)
        if not path.exists():
            raise FileNotFoundError(f"config not found: {config_id}")
        path.unlink()
        return {"status": "deleted", "id": safe_id}

    def save_library_config(self, config_id: str, config: dict[str, Any]) -> dict[str, Any]:
        safe_id = self._safe_id(config_id)
        payload = dict(config or {})
        if isinstance(payload.get("upload"), dict):
            payload["upload"].pop("password", None)
        if isinstance(payload.get("dataset_config"), dict):
            self.sync_dataset_schema(payload["dataset_config"])
        payload.setdefault("config_meta", {})
        payload["config_meta"]["id"] = safe_id
        payload["config_meta"].setdefault("name", safe_id)
        payload["config_meta"]["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self.library_root.mkdir(parents=True, exist_ok=True)
        self.write_yaml(self.config_path(safe_id), payload)
        return self.config_summary(safe_id)

    def apply_library_config_to_project(self, project_dir: Path, config_id: str) -> dict[str, Any]:
        payload = self.read_library_config(config_id)
        project_config = dict(payload)
        if isinstance(project_config.get("upload"), dict):
            project_config["upload"].pop("password", None)
        dataset_config = project_config.get("dataset_config", {})
        if not isinstance(dataset_config, dict):
            dataset_config = {}
        self.sync_dataset_schema(dataset_config)
        project_config["dataset_config"] = self._dataset_only(dataset_config)
        self.write_yaml(project_dir / "project_config.yaml", project_config)
        self.write_yaml(project_dir / "dataset_config.yaml", project_config["dataset_config"])
        return project_config

    def read_project_config(self, project_dir: Path) -> dict[str, Any]:
        payload = self.read_yaml(project_dir / "project_config.yaml")
        if isinstance(payload.get("dataset_config"), dict):
            self.sync_dataset_schema(payload["dataset_config"])
        return payload

    def read_dataset_config(self, project_dir: Path) -> dict[str, Any]:
        dataset_path = project_dir / "dataset_config.yaml"
        if dataset_path.exists():
            dataset_config = self.read_yaml(dataset_path)
            self.sync_dataset_schema(dataset_config)
            return dataset_config
        project_config = self.read_project_config(project_dir)
        dataset_config = project_config.get("dataset_config", {})
        return self._dataset_only(dataset_config) if isinstance(dataset_config, dict) else {}

    def write_project_config(self, project_dir: Path, config: ProjectConfigDraft) -> None:
        payload = config.model_dump()
        if isinstance(payload.get("upload"), dict):
            payload["upload"].pop("password", None)
        dataset_config = payload.get("dataset_config", {})
        if not isinstance(dataset_config, dict):
            dataset_config = {}
        self.sync_dataset_schema(dataset_config)
        payload["dataset_config"] = self._dataset_only(dataset_config)
        self.write_yaml(project_dir / "project_config.yaml", payload)
        self.write_yaml(project_dir / "dataset_config.yaml", payload.get("dataset_config", {}))

    def write_yaml(self, path: Path, payload: dict[str, Any]) -> None:
        path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")

    def read_yaml(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}

    def _dataset_only(self, dataset_config: dict[str, Any]) -> dict[str, Any]:
        dataset = dict(dataset_config or {})
        dataset.pop("ros", None)
        self.sync_dataset_schema(dataset)
        return dataset

    def _safe_id(self, value: str) -> str:
        text = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value.strip())
        return text.strip("_-") or "default_calvin"

    def preview_project(self, config: ProjectConfigDraft | dict[str, Any]) -> ConfigPreview:
        if isinstance(config, dict):
            config = ProjectConfigDraft.model_validate(config)
        dataset = config.dataset_config
        stream_count = len(dataset.streams)
        image_count = sum(1 for stream in dataset.streams if "Image" in str(stream.get("message_type", "")))
        summary = (
            "project_config "
            f"streams={stream_count} image_streams={image_count} "
            f"upload_host={config.upload.get('host', '')}"
        )
        warnings = []
        if not dataset.streams:
            warnings.append("no streams selected")
        if config.upload and not config.upload.get("host"):
            warnings.append("upload.host is empty")
        return ConfigPreview(summary=summary, warnings=warnings, dataset_summary=self._dataset_summary(dataset))

    def preview_dataset(self, config: DatasetConfigDraft | dict[str, Any]) -> ConfigPreview:
        if isinstance(config, dict):
            config = DatasetConfigDraft.model_validate(config)
        warnings = []
        if not config.streams:
            warnings.append("no streams selected")
        return ConfigPreview(summary=self._dataset_summary(config), warnings=warnings)

    def _dataset_summary(self, config: DatasetConfigDraft) -> str:
        stream_count = len(config.streams)
        image_count = sum(1 for stream in config.streams if "Image" in str(stream.get("message_type", "")))
        state_keys = config.state.get("keys", []) if isinstance(config.state, dict) else []
        state_count = len(state_keys) if isinstance(state_keys, list) else 0
        sample_rate = config.recording.get("sample_rate_hz", "")
        return (
            f"dataset_config streams={stream_count} image_streams={image_count} "
            f"state_keys={state_count} sample_rate_hz={sample_rate}"
        )
