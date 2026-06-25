from __future__ import annotations

import os
from pathlib import Path


class PathPolicy:
    def __init__(self) -> None:
        self.enabled = str(os.environ.get("ROBODATASET_DOCKER", "")).lower() in {"1", "true", "yes"}
        root = os.environ.get("ROBODATASET_ALLOWED_ROOT", "")
        self.allowed_root = Path(root).expanduser() if root else None

    def check(self, path: Path | str, *, label: str = "path", must_exist: bool = False) -> Path:
        resolved = Path(path).expanduser()
        if must_exist:
            resolved = resolved.resolve()
        else:
            resolved = resolved.resolve(strict=False)
        if not self.enabled or self.allowed_root is None:
            return resolved
        allowed = self.allowed_root.resolve(strict=False)
        try:
            resolved.relative_to(allowed)
        except ValueError as exc:
            raise ValueError(
                f"{label} is outside the Docker workspace: {resolved}. "
                f"Use a path under {allowed}."
            ) from exc
        return resolved

    def is_enabled(self) -> bool:
        return self.enabled and self.allowed_root is not None


path_policy = PathPolicy()
