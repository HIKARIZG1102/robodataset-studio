from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from robodataset_studio.models.config import (
    CollectionConfigDraft,
    ConfigPreview,
    DatasetConfigDraft,
    ProjectConfigDraft,
)
from robodataset_studio.services.config_service import ConfigService
from robodataset_studio.services.project_service import project_service

router = APIRouter()
service = ConfigService()
projects = project_service


class LibraryConfigCreateRequest(BaseModel):
    name: str = ""
    source_config_id: str = ""


class LibraryConfigRenameRequest(BaseModel):
    name: str


@router.post("/preview", response_model=ConfigPreview)
def preview_config(config: CollectionConfigDraft) -> ConfigPreview:
    return service.preview_dataset(config)


@router.post("/project/preview", response_model=ConfigPreview)
def preview_project_config(config: ProjectConfigDraft) -> ConfigPreview:
    return service.preview_project(config)


@router.post("/dataset/preview", response_model=ConfigPreview)
def preview_dataset_config(config: DatasetConfigDraft) -> ConfigPreview:
    return service.preview_dataset(config)


@router.get("/library", response_model=list[dict[str, Any]])
def list_library_configs() -> list[dict[str, Any]]:
    return service.list_library_configs()


@router.post("/library", response_model=dict[str, Any])
def create_library_config(request: LibraryConfigCreateRequest) -> dict[str, Any]:
    return service.create_library_config(request.name, request.source_config_id)


@router.post("/library/{config_id}/duplicate", response_model=dict[str, Any])
def duplicate_library_config(config_id: str, request: LibraryConfigCreateRequest) -> dict[str, Any]:
    try:
        return service.duplicate_library_config(config_id, request.name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/library/{config_id}/rename", response_model=dict[str, Any])
def rename_library_config(config_id: str, request: LibraryConfigRenameRequest) -> dict[str, Any]:
    try:
        return service.rename_library_config(config_id, request.name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/library/{config_id}", response_model=dict[str, Any])
def get_library_config(config_id: str) -> dict[str, Any]:
    try:
        return service.read_library_config(config_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/library/{config_id}", response_model=dict[str, Any])
def save_library_config(config_id: str, config: dict[str, Any]) -> dict[str, Any]:
    return service.save_library_config(config_id, config)


@router.delete("/library/{config_id}", response_model=dict[str, Any])
def delete_library_config(config_id: str) -> dict[str, Any]:
    try:
        return service.delete_library_config(config_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/project/{project_key}", response_model=dict[str, Any])
def get_project_config(project_key: str) -> dict[str, Any]:
    try:
        return service.read_project_config(projects.project_dir(project_key))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/dataset/{project_key}", response_model=dict[str, Any])
def get_dataset_config(project_key: str) -> dict[str, Any]:
    try:
        return service.read_dataset_config(projects.project_dir(project_key))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/project/{project_key}", response_model=dict[str, str])
def save_project_config(project_key: str, config: ProjectConfigDraft) -> dict[str, str]:
    try:
        service.write_project_config(projects.project_dir(project_key), config)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "saved"}
