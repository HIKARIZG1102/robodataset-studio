from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from robodataset_studio_v3.services.recording_service import recording_service

router = APIRouter()


class ProjectRequest(BaseModel):
    project_key: str


class RecordingStartRequest(ProjectRequest):
    mode: str = "manual"


@router.post("/preflight", response_model=dict[str, Any])
def preflight(request: ProjectRequest) -> dict[str, Any]:
    return recording_service.preflight(request.project_key)


@router.post("/start", response_model=dict[str, Any])
def start(request: RecordingStartRequest) -> dict[str, Any]:
    return recording_service.start(request.project_key, mode=request.mode)


@router.post("/stop", response_model=dict[str, Any])
def stop(request: ProjectRequest) -> dict[str, Any]:
    return recording_service.stop(request.project_key)
