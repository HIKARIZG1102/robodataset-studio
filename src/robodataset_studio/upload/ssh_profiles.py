from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class SshProfile:
    name: str
    lan_host: str = ""
    wan_host: str = ""
    port: int = 22
    username: str = ""
    key_path: str = ""
    remote_path: str = "/data/dataset"


class SshProfileStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or Path(__file__).resolve().parents[3] / "config_library" / "ssh_profiles.json"

    def list_profiles(self) -> list[SshProfile]:
        data = self._load_data()
        profiles = []
        for raw in data.get("profiles", []):
            if isinstance(raw, dict):
                profiles.append(self._profile_from_dict(raw))
        return sorted(profiles, key=lambda profile: profile.name.lower())

    def save_profile(self, profile: SshProfile) -> None:
        profile.name = self._safe_name(profile.name)
        profiles = {item.name: item for item in self.list_profiles()}
        profiles[profile.name] = profile
        self._write_profiles(profiles.values())

    def load_profile(self, name: str) -> SshProfile:
        safe_name = self._safe_name(name)
        for profile in self.list_profiles():
            if profile.name == safe_name:
                return profile
        raise KeyError(f"SSH profile not found: {safe_name}")

    def delete_profile(self, name: str) -> None:
        safe_name = self._safe_name(name)
        profiles = [profile for profile in self.list_profiles() if profile.name != safe_name]
        self._write_profiles(profiles)

    def _load_data(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"profiles": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"profiles": []}
        return data if isinstance(data, dict) else {"profiles": []}

    def _write_profiles(self, profiles: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"profiles": [asdict(profile) for profile in profiles]}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _profile_from_dict(self, data: dict[str, Any]) -> SshProfile:
        return SshProfile(
            name=self._safe_name(str(data.get("name", ""))),
            lan_host=str(data.get("lan_host", "")),
            wan_host=str(data.get("wan_host", "")),
            port=int(data.get("port", 22) or 22),
            username=str(data.get("username", "")),
            key_path=str(data.get("key_path", "")),
            remote_path=str(data.get("remote_path", "/data/dataset") or "/data/dataset"),
        )

    def _safe_name(self, name: str) -> str:
        text = name.strip()
        if not text:
            raise ValueError("SSH profile name is required")
        return text
