from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from robodataset_studio.services.environment_service import environment_service

router = APIRouter()


@router.get("/diagnostics", response_model=dict[str, Any])
def diagnostics() -> dict[str, Any]:
    return environment_service.diagnostics()
