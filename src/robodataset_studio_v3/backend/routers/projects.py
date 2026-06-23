from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from robodataset_studio_v3.models.project import ProjectConfigBindRequest, ProjectCreateRequest, ProjectOpenPathRequest, ProjectSummary
from robodataset_studio_v3.services.project_service import project_service

router = APIRouter()
service = project_service


class ProjectRenameRequest(BaseModel):
    name: str


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


@router.put("/{project_key}/config", response_model=ProjectSummary)
def bind_project_config(project_key: str, request: ProjectConfigBindRequest) -> ProjectSummary:
    try:
        return service.bind_config(project_key, request.config_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{project_key}/rename", response_model=ProjectSummary)
def rename_project(project_key: str, request: ProjectRenameRequest) -> ProjectSummary:
    try:
        return service.rename_project(project_key, request.name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/{project_key}", response_model=dict[str, str])
def delete_project(project_key: str) -> dict[str, str]:
    try:
        return service.delete_project(project_key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{project_key}/permanent", response_model=dict[str, str])
def permanently_delete_project(project_key: str) -> dict[str, str]:
    try:
        return service.permanently_delete_project(project_key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
