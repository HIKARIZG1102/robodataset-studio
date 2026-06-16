from __future__ import annotations

from fastapi import APIRouter

from robodataset_studio_v3.models.project import ProjectCreateRequest, ProjectSummary
from robodataset_studio_v3.services.project_service import ProjectService

router = APIRouter()
service = ProjectService()


@router.get("", response_model=list[ProjectSummary])
def list_projects() -> list[ProjectSummary]:
    return service.list_projects()


@router.post("", response_model=ProjectSummary)
def create_project(request: ProjectCreateRequest) -> ProjectSummary:
    return service.create_project(request)
