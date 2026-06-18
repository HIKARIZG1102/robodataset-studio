from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DatasetConfigDraft(BaseModel):
    environment: dict[str, Any] = Field(default_factory=dict)
    instruction: dict[str, Any] = Field(default_factory=dict)
    ros: dict[str, Any] = Field(default_factory=dict)
    robot: dict[str, Any] = Field(default_factory=dict)
    streams: list[dict[str, Any]] = Field(default_factory=list)
    state: dict[str, Any] = Field(default_factory=dict)
    action: dict[str, Any] = Field(default_factory=dict)
    recording: dict[str, Any] = Field(default_factory=dict)
    dataset: dict[str, Any] = Field(default_factory=dict)
    ai_assist: dict[str, Any] = Field(default_factory=dict)


class ProjectConfigDraft(BaseModel):
    dataset_config: DatasetConfigDraft = Field(default_factory=DatasetConfigDraft)
    paths: dict[str, Any] = Field(default_factory=dict)
    collection: dict[str, Any] = Field(default_factory=dict)
    review: dict[str, Any] = Field(default_factory=dict)
    convert: dict[str, Any] = Field(default_factory=dict)
    upload: dict[str, Any] = Field(default_factory=dict)
    ros: dict[str, Any] = Field(default_factory=dict)
    ui_state: dict[str, Any] = Field(default_factory=dict)


class CollectionConfigDraft(DatasetConfigDraft):
    """Backward-compatible name for older V2-style dataset config payloads."""


class ConfigPreview(BaseModel):
    summary: str
    warnings: list[str] = Field(default_factory=list)
    dataset_summary: str = ""
