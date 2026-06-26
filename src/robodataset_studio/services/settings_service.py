from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class SettingsService:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path.home() / ".config" / "robodataset-studio" / "settings.yaml"

    def default_settings(self) -> dict[str, Any]:
        return {
            "language": "en",
            "recent_projects": [],
            "ai": {
                "enabled": False,
                "base_url": "",
                "api_key": "",
                "model": "",
                "timeout_sec": 90,
                "prompt_char_budget": 120000,
                "probe_stdout_budget": 12000,
            },
            "ui": {"last_active_tab": "", "inspector_visible": True, "last_project_path": ""},
        }

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            return self.default_settings()
        data = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return self.default_settings()
        settings = self.default_settings()
        settings.update(data)
        settings.pop("server_profiles", None)
        if isinstance(data.get("ai"), dict):
            settings["ai"].update(data["ai"])
        if isinstance(data.get("ui"), dict):
            settings["ui"].update(data["ui"])
        return settings

    def write(self, settings: dict[str, Any]) -> dict[str, Any]:
        settings = dict(settings or {})
        settings.pop("server_profiles", None)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(yaml.safe_dump(settings, sort_keys=False, allow_unicode=True), encoding="utf-8")
        return settings


settings_service = SettingsService()
