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

    def list_projects(self) -> list[ProjectSummary]:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{self.base_url}/api/projects")
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, list):
            return []
        return [ProjectSummary(**item) for item in data if isinstance(item, dict)]

    def create_project(self, *, name: str, version: str, operator: str = "", notes: str = "") -> ProjectSummary:
        payload = {"name": name, "version": version, "operator": operator, "notes": notes}
        with httpx.Client(timeout=5.0) as client:
            response = client.post(f"{self.base_url}/api/projects", json=payload)
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("backend returned invalid project response")
        return ProjectSummary(**data)

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
