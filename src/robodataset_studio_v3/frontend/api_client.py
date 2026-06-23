from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class ProjectSummary:
    key: str
    name: str
    version: str
    path: str
    config_id: str = ""
    has_recorded_data: bool = False


class ApiClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8765") -> None:
        self.base_url = base_url.rstrip("/")

    def health(self) -> dict[str, Any]:
        with httpx.Client(timeout=2.0) as client:
            response = client.get(f"{self.base_url}/api/health")
            response.raise_for_status()
            data = response.json()
        return data if isinstance(data, dict) else {}

    def get(self, path: str, *, timeout: float = 10.0) -> Any:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(f"{self.base_url}{path}")
            response.raise_for_status()
            return response.json()

    def post(self, path: str, payload: dict[str, Any] | None = None, *, timeout: float = 20.0) -> Any:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(f"{self.base_url}{path}", json=payload or {})
            response.raise_for_status()
            return response.json()

    def put(self, path: str, payload: dict[str, Any], *, timeout: float = 20.0) -> Any:
        with httpx.Client(timeout=timeout) as client:
            response = client.put(f"{self.base_url}{path}", json=payload)
            response.raise_for_status()
            return response.json()

    def delete(self, path: str, *, timeout: float = 20.0) -> Any:
        with httpx.Client(timeout=timeout) as client:
            response = client.delete(f"{self.base_url}{path}")
            response.raise_for_status()
            return response.json()

    def list_projects(self) -> list[ProjectSummary]:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{self.base_url}/api/projects")
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, list):
            return []
        return [ProjectSummary(**item) for item in data if isinstance(item, dict)]

    def default_project_root(self) -> str:
        data = self.get("/api/projects/default-root", timeout=5.0)
        return str(data.get("path") or "") if isinstance(data, dict) else ""

    def open_project_path(self, path: str) -> ProjectSummary:
        data = self.post("/api/projects/open-path", {"path": path})
        if not isinstance(data, dict):
            raise RuntimeError("backend returned invalid project response")
        return ProjectSummary(**data)

    def create_project(
        self,
        *,
        name: str,
        version: str,
        operator: str = "",
        notes: str = "",
        root_path: str = "",
        config_id: str = "",
    ) -> ProjectSummary:
        payload = {
            "name": name,
            "version": version,
            "operator": operator,
            "notes": notes,
            "root_path": root_path,
            "config_id": config_id,
        }
        with httpx.Client(timeout=5.0) as client:
            response = client.post(f"{self.base_url}/api/projects", json=payload)
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("backend returned invalid project response")
        return ProjectSummary(**data)

    def bind_project_config(self, project_key: str, config_id: str) -> ProjectSummary:
        data = self.put(f"/api/projects/{project_key}/config", {"config_id": config_id}, timeout=10.0)
        if not isinstance(data, dict):
            raise RuntimeError("backend returned invalid project response")
        return ProjectSummary(**data)

    def rename_project(self, project_key: str, name: str) -> ProjectSummary:
        data = self.post(f"/api/projects/{project_key}/rename", {"name": name}, timeout=10.0)
        if not isinstance(data, dict):
            raise RuntimeError("backend returned invalid project response")
        return ProjectSummary(**data)

    def delete_project(self, project_key: str) -> dict[str, Any]:
        data = self.delete(f"/api/projects/{project_key}", timeout=10.0)
        return data if isinstance(data, dict) else {}

    def permanently_delete_project(self, project_key: str) -> dict[str, Any]:
        data = self.delete(f"/api/projects/{project_key}/permanent", timeout=20.0)
        return data if isinstance(data, dict) else {}

    def list_configs(self) -> list[dict[str, Any]]:
        data = self.get("/api/config/library")
        return data if isinstance(data, list) else []

    def create_config(self, name: str, source_config_id: str = "") -> dict[str, Any]:
        data = self.post("/api/config/library", {"name": name, "source_config_id": source_config_id})
        return data if isinstance(data, dict) else {}

    def get_config(self, config_id: str) -> dict[str, Any]:
        data = self.get(f"/api/config/library/{config_id}")
        return data if isinstance(data, dict) else {}

    def save_config(self, config_id: str, config: dict[str, Any]) -> dict[str, Any]:
        data = self.put(f"/api/config/library/{config_id}", config, timeout=20.0)
        return data if isinstance(data, dict) else {}

    def duplicate_config(self, config_id: str, name: str = "") -> dict[str, Any]:
        data = self.post(f"/api/config/library/{config_id}/duplicate", {"name": name}, timeout=10.0)
        return data if isinstance(data, dict) else {}

    def rename_config(self, config_id: str, name: str) -> dict[str, Any]:
        data = self.post(f"/api/config/library/{config_id}/rename", {"name": name}, timeout=10.0)
        return data if isinstance(data, dict) else {}

    def delete_config(self, config_id: str) -> dict[str, Any]:
        data = self.delete(f"/api/config/library/{config_id}", timeout=10.0)
        return data if isinstance(data, dict) else {}

    def get_project_config(self, project_key: str) -> dict[str, Any]:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{self.base_url}/api/config/project/{project_key}")
            response.raise_for_status()
            data = response.json()
        return data if isinstance(data, dict) else {}

    def get_dataset_config(self, project_key: str) -> dict[str, Any]:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{self.base_url}/api/config/dataset/{project_key}")
            response.raise_for_status()
            data = response.json()
        return data if isinstance(data, dict) else {}

    def list_tasks(self) -> list[dict[str, Any]]:
        data = self.get("/api/tasks")
        return data if isinstance(data, list) else []
