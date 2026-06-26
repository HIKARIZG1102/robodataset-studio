from __future__ import annotations

import os

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, object]:
    docker_mode = str(os.environ.get("ROBODATASET_DOCKER", "")).lower() in {"1", "true", "yes"}
    return {
        "status": "ok",
        "service": "robodataset-studio-v3",
        "root": os.environ.get("ROBODATASET_V3_ROOT", ""),
        "docker": docker_mode,
        "allowed_root": os.environ.get("ROBODATASET_ALLOWED_ROOT", ""),
        "pid": os.getpid(),
    }
