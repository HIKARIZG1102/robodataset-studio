from __future__ import annotations

from pathlib import Path


class ConfigLibrary:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[3] / "config_library"

    def list_configs(self) -> list[Path]:
        self.root.mkdir(parents=True, exist_ok=True)
        return sorted([*self.root.glob("*.yaml"), *self.root.glob("*.yml")])

    def path_for(self, name: str) -> Path:
        stem = self._safe_stem(name)
        return self.root / f"{stem}.yaml"

    def save_text(self, name: str, text: str) -> Path:
        path = self.path_for(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def load_text(self, name: str) -> str:
        return self.path_for(name).read_text(encoding="utf-8")

    def delete(self, name: str) -> Path:
        path = self.path_for(name)
        path.unlink()
        return path

    def _safe_stem(self, name: str) -> str:
        text = Path(name.strip()).stem
        safe = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in text)
        safe = safe.strip("._-")
        if not safe:
            raise ValueError("config name is required")
        return safe
