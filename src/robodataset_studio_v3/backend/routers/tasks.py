from __future__ import annotations

from fastapi import APIRouter

from robodataset_studio_v3.models.task import TaskRecord
from robodataset_studio_v3.services.task_service import TaskService

router = APIRouter()
service = TaskService()


@router.get("", response_model=list[TaskRecord])
def list_tasks() -> list[TaskRecord]:
    return service.list_tasks()
