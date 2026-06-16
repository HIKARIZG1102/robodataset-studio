from __future__ import annotations

from fastapi import APIRouter, HTTPException

from robodataset_studio_v3.models.project import ProjectCreateRequest, ProjectOpenPathRequest, ProjectSummary
from robodataset_studio_v3.services.project_service import project_service

router = APIRouter()
service = project_service


@router.get("", response_model=list[ProjectSummary])
def list_projects() -> list[ProjectSummary]:
    return service.list_projects()


@router.post("", response_model=ProjectSummary)
def create_project(request: ProjectCreateRequest) -> ProjectSummary:
    try:
        return service.create_project(request)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/open-path", response_model=ProjectSummary)
def open_project_path(request: ProjectOpenPathRequest) -> ProjectSummary:
    try:
        return service.open_path(request.path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
