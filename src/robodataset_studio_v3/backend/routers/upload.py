from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from robodataset_studio_v3.services.upload_service import upload_service

router = APIRouter()


class ConnectRequest(BaseModel):
    host: str = ""
    username: str = ""
    port: int = 22


class UploadRequest(ConnectRequest):
    local_path: str = ""
    remote_path: str = ""
    repair: bool = False


@router.get("/dependencies", response_model=dict[str, Any])
def dependencies() -> dict[str, Any]:
    return upload_service.dependency_check()


@router.post("/connect", response_model=dict[str, Any])
def connect(request: ConnectRequest) -> dict[str, Any]:
    return upload_service.connect(request.host, request.username, request.port)


@router.post("/start", response_model=dict[str, Any])
def start(request: UploadRequest) -> dict[str, Any]:
    return upload_service.start(request.local_path, request.remote_path, request.host, request.username, repair=request.repair)


@router.post("/repair", response_model=dict[str, Any])
def repair(request: UploadRequest) -> dict[str, Any]:
    return upload_service.start(request.local_path, request.remote_path, request.host, request.username, repair=True)


@router.post("/verify", response_model=dict[str, Any])
def verify(request: UploadRequest) -> dict[str, Any]:
    return upload_service.verify(request.local_path, request.remote_path, request.host)
