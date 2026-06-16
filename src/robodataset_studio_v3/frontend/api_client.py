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

    def list_projects(self) -> list[ProjectSummary]:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{self.base_url}/api/projects")
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, list):
            return []
        return [ProjectSummary(**item) for item in data if isinstance(item, dict)]

    def create_project(self, *, name: str, version: str, operator: str = "") -> ProjectSummary:
        payload = {"name": name, "version": version, "operator": operator}
        with httpx.Client(timeout=5.0) as client:
            response = client.post(f"{self.base_url}/api/projects", json=payload)
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("backend returned invalid project response")
        return ProjectSummary(**data)
