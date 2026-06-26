from __future__ import annotations

from fastapi import APIRouter, HTTPException

from robodataset_studio.models.task import TaskRecord
from robodataset_studio.services.task_service import task_service

router = APIRouter()


@router.get("", response_model=list[TaskRecord])
def list_tasks() -> list[TaskRecord]:
    return task_service.list_tasks()


@router.get("/{task_id}", response_model=TaskRecord)
def get_task(task_id: str) -> TaskRecord:
    task = task_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"task not found: {task_id}")
    return task


@router.post("/{task_id}/cancel", response_model=TaskRecord)
def cancel_task(task_id: str) -> TaskRecord:
    try:
        return task_service.cancel_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"task not found: {task_id}") from exc
