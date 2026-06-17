from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


class SettingsService:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path.home() / ".config" / "robodataset-studio-v3" / "settings.yaml"

    def default_settings(self) -> dict[str, Any]:
        return {
            "language": "en",
            "recent_projects": [],
            "ai": {"enabled": False, "base_url": "", "api_key": "", "model": "", "timeout_sec": 90},
            "server_profiles": [],
            "ui": {"last_active_tab": "", "inspector_visible": True, "last_project_path": ""},
        }

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._with_v2_ai_defaults(self.default_settings())
        data = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return self._with_v2_ai_defaults(self.default_settings())
        settings = self.default_settings()
        settings.update(data)
        if isinstance(data.get("ai"), dict):
            settings["ai"].update(data["ai"])
        if isinstance(data.get("ui"), dict):
            settings["ui"].update(data["ui"])
        return self._with_v2_ai_defaults(settings)

    def write(self, settings: dict[str, Any]) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(yaml.safe_dump(settings, sort_keys=False, allow_unicode=True), encoding="utf-8")
        return settings

    def _with_v2_ai_defaults(self, settings: dict[str, Any]) -> dict[str, Any]:
        ai = settings.setdefault("ai", {})
        if not isinstance(ai, dict):
            ai = {}
            settings["ai"] = ai
        if ai.get("base_url") or ai.get("model") or ai.get("api_key"):
            return settings
        v2_path = Path.home() / ".config" / "robodataset-studio" / "settings.json"
        if not v2_path.exists():
            return settings
        try:
            payload = json.loads(v2_path.read_text(encoding="utf-8"))
        except Exception:
            return settings
        v2_ai = payload.get("ai", {}) if isinstance(payload, dict) and isinstance(payload.get("ai"), dict) else {}
        for key in ["enabled", "base_url", "api_key", "model"]:
            if v2_ai.get(key) not in (None, ""):
                ai[key] = v2_ai[key]
        ai.setdefault("timeout_sec", 90)
        return settings


settings_service = SettingsService()
