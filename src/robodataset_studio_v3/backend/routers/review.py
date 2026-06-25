from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from robodataset_studio_v3.services.review_service import review_service

router = APIRouter()


class SessionRequest(BaseModel):
    session_dir: str


class SessionAiReportRequest(SessionRequest):
    content: str


class MarkRequest(SessionRequest):
    episode: str
    status: str


class Hdf5Request(BaseModel):
    hdf5_path: str


class FolderRequest(BaseModel):
    folder: str


@router.post("/session/scan", response_model=dict[str, Any])
def scan_session(request: SessionRequest) -> dict[str, Any]:
    return _review_call(review_service.scan_session, request.session_dir)


@router.post("/session/check", response_model=dict[str, Any])
def check_session(request: SessionRequest) -> dict[str, Any]:
    return _review_call(review_service.check_session, request.session_dir)


@router.post("/session/report", response_model=dict[str, Any])
def quality_report(request: SessionRequest) -> dict[str, Any]:
    return _review_call(review_service.quality_report, request.session_dir)


@router.post("/session/ai-report/load", response_model=dict[str, Any])
def load_ai_report(request: SessionRequest) -> dict[str, Any]:
    return _review_call(review_service.load_ai_report, request.session_dir)


@router.post("/session/ai-prompt", response_model=dict[str, Any])
def session_ai_prompt(request: SessionRequest) -> dict[str, Any]:
    return _review_call(review_service.ai_prompt, request.session_dir)


@router.post("/session/ai-report/save", response_model=dict[str, Any])
def save_ai_report(request: SessionAiReportRequest) -> dict[str, Any]:
    return _review_call(review_service.save_ai_report, request.session_dir, request.content)


@router.post("/session/mark", response_model=dict[str, Any])
def mark(request: MarkRequest) -> dict[str, Any]:
    return _review_call(review_service.mark, request.session_dir, request.episode, request.status)


@router.post("/session/episode", response_model=dict[str, Any])
def episode_detail(request: MarkRequest) -> dict[str, Any]:
    return _review_call(review_service.episode_detail, request.session_dir, request.episode)


@router.post("/session/trash", response_model=dict[str, Any])
def trash_episode(request: MarkRequest) -> dict[str, Any]:
    return _review_call(review_service.trash_episode, request.session_dir, request.episode)


@router.post("/session/delete", response_model=dict[str, Any])
def delete_session(request: SessionRequest) -> dict[str, Any]:
    return _review_call(review_service.delete_session, request.session_dir)


@router.post("/hdf5/inspect", response_model=dict[str, Any])
def inspect_hdf5(request: Hdf5Request) -> dict[str, Any]:
    return _review_call(review_service.inspect_hdf5, request.hdf5_path)


@router.post("/hdf5/check", response_model=dict[str, Any])
def check_hdf5(request: Hdf5Request) -> dict[str, Any]:
    return _review_call(review_service.check_hdf5, request.hdf5_path)


@router.post("/layout/scan", response_model=dict[str, Any])
def scan_layout(request: FolderRequest) -> dict[str, Any]:
    return _review_call(review_service.scan_layout, request.folder)


@router.post("/layout/check", response_model=dict[str, Any])
def check_layout(request: FolderRequest) -> dict[str, Any]:
    return _review_call(review_service.check_layout, request.folder)


def _review_call(fn, *args, **kwargs) -> dict[str, Any]:
    try:
        return fn(*args, **kwargs)
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
