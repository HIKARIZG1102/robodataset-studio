from __future__ import annotations

from pydantic import BaseModel, Field


class ProjectCreateRequest(BaseModel):
    name: str = Field(default="")
    version: str = Field(default="v1")
    operator: str = Field(default="")
    notes: str = Field(default="")
    root_path: str = Field(default="")
    config_id: str = Field(default="")


class ProjectSummary(BaseModel):
    key: str
    name: str
    version: str
    path: str
    config_id: str = ""
    has_recorded_data: bool = False


class ProjectConfigBindRequest(BaseModel):
    config_id: str = Field(default="")


class ProjectOpenPathRequest(BaseModel):
    path: str = Field(default="")
