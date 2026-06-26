from __future__ import annotations

from datetime import datetime
from itertools import count
import json
import shutil
from pathlib import Path
from typing import Any

from robodataset_studio.models.task import TaskRecord


class TaskService:
    def __init__(self, archive_path: Path | None = None) -> None:
        self._tasks: dict[str, TaskRecord] = {}
        self._cancel_callbacks: dict[str, Any] = {}
        self._counter = count(1)
        self.archive_path = archive_path or Path.home() / ".config" / "robodataset-studio" / "task_archive.jsonl"

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
        self._archive_task(task)
        return task

    def fail_task(self, task_id: str, *, message: str = "", error: str = "") -> TaskRecord:
        task = self._require_task(task_id)
        task.status = "failed"
        task.message = message or task.message
        task.error = error
        task.ended_at = datetime.now()
        if error:
            task.logs.append(f"error: {error}")
        self._archive_task(task)
        return task

    def cancel_task(self, task_id: str) -> TaskRecord:
        task = self._require_task(task_id)
        callback = self._cancel_callbacks.get(task_id)
        if callable(callback):
            try:
                callback()
            except Exception as exc:
                task.logs.append(f"cancel callback failed: {exc}")
        task.status = "cancelled"
        task.message = "cancelled"
        task.ended_at = datetime.now()
        self._archive_task(task)
        return task

    def add_log(self, task_id: str, line: str) -> TaskRecord:
        task = self._require_task(task_id)
        task.logs.append(line)
        if len(task.logs) > 1500:
            task.logs = task.logs[-1500:]
        return task

    def register_cancel_callback(self, task_id: str, callback: Any) -> None:
        self._cancel_callbacks[task_id] = callback

    def clear_cancel_callback(self, task_id: str) -> None:
        self._cancel_callbacks.pop(task_id, None)

    def is_cancelled(self, task_id: str) -> bool:
        task = self.get_task(task_id)
        return bool(task and task.status == "cancelled")

    def run_instant(self, kind: str, message: str, result: dict[str, Any]) -> TaskRecord:
        task = self.create_task(kind, message)
        task.logs.append(message)
        return self.complete_task(task.task_id, message=message, result=result)

    def clear_runtime_cache(self) -> dict[str, Any]:
        task_count = len(self._tasks)
        self._tasks.clear()
        self._cancel_callbacks.clear()
        removed_paths: list[str] = []
        removed_bytes = 0
        for path in [Path("/tmp/robodataset_ros_logs"), Path("/tmp/robodataset_inspector_display_frame.png")]:
            size = self._path_size(path)
            if not path.exists():
                continue
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            removed_paths.append(str(path))
            removed_bytes += size
        archive = self.archive_summary()
        if self.archive_path.exists():
            self.archive_path.unlink()
        return {
            "cleared_runtime_tasks": task_count,
            "cleared_archive_records": archive.get("records", 0),
            "cleared_archive_bytes": archive.get("size_bytes", 0),
            "removed_paths": removed_paths,
            "removed_bytes": removed_bytes,
            "archive_path": str(self.archive_path),
            "archive_preserved": False,
        }

    def archive_summary(self) -> dict[str, Any]:
        count = 0
        by_status: dict[str, int] = {}
        if self.archive_path.exists():
            with self.archive_path.open("r", encoding="utf-8") as file:
                for line in file:
                    count += 1
                    try:
                        status = str(json.loads(line).get("status") or "unknown")
                    except Exception:
                        status = "unreadable"
                    by_status[status] = by_status.get(status, 0) + 1
        return {
            "path": str(self.archive_path),
            "exists": self.archive_path.exists(),
            "records": count,
            "by_status": by_status,
            "size_bytes": self.archive_path.stat().st_size if self.archive_path.exists() else 0,
        }

    def _require_task(self, task_id: str) -> TaskRecord:
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        return task

    def _archive_task(self, task: TaskRecord) -> None:
        self.archive_path.parent.mkdir(parents=True, exist_ok=True)
        if hasattr(task, "model_dump"):
            payload = task.model_dump(mode="json")
        else:
            payload = task.dict()
        payload["archived_at"] = datetime.now().isoformat()
        with self.archive_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")

    def _path_size(self, path: Path) -> int:
        try:
            if path.is_file():
                return path.stat().st_size
            if path.is_dir():
                return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
        except Exception:
            return 0
        return 0


task_service = TaskService()
