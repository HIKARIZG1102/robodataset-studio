from __future__ import annotations

from datetime import datetime
from itertools import count
from typing import Any

from robodataset_studio_v3.models.task import TaskRecord


class TaskService:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {}
        self._counter = count(1)

    def list_tasks(self) -> list[TaskRecord]:
        return list(self._tasks.values())

    def get_task(self, task_id: str) -> TaskRecord | None:
        return self._tasks.get(task_id)

    def create_task(self, kind: str, message: str = "") -> TaskRecord:
        task_id = f"{kind}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{next(self._counter):04d}"
        task = TaskRecord(task_id=task_id, kind=kind, status="running", message=message, started_at=datetime.now())
        self._tasks[task_id] = task
        return task

    def complete_task(self, task_id: str, *, message: str = "", result: dict[str, Any] | None = None) -> TaskRecord:
        task = self._require_task(task_id)
        task.status = "done"
        task.progress = 1.0
        task.message = message or task.message
        task.result = result or task.result
        task.ended_at = datetime.now()
        return task

    def fail_task(self, task_id: str, *, message: str = "", error: str = "") -> TaskRecord:
        task = self._require_task(task_id)
        task.status = "failed"
        task.message = message or task.message
        task.error = error
        task.ended_at = datetime.now()
        return task

    def cancel_task(self, task_id: str) -> TaskRecord:
        task = self._require_task(task_id)
        task.status = "cancelled"
        task.message = "cancelled"
        task.ended_at = datetime.now()
        return task

    def add_log(self, task_id: str, line: str) -> TaskRecord:
        task = self._require_task(task_id)
        task.logs.append(line)
        return task

    def run_instant(self, kind: str, message: str, result: dict[str, Any]) -> TaskRecord:
        task = self.create_task(kind, message)
        task.logs.append(message)
        return self.complete_task(task.task_id, message=message, result=result)

    def _require_task(self, task_id: str) -> TaskRecord:
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        return task


task_service = TaskService()
