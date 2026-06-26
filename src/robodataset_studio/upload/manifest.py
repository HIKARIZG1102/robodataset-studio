from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MANIFEST_NAME = "upload_manifest.json"


class UploadManifest:
    def build(self, root: Path) -> dict[str, Any]:
        source = root.expanduser().resolve()
        base, paths = self.source_base_and_files(source)
        files: list[dict[str, Any]] = []
        for path in paths:
            if not path.is_file() or path.name == MANIFEST_NAME:
                continue
            files.append(
                {
                    "path": path.relative_to(base).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": self._sha256(path),
                }
            )
        return {
            "schema": "robodataset_studio.upload_manifest.v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "root": str(base),
            "source": str(source),
            "source_type": "file" if source.is_file() else "directory",
            "file_count": len(files),
            "total_size_bytes": sum(int(file["size_bytes"]) for file in files),
            "files": files,
        }

    def write(self, root: Path, manifest: dict[str, Any] | None = None) -> Path:
        source = root.expanduser().resolve()
        base, _paths = self.source_base_and_files(source)
        manifest = manifest or self.build(source)
        output = base / MANIFEST_NAME
        output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return output

    def source_base_and_files(self, source: Path) -> tuple[Path, list[Path]]:
        if source.is_file():
            return source.parent, [source]
        if source.is_dir():
            return source, sorted(source.rglob("*"))
        raise FileNotFoundError(f"Upload source does not exist: {source}")

    def verify(self, manifest_path: Path) -> dict[str, Any]:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        root = Path(manifest.get("root") or manifest_path.parent).expanduser()
        missing: list[str] = []
        mismatched: list[str] = []
        checked = 0
        for entry in manifest.get("files", []):
            rel_path = str(entry.get("path", ""))
            path = root / rel_path
            if not path.exists():
                missing.append(rel_path)
                continue
            checked += 1
            if path.stat().st_size != int(entry.get("size_bytes", -1)) or self._sha256(path) != entry.get("sha256"):
                mismatched.append(rel_path)
        return {
            "checked": checked,
            "missing": missing,
            "mismatched": mismatched,
            "ok": not missing and not mismatched,
        }

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
