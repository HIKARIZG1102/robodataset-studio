from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CollectionConfigDraft(BaseModel):
    project: dict[str, Any] = Field(default_factory=dict)
    environment: dict[str, Any] = Field(default_factory=dict)
    ros: dict[str, Any] = Field(default_factory=dict)
    robot: dict[str, Any] = Field(default_factory=dict)
    streams: list[dict[str, Any]] = Field(default_factory=list)
    recording: dict[str, Any] = Field(default_factory=dict)
    dataset: dict[str, Any] = Field(default_factory=dict)


class ConfigPreview(BaseModel):
    summary: str
    warnings: list[str] = Field(default_factory=list)
