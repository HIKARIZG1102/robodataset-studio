from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from robodataset_studio_v3.models.config import ConfigPreview, DatasetConfigDraft, ProjectConfigDraft


class ConfigService:
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
            "dataset_config": self.default_dataset_config(),
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
                "port": 22,
                "username": "",
                "auth_mode": "password_or_key",
                "remote_root": "",
                "use_rsync": True,
                "repair_resume_enabled": True,
                "verify_after_upload": True,
            },
            "ui_state": {
                "last_active_tab": "Collect",
                "inspector_visible": True,
                "inspector_width": 360,
            },
        }

    def write_default_configs(self, project_dir: Path) -> None:
        project_config = self.default_project_config()
        dataset_config = project_config["dataset_config"]
        self.write_yaml(project_dir / "project_config.yaml", project_config)
        self.write_yaml(project_dir / "dataset_config.yaml", dataset_config)

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
