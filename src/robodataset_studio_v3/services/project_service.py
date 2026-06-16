from __future__ import annotations

from pathlib import Path

import yaml

from robodataset_studio_v3.models.project import ProjectCreateRequest, ProjectSummary
from robodataset_studio_v3.services.config_service import ConfigService


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


class ProjectService:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or repo_root() / "robodataset" / "projects"
        self.config_service = ConfigService()

    def list_projects(self) -> list[ProjectSummary]:
        if not self.root.exists():
            return []
        projects = []
        for path in sorted(item for item in self.root.iterdir() if item.is_dir()):
            name, version = self._split_key(path.name)
            projects.append(ProjectSummary(key=path.name, name=name, version=version, path=str(path)))
        return projects

    def project_dir(self, key: str) -> Path:
        safe_key = self._safe_part(key)
        path = self.root / safe_key
        if not path.exists() or not path.is_dir():
            raise FileNotFoundError(f"project not found: {key}")
        return path

    def create_project(self, request: ProjectCreateRequest) -> ProjectSummary:
        name = self._safe_part(request.name or "untitled_project")
        version = self._safe_part(request.version or "v1")
        key = f"{name}_{version}"
        path = self.root / key
        if path.exists():
            raise FileExistsError(f"project already exists: {key}")
        path.mkdir(parents=True, exist_ok=False)
        for child in ["raw_sessions", "review", "exports", "logs"]:
            (path / child).mkdir(exist_ok=True)
        project_meta = {"project": {"name": name, "version": version, "operator": request.operator, "notes": request.notes}}
        (path / "project.yaml").write_text(yaml.safe_dump(project_meta, sort_keys=False, allow_unicode=True), encoding="utf-8")
        self.config_service.write_default_configs(path)
        return ProjectSummary(key=key, name=name, version=version, path=str(path))

    def _safe_part(self, value: str) -> str:
        text = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value.strip())
        return text.strip("_-") or "untitled"

    def _split_key(self, key: str) -> tuple[str, str]:
        if "_v" in key:
            name, version = key.rsplit("_", 1)
            return name, version
        return key, "v1"
