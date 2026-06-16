from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from robodataset_studio_v3.models.config import (
    CollectionConfigDraft,
    ConfigPreview,
    DatasetConfigDraft,
    ProjectConfigDraft,
)
from robodataset_studio_v3.services.config_service import ConfigService
from robodataset_studio_v3.services.project_service import ProjectService

router = APIRouter()
service = ConfigService()
projects = ProjectService()


@router.post("/preview", response_model=ConfigPreview)
def preview_config(config: CollectionConfigDraft) -> ConfigPreview:
    return service.preview_dataset(config)


@router.post("/project/preview", response_model=ConfigPreview)
def preview_project_config(config: ProjectConfigDraft) -> ConfigPreview:
    return service.preview_project(config)


@router.post("/dataset/preview", response_model=ConfigPreview)
def preview_dataset_config(config: DatasetConfigDraft) -> ConfigPreview:
    return service.preview_dataset(config)


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
