from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from robodataset_studio_v3.services.ai_service import ai_service

router = APIRouter()


class ConfigPromptRequest(BaseModel):
    dataset_config: dict[str, Any] = {}
    ros_context: dict[str, Any] = {}


class ReviewPromptRequest(BaseModel):
    review_summary: dict[str, Any] = {}


class ModelsRequest(BaseModel):
    base_url: str = ""


class SendRequest(BaseModel):
    prompt: str
    kind: str = "ai"


@router.post("/config-prompt", response_model=dict[str, Any])
def config_prompt(request: ConfigPromptRequest) -> dict[str, Any]:
    return ai_service.config_prompt(request.dataset_config, request.ros_context)


@router.post("/review-prompt", response_model=dict[str, Any])
def review_prompt(request: ReviewPromptRequest) -> dict[str, Any]:
    return ai_service.review_prompt(request.review_summary)


@router.post("/models", response_model=dict[str, Any])
def models(request: ModelsRequest) -> dict[str, Any]:
    return ai_service.models(request.base_url)


@router.post("/send", response_model=dict[str, Any])
def send(request: SendRequest) -> dict[str, Any]:
    return ai_service.send(request.prompt, request.kind)
