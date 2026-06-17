from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from robodataset_studio_v3.models.config import ConfigPreview, DatasetConfigDraft, ProjectConfigDraft


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


class ConfigService:
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
            "ros": {
                "selected_nodes": [],
                "selected_topics": [],
                "discovery_snapshot": [],
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
                "metadata_extensions": [
                    "collection_config",
                    "task_info",
                    "environment_info",
                    "robot_info",
                    "stream_schema",
                ],
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
                "enabled": False,
                "profile_name": "",
                "host": "",
                "lan_host": "",
                "wan_host": "",
                "port": 22,
                "username": "",
                "auth_mode": "password_or_key",
                "key_path": "",
                "remote_root": "",
                "use_rsync": True,
                "repair_resume_enabled": True,
                "verify_after_upload": True,
            },
            "dataset_config": self.default_dataset_config(),
        }

    def write_default_configs(self, project_dir: Path) -> None:
        project_config = self.default_project_config()
        dataset_config = project_config["dataset_config"]
        self.write_yaml(project_dir / "project_config.yaml", project_config)
        self.write_yaml(project_dir / "dataset_config.yaml", dataset_config)

    def ensure_default_library_config(self) -> dict[str, Any]:
        self.library_root.mkdir(parents=True, exist_ok=True)
        config_id = "default_calvin"
        path = self.config_path(config_id)
        if not path.exists():
            payload = self.default_project_config()
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
        self.write_yaml(self.config_path(candidate), payload)
        return self.config_summary(candidate)

    def duplicate_library_config(self, config_id: str, name: str = "") -> dict[str, Any]:
        source = self.read_library_config(config_id)
        source_name = str(source.get("config_meta", {}).get("name") or config_id) if isinstance(source.get("config_meta"), dict) else config_id
        return self.create_library_config(name.strip() or f"{source_name}_copy", config_id)

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
        dataset_config = project_config.get("dataset_config", {})
        if not isinstance(dataset_config, dict):
            dataset_config = {}
        self.write_yaml(project_dir / "project_config.yaml", project_config)
        self.write_yaml(project_dir / "dataset_config.yaml", dataset_config)
        return project_config

    def read_project_config(self, project_dir: Path) -> dict[str, Any]:
        return self.read_yaml(project_dir / "project_config.yaml")

    def read_dataset_config(self, project_dir: Path) -> dict[str, Any]:
        dataset_path = project_dir / "dataset_config.yaml"
        if dataset_path.exists():
            return self.read_yaml(dataset_path)
        project_config = self.read_project_config(project_dir)
        dataset_config = project_config.get("dataset_config", {})
        return dataset_config if isinstance(dataset_config, dict) else {}

    def write_project_config(self, project_dir: Path, config: ProjectConfigDraft) -> None:
        payload = config.model_dump()
        self.write_yaml(project_dir / "project_config.yaml", payload)
        self.write_yaml(project_dir / "dataset_config.yaml", payload.get("dataset_config", {}))

    def write_yaml(self, path: Path, payload: dict[str, Any]) -> None:
        path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")

    def read_yaml(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}

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
        if config.upload.get("enabled") and not config.upload.get("host"):
            warnings.append("upload.enabled is true but upload.host is empty")
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
