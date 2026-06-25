from __future__ import annotations

import shutil
from pathlib import Path
from datetime import datetime

import yaml

from robodataset_studio_v3.models.project import ProjectCreateRequest, ProjectSummary
from robodataset_studio_v3.services.config_service import ConfigService
from robodataset_studio_v3.services.path_policy import path_policy


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


class ProjectService:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or repo_root() / "robodataset" / "projects"
        self.config_service = ConfigService()
        self._known_paths: dict[str, Path] = {}
        self._index_path = self.root / ".project_index.yaml"

    def list_projects(self) -> list[ProjectSummary]:
        projects = []
        self._known_paths = {}
        paths_by_resolved: dict[Path, Path] = {}
        if self.root.exists():
            for path in self._discover_project_dirs(self.root):
                paths_by_resolved[path.resolve()] = path
        for indexed in self._load_project_index().values():
            path = Path(indexed)
            if not self._path_allowed(path):
                continue
            if path.exists() and path.is_dir() and (path / "project.yaml").exists():
                paths_by_resolved.setdefault(path.resolve(), path)
        for path in sorted(paths_by_resolved.values(), key=lambda item: (item.name.lower(), str(item))):
            if path.name.startswith("."):
                continue
            try:
                if self.root.exists() and any(part.startswith(".") for part in path.relative_to(self.root).parts):
                    continue
            except ValueError:
                pass
            key = self._safe_part(path.name)
            if key in self._known_paths:
                continue
            self._known_paths[key] = path
            projects.append(self._summary_for_path(path))
        return projects

    def project_dir(self, key: str) -> Path:
        safe_key = self._safe_part(key)
        known = self._project_path_for_key(safe_key)
        if known is not None and known.exists() and known.is_dir():
            path_policy.check(known, label="project folder")
            self._known_paths[safe_key] = known
            return known
        path = self.root / safe_key
        path_policy.check(path, label="project folder")
        if not path.exists() or not path.is_dir():
            raise FileNotFoundError(f"project not found: {key}")
        return path

    def open_path(self, path_text: str) -> ProjectSummary:
        path = self._resolve_project_path(path_text)
        path_policy.check(path, label="project folder")
        if not path.exists() or not path.is_dir():
            raise FileNotFoundError(f"project folder not found: {path}")
        key = path.name
        existing = self._project_path_for_key(key)
        if existing is not None and existing.resolve() != path.resolve():
            raise FileExistsError(f"project key already opened from another path: {key} ({existing})")
        self._known_paths[key] = path
        self._register_project_path(key, path)
        return self._summary_for_path(path)

    def rename_project(self, key: str, new_key: str) -> ProjectSummary:
        old_path = self.project_dir(key)
        safe_key = self._safe_project_key(new_key)
        new_path = old_path.parent / safe_key
        existing = self._project_path_for_key(safe_key)
        if existing is not None and existing.resolve() != old_path.resolve():
            raise FileExistsError(f"project already exists: {safe_key} ({existing})")
        if new_path.exists():
            raise FileExistsError(f"project already exists: {safe_key}")
        old_path.rename(new_path)
        self._known_paths.pop(self._safe_part(key), None)
        self._known_paths[safe_key] = new_path
        self._unregister_project_path(self._safe_part(key))
        self._register_project_path(safe_key, new_path)
        name, version = self._split_key(safe_key)
        meta = self._project_meta(new_path)
        meta.setdefault("project", {})
        meta["project"]["name"] = name
        meta["project"]["version"] = version
        (new_path / "project.yaml").write_text(yaml.safe_dump(meta, sort_keys=False, allow_unicode=True), encoding="utf-8")
        return self._summary_for_path(new_path)

    def delete_project(self, key: str) -> dict[str, str]:
        path = self.project_dir(key)
        deleted_root = path.parent / ".deleted_projects"
        deleted_root.mkdir(exist_ok=True)
        target = deleted_root / f"{path.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        path.rename(target)
        self._known_paths.pop(self._safe_part(key), None)
        self._unregister_project_path(self._safe_part(key))
        return {"status": "moved", "path": str(target)}

    def permanently_delete_project(self, key: str) -> dict[str, str]:
        path = self.project_dir(key)
        self._ensure_deletable_project_path(path)
        shutil.rmtree(path)
        self._known_paths.pop(self._safe_part(key), None)
        self._unregister_project_path(self._safe_part(key))
        return {"status": "deleted", "path": str(path)}

    def create_project(self, request: ProjectCreateRequest) -> ProjectSummary:
        name = self._safe_part(request.name or "untitled_project")
        version = self._safe_part(request.version or "v1")
        key = f"{name}_{version}"
        root = self._resolve_user_path(request.root_path) if request.root_path.strip() else self.root
        path_policy.check(root, label="project root")
        existing = self._project_path_for_key(key)
        if existing is not None:
            raise FileExistsError(f"project already exists: {key} ({existing})")
        if (root / "project.yaml").exists():
            raise FileExistsError(f"selected root is already a project folder: {root}")
        path = root / key
        nested_projects = self._discover_project_dirs(root, max_depth=1) if root.exists() else []
        same_key_nested = [item for item in nested_projects if item.name == key]
        if same_key_nested:
            raise FileExistsError(f"project already exists: {key} ({same_key_nested[0]})")
        if path.exists():
            raise FileExistsError(f"project already exists: {key}")
        path.mkdir(parents=True, exist_ok=False)
        self._known_paths[key] = path
        self._register_project_path(key, path)
        for child in ["raw_sessions", "review", "exports", "logs"]:
            (path / child).mkdir(exist_ok=True)
        config_id = request.config_id or "default_calvin"
        project_meta = {
            "project": {
                "name": name,
                "version": version,
                "operator": request.operator,
                "notes": request.notes,
                "config_id": config_id,
            }
        }
        (path / "project.yaml").write_text(yaml.safe_dump(project_meta, sort_keys=False, allow_unicode=True), encoding="utf-8")
        try:
            self.config_service.apply_library_config_to_project(path, config_id)
        except FileNotFoundError:
            self.config_service.ensure_default_library_config()
            config_id = "default_calvin"
            project_meta["project"]["config_id"] = config_id
            (path / "project.yaml").write_text(yaml.safe_dump(project_meta, sort_keys=False, allow_unicode=True), encoding="utf-8")
            self.config_service.apply_library_config_to_project(path, config_id)
        return self._summary_for_path(path)

    def bind_config(self, key: str, config_id: str) -> ProjectSummary:
        path = self.project_dir(key)
        meta = self._project_meta(path)
        project = meta.get("project", {}) if isinstance(meta.get("project"), dict) else {}
        current_config_id = str(project.get("config_id") or "")
        if self.has_recorded_data(path) and config_id != current_config_id:
            raise RuntimeError("project already has recorded data; create a new project version before loading another config")
        self.config_service.apply_library_config_to_project(path, config_id)
        meta.setdefault("project", {})
        meta["project"]["config_id"] = config_id
        (path / "project.yaml").write_text(yaml.safe_dump(meta, sort_keys=False, allow_unicode=True), encoding="utf-8")
        return self._summary_for_path(path)

    def has_recorded_data(self, path: Path) -> bool:
        raw_sessions = path / "raw_sessions"
        if not raw_sessions.exists():
            return False
        for item in raw_sessions.rglob("*"):
            if item.is_file() and (item.name.startswith("episode_") or item.suffix in {".npz", ".hdf5"}):
                return True
            if item.is_dir() and item.name.startswith("session_"):
                training = item / "training"
                if training.exists() and any(training.glob("episode_*.npz")):
                    return True
        return False

    def _summary_for_path(self, path: Path) -> ProjectSummary:
        name, version = self._split_key(path.name)
        meta = self._project_meta(path)
        project = meta.get("project", {}) if isinstance(meta.get("project"), dict) else {}
        return ProjectSummary(
            key=path.name,
            name=str(project.get("name") or name),
            version=str(project.get("version") or version),
            path=str(path),
            config_id=str(project.get("config_id") or ""),
            has_recorded_data=self.has_recorded_data(path),
        )

    def _project_meta(self, path: Path) -> dict:
        meta_path = path / "project.yaml"
        if not meta_path.exists():
            return {}
        data = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}

    def _safe_part(self, value: str) -> str:
        text = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value.strip())
        return text.strip("_-") or "untitled"

    def _safe_project_key(self, value: str) -> str:
        safe = self._safe_part(value)
        if "_" not in safe:
            safe = f"{safe}_v1"
        return safe

    def _split_key(self, key: str) -> tuple[str, str]:
        if "_v" in key:
            name, version = key.rsplit("_", 1)
            return name, version
        return key, "v1"

    def _resolve_user_path(self, path_text: str) -> Path:
        path = Path(path_text).expanduser()
        if not path.is_absolute():
            path = repo_root() / path
        return path_policy.check(path, label="path")

    def _resolve_project_path(self, path_text: str) -> Path:
        path = self._resolve_user_path(path_text)
        if (path / "project.yaml").exists():
            return path
        candidates = self._discover_project_dirs(path, max_depth=1)
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            names = ", ".join(candidate.name for candidate in candidates[:5])
            raise FileExistsError(f"selected folder contains multiple projects; choose one project folder: {names}")
        return path

    def _project_path_for_key(self, key: str) -> Path | None:
        safe_key = self._safe_part(key)
        known = self._known_paths.get(safe_key)
        if known is not None and known.exists() and known.is_dir():
            if not self._path_allowed(known):
                return None
            return known
        index = self._load_project_index()
        indexed = index.get(safe_key)
        if indexed:
            indexed_path = Path(indexed)
            if self._path_allowed(indexed_path) and indexed_path.exists() and indexed_path.is_dir() and (indexed_path / "project.yaml").exists():
                return indexed_path
            self._unregister_project_path(safe_key)
        default_path = self.root / safe_key
        if default_path.exists() and default_path.is_dir() and (default_path / "project.yaml").exists():
            return default_path
        for path in self._discover_project_dirs(self.root):
            if path.name == safe_key:
                path_policy.check(path, label="project folder")
                return path
        return None

    def _load_project_index(self) -> dict[str, str]:
        if not self._index_path.exists():
            return {}
        try:
            data = yaml.safe_load(self._index_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        projects = data.get("projects", data)
        if not isinstance(projects, dict):
            return {}
        return {self._safe_part(str(key)): str(value) for key, value in projects.items() if str(value)}

    def _save_project_index(self, index: dict[str, str]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {"projects": dict(sorted(index.items()))}
        self._index_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")

    def _register_project_path(self, key: str, path: Path) -> None:
        safe_key = self._safe_part(key)
        index = self._load_project_index()
        index[safe_key] = str(path)
        self._save_project_index(index)

    def _unregister_project_path(self, key: str) -> None:
        safe_key = self._safe_part(key)
        index = self._load_project_index()
        if safe_key in index:
            index.pop(safe_key, None)
            self._save_project_index(index)

    def _discover_project_dirs(self, root: Path, *, max_depth: int = 2) -> list[Path]:
        if not root.exists() or not root.is_dir():
            return []
        projects: list[Path] = []

        def walk(path: Path, depth: int) -> None:
            if depth > max_depth:
                return
            if path.name.startswith("."):
                return
            if (path / "project.yaml").exists():
                projects.append(path)
                return
            try:
                children = sorted(item for item in path.iterdir() if item.is_dir())
            except Exception:
                return
            for child in children:
                walk(child, depth + 1)

        walk(root, 0)
        return projects

    def _ensure_deletable_project_path(self, path: Path) -> None:
        resolved = path.resolve()
        projects_root = self.root.resolve()
        try:
            resolved.relative_to(projects_root)
        except ValueError as exc:
            raise ValueError(f"refusing to permanently delete project outside project root: {resolved}") from exc
        if resolved == projects_root or resolved.name.startswith("."):
            raise ValueError(f"refusing to permanently delete protected path: {resolved}")

    def _path_allowed(self, path: Path) -> bool:
        try:
            path_policy.check(path, label="project folder")
        except ValueError:
            return False
        return True


project_service = ProjectService()
