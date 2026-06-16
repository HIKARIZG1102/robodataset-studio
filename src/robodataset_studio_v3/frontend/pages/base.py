from __future__ import annotations

import json
from typing import Any

from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary


class BasePage(QWidget):
    def __init__(self, title: str, api: ApiClient, project: ProjectSummary | None = None) -> None:
        super().__init__()
        self.api = api
        self.project = project
        self.layout = QVBoxLayout(self)
        self.title = QLabel(title)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.status = QLabel("")
        self.layout.addWidget(self.title)

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
