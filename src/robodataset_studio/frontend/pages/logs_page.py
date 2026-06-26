from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QSplitter, QVBoxLayout, QWidget

from robodataset_studio.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio.frontend.pages.base import BasePage


class LogsPage(BasePage):
    def __init__(self, api: ApiClient, project: ProjectSummary | None = None) -> None:
        super().__init__("Logs / Tasks", api, project)
        self.items = QListWidget()
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.items.currentItemChanged.connect(lambda item, _prev: self.show_item(item))
        self._entries: list[dict[str, Any]] = []
        self._build()
        self.refresh()

    def _build(self) -> None:
        buttons = QHBoxLayout()
        refresh = QPushButton("Refresh Tasks")
        refresh.clicked.connect(self.refresh)
        buttons.addWidget(refresh)
        buttons.addStretch(1)

        splitter = QSplitter(Qt.Horizontal)
        list_panel = QWidget()
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.addWidget(QLabel("Tasks and log files"))
        list_layout.addWidget(self.items)
        detail_panel = QWidget()
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.addWidget(QLabel("Selected log"))
        detail_layout.addWidget(self.detail)
        splitter.addWidget(list_panel)
        splitter.addWidget(detail_panel)
        splitter.setSizes([380, 820])

        self.layout.addLayout(buttons)
        self.layout.addWidget(splitter, 1)
        self.finish_layout()

    def on_project_config_changed(self, project: ProjectSummary | None) -> None:
        self.project = project
        self.refresh()

    def refresh(self) -> None:
        self.items.clear()
        self._entries = []
        try:
            tasks = self.api.list_tasks()
        except Exception as exc:
            self.show_error(exc)
            tasks = []
        for task in tasks:
            if not isinstance(task, dict):
                continue
            self._add_entry(
                {
                    "kind": "task",
                    "title": f"task | {task.get('status', '-')} | {task.get('kind', 'task')} | {task.get('task_id', '-')}",
                    "payload": task,
                }
            )
        for path in self._project_log_files():
            label = path.name
            try:
                if self.project is not None:
                    label = str(path.relative_to(Path(self.project.path)))
            except ValueError:
                pass
            self._add_entry({"kind": "file", "title": f"file | {label}", "path": str(path)})
        self.show_result({"tasks": len(tasks), "log_files": sum(1 for entry in self._entries if entry.get("kind") == "file")}, "Logs refreshed")
        if self.items.count():
            self.items.setCurrentRow(0)
        else:
            self.detail.setPlainText("No runtime tasks or project log files found. Task archive may have been cleared from Settings > Maintenance.")

    def select_task(self, task_id: str) -> None:
        for row, entry in enumerate(self._entries):
            task = entry.get("payload", {}) if entry.get("kind") == "task" else {}
            if isinstance(task, dict) and str(task.get("task_id") or "") == task_id:
                self.items.setCurrentRow(row)
                return

    def _add_entry(self, entry: dict[str, Any]) -> None:
        row = len(self._entries)
        self._entries.append(entry)
        item = QListWidgetItem(str(entry.get("title") or "log"))
        item.setData(Qt.UserRole, row)
        self.items.addItem(item)

    def show_item(self, item: QListWidgetItem | None) -> None:
        if item is None:
            self.detail.clear()
            return
        row = int(item.data(Qt.UserRole) or -1)
        if row < 0 or row >= len(self._entries):
            self.detail.clear()
            return
        entry = self._entries[row]
        if entry.get("kind") == "task":
            task = entry.get("payload", {})
            if isinstance(task, dict):
                lines = [
                    f"task_id: {task.get('task_id', '')}",
                    f"kind: {task.get('kind', '')}",
                    f"status: {task.get('status', '')}",
                    f"message: {task.get('message', '')}",
                    f"progress: {task.get('progress', '')}",
                    f"created_at: {task.get('created_at', '')}",
                    f"started_at: {task.get('started_at', '')}",
                    f"ended_at: {task.get('ended_at', '')}",
                    "",
                    "logs:",
                    *[str(line) for line in task.get("logs", []) if line is not None],
                    "",
                    "result:",
                    json.dumps(task.get("result", {}), ensure_ascii=False, indent=2, default=str),
                ]
                if task.get("error"):
                    lines.extend(["", "error:", str(task.get("error"))])
                self.detail.setPlainText("\n".join(lines))
            return
        if entry.get("kind") == "file":
            path = Path(str(entry.get("path") or ""))
            if not path.exists() or not path.is_file():
                self.detail.setPlainText(f"Log file not found: {path}")
                return
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                self.detail.setPlainText(f"Cannot read log file:\n{exc}")
                return
            if len(content) > 50000:
                content = content[-50000:]
                content = "[tail 50000 chars]\n" + content
            self.detail.setPlainText(f"path: {path}\n\n{content}")

    def _project_log_files(self) -> list[Path]:
        if self.project is None:
            return []
        root = Path(self.project.path)
        candidates: list[Path] = []
        for folder in [root / "logs", root / "review", root / "exports"]:
            if not folder.exists():
                continue
            for path in folder.rglob("*"):
                if path.is_file() and path.suffix.lower() in {".log", ".txt", ".json", ".yaml", ".yml"}:
                    candidates.append(path)
        return sorted(candidates, key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)[:300]
