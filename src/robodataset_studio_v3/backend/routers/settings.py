from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from robodataset_studio_v3.services.settings_service import settings_service

router = APIRouter()


@router.get("", response_model=dict[str, Any])
def get_settings() -> dict[str, Any]:
    return settings_service.read()


@router.put("", response_model=dict[str, Any])
def put_settings(settings: dict[str, Any]) -> dict[str, Any]:
    return settings_service.write(settings)
