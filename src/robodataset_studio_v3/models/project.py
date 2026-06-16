from __future__ import annotations

from pydantic import BaseModel, Field


class ProjectCreateRequest(BaseModel):
    name: str = Field(default="")
    version: str = Field(default="v1")
    operator: str = Field(default="")
    notes: str = Field(default="")
    root_path: str = Field(default="")


class ProjectSummary(BaseModel):
    key: str
    name: str
    version: str
    path: str


class ProjectOpenPathRequest(BaseModel):
    path: str = Field(default="")
