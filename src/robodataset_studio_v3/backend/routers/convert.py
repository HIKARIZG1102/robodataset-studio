from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from robodataset_studio_v3.services.convert_service import convert_service

router = APIRouter()


class ScanRequest(BaseModel):
    root: str


class ConvertRequest(BaseModel):
    sessions: list[str]
    output_dir: str


@router.post("/scan", response_model=dict[str, Any])
def scan(request: ScanRequest) -> dict[str, Any]:
    return convert_service.scan(request.root)


@router.post("/merge", response_model=dict[str, Any])
def merge(request: ConvertRequest) -> dict[str, Any]:
    return convert_service.merge(request.sessions, request.output_dir)


@router.post("/hdf5", response_model=dict[str, Any])
def hdf5(request: ConvertRequest) -> dict[str, Any]:
    return convert_service.hdf5(request.sessions, request.output_dir)
