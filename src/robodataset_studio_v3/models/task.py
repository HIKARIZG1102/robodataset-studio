from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TaskRecord(BaseModel):
    task_id: str
    kind: str
    status: str = "queued"
    message: str = ""
    progress: float = 0.0
    created_at: datetime = Field(default_factory=datetime.now)
