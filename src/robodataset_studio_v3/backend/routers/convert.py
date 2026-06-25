from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from robodataset_studio_v3.services.convert_service import convert_service

router = APIRouter()


class ScanRequest(BaseModel):
    root: str


class ConvertRequest(BaseModel):
    sessions: list[str]
    output_dir: str
    output_name: str = ""


@router.post("/scan", response_model=dict[str, Any])
def scan(request: ScanRequest) -> dict[str, Any]:
    return _convert_call(convert_service.scan, request.root)


@router.post("/merge", response_model=dict[str, Any])
def merge(request: ConvertRequest) -> dict[str, Any]:
    return _convert_call(convert_service.merge, request.sessions, request.output_dir, request.output_name)


@router.post("/hdf5", response_model=dict[str, Any])
def hdf5(request: ConvertRequest) -> dict[str, Any]:
    return _convert_call(convert_service.hdf5, request.sessions, request.output_dir, request.output_name)


def _convert_call(fn, *args, **kwargs) -> dict[str, Any]:
    try:
        return fn(*args, **kwargs)
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
