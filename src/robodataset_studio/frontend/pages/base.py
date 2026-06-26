from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from robodataset_studio.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio.frontend.worker import ApiWorker


class BasePage(QWidget):
    def __init__(self, title: str, api: ApiClient, project: ProjectSummary | None = None) -> None:
        super().__init__()
        self.api = api
        self.project = project
        self.pool = QThreadPool.globalInstance()
        self._workers: list[ApiWorker] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.content = QWidget()
        self.content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.layout = QVBoxLayout(self.content)
        self.layout.setContentsMargins(8, 8, 8, 8)
        self.title = QLabel(title)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.status = QLabel("")
        self.layout.addWidget(self.title)
        self.scroll.setWidget(self.content)
        root.addWidget(self.scroll)

    def finish_layout(self) -> None:
        self.layout.addWidget(self.output)
        self.layout.addWidget(self.status)

    def show_result(self, result: Any, status: str = "Done") -> None:
        self.output.setPlainText(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        self.status.setText(status)

    def show_error(self, exc: Exception) -> None:
        self.status.setText(f"Error: {exc}")

    def project_key(self) -> str:
        return self.project.key if self.project is not None else ""

    def run_async(self, fn, callback, *args, **kwargs) -> None:
        worker = ApiWorker(fn, *args, **kwargs)
        self._workers.append(worker)

        def finish(result: object, error: object, item: ApiWorker = worker) -> None:
            try:
                callback(result, error)
            finally:
                if item in self._workers:
                    self._workers.remove(item)

        worker.signals.finished.connect(finish, Qt.QueuedConnection)
        self.pool.start(worker)

    def finish_async_result(self, result: object, error: object, status: str) -> None:
        if error is not None:
            self.show_error(error if isinstance(error, Exception) else Exception(str(error)))
            return
        self.show_result(result, status)
