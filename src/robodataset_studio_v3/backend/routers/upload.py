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
    password: str = ""
    key_path: str = ""


class UploadRequest(ConnectRequest):
    local_path: str = ""
    remote_path: str = ""
    repair: bool = False


class LocalPathRequest(BaseModel):
    local_path: str = ""


class RemotePathRequest(ConnectRequest):
    remote_path: str = ""


class RemoteMkdirRequest(RemotePathRequest):
    folder_name: str = ""


@router.get("/dependencies", response_model=dict[str, Any])
def dependencies() -> dict[str, Any]:
    return upload_service.dependency_check()


@router.post("/connect", response_model=dict[str, Any])
def connect(request: ConnectRequest) -> dict[str, Any]:
    return upload_service.connect(request.host, request.username, request.port, request.password, request.key_path)


@router.post("/manifest", response_model=dict[str, Any])
def manifest(request: LocalPathRequest) -> dict[str, Any]:
    return upload_service.manifest(request.local_path)


@router.post("/manifest/verify", response_model=dict[str, Any])
def verify_manifest(request: LocalPathRequest) -> dict[str, Any]:
    return upload_service.verify_local_manifest(request.local_path)


@router.post("/remote/list", response_model=dict[str, Any])
def remote_list(request: RemotePathRequest) -> dict[str, Any]:
    return upload_service.remote_list(request.host, request.username, request.remote_path, request.port, request.password, request.key_path)


@router.post("/remote/mkdir", response_model=dict[str, Any])
def remote_mkdir(request: RemoteMkdirRequest) -> dict[str, Any]:
    return upload_service.remote_mkdir(request.host, request.username, request.remote_path, request.folder_name, request.port, request.password, request.key_path)


@router.post("/remote/space", response_model=dict[str, Any])
def remote_space(request: RemotePathRequest) -> dict[str, Any]:
    return upload_service.remote_space(request.host, request.username, request.remote_path, request.port, request.password, request.key_path)


@router.post("/start", response_model=dict[str, Any])
def start(request: UploadRequest) -> dict[str, Any]:
    return upload_service.start(request.local_path, request.remote_path, request.host, request.username, repair=request.repair, port=request.port, password=request.password, key_path=request.key_path)


@router.post("/repair", response_model=dict[str, Any])
def repair(request: UploadRequest) -> dict[str, Any]:
    return upload_service.start(request.local_path, request.remote_path, request.host, request.username, repair=True, port=request.port, password=request.password, key_path=request.key_path)


@router.post("/verify", response_model=dict[str, Any])
def verify(request: UploadRequest) -> dict[str, Any]:
    return upload_service.verify(request.local_path, request.remote_path, request.host, request.username, port=request.port, password=request.password, key_path=request.key_path)
