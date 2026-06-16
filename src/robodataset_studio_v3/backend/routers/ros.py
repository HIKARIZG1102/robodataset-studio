from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from robodataset_studio_v3.services.ros_service import ros_service

router = APIRouter()


class TopicRequest(BaseModel):
    topic: str


class NodeRequest(BaseModel):
    node: str


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


@router.post("/image-snapshot", response_model=dict[str, Any])
def image_snapshot(request: TopicRequest) -> dict[str, Any]:
    return ros_service.image_snapshot(request.topic)


@router.post("/node-info", response_model=dict[str, Any])
def node_info(request: NodeRequest) -> dict[str, Any]:
    return ros_service.node_info(request.node)


@router.post("/node-details", response_model=dict[str, Any])
def node_details(request: NodeRequest) -> dict[str, Any]:
    return ros_service.node_details(request.node)


@router.post("/check", response_model=dict[str, Any])
def check(request: TopicRequest) -> dict[str, Any]:
    return ros_service.check_topic_task(request.topic)
