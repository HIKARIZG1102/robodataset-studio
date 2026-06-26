from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from robodataset_studio.services.review_service import review_service
from robodataset_studio.services.settings_service import settings_service
from robodataset_studio.services.task_service import task_service

router = APIRouter()


@router.get("", response_model=dict[str, Any])
def get_settings() -> dict[str, Any]:
    return settings_service.read()


@router.put("", response_model=dict[str, Any])
def put_settings(settings: dict[str, Any]) -> dict[str, Any]:
    return settings_service.write(settings)


@router.get("/maintenance/summary", response_model=dict[str, Any])
def maintenance_summary() -> dict[str, Any]:
    return {"task_archive": task_service.archive_summary()}


@router.post("/maintenance/cleanup-recycle-bin", response_model=dict[str, Any])
def cleanup_recycle_bin(request: dict[str, Any]) -> dict[str, Any]:
    return review_service.cleanup_recycle_bin(str(request.get("project_dir") or ""))


@router.post("/maintenance/clear-log-cache", response_model=dict[str, Any])
def clear_log_cache() -> dict[str, Any]:
    return {"result": task_service.clear_runtime_cache()}
