from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from robodataset_studio_v3.services.review_service import review_service

router = APIRouter()


class SessionRequest(BaseModel):
    session_dir: str


class MarkRequest(SessionRequest):
    episode: str
    status: str


class Hdf5Request(BaseModel):
    hdf5_path: str


class FolderRequest(BaseModel):
    folder: str


@router.post("/session/scan", response_model=dict[str, Any])
def scan_session(request: SessionRequest) -> dict[str, Any]:
    return review_service.scan_session(request.session_dir)


@router.post("/session/check", response_model=dict[str, Any])
def check_session(request: SessionRequest) -> dict[str, Any]:
    return review_service.check_session(request.session_dir)


@router.post("/session/mark", response_model=dict[str, Any])
def mark(request: MarkRequest) -> dict[str, Any]:
    return review_service.mark(request.session_dir, request.episode, request.status)


@router.post("/hdf5/check", response_model=dict[str, Any])
def check_hdf5(request: Hdf5Request) -> dict[str, Any]:
    return review_service.check_hdf5(request.hdf5_path)


@router.post("/layout/check", response_model=dict[str, Any])
def check_layout(request: FolderRequest) -> dict[str, Any]:
    return review_service.check_layout(request.folder)
