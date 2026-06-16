from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from robodataset_studio_v3.services.ros_service import ros_service

router = APIRouter()


class TopicRequest(BaseModel):
    topic: str


@router.get("/graph", response_model=dict[str, Any])
def graph() -> dict[str, Any]:
    return ros_service.graph()


@router.post("/topic-info", response_model=dict[str, Any])
def topic_info(request: TopicRequest) -> dict[str, Any]:
    return ros_service.topic_info(request.topic)


@router.post("/topic-echo-once", response_model=dict[str, Any])
def topic_echo_once(request: TopicRequest) -> dict[str, Any]:
    return ros_service.echo_once(request.topic)


@router.post("/topic-hz", response_model=dict[str, Any])
def topic_hz(request: TopicRequest) -> dict[str, Any]:
    return ros_service.topic_hz(request.topic)


@router.post("/check", response_model=dict[str, Any])
def check(request: TopicRequest) -> dict[str, Any]:
    return ros_service.check_topic_task(request.topic)
