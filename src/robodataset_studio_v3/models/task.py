from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TaskRecord(BaseModel):
    task_id: str
    kind: str
    status: str = "queued"
    message: str = ""
    progress: float = 0.0
    logs: list[str] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: datetime | None = None
    ended_at: datetime | None = None
