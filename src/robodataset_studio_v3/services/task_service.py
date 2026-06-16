from __future__ import annotations

from robodataset_studio_v3.models.task import TaskRecord


class TaskService:
    def __init__(self) -> None:
        self._tasks: list[TaskRecord] = []

    def list_tasks(self) -> list[TaskRecord]:
        return list(self._tasks)
