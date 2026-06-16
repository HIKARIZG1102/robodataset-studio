from __future__ import annotations

from fastapi import APIRouter

from robodataset_studio_v3.models.config import CollectionConfigDraft, ConfigPreview
from robodataset_studio_v3.services.config_service import ConfigService

router = APIRouter()
service = ConfigService()


@router.post("/preview", response_model=ConfigPreview)
def preview_config(config: CollectionConfigDraft) -> ConfigPreview:
    return service.preview(config)
