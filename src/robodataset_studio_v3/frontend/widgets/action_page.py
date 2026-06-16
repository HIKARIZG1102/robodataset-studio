from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QLineEdit, QPushButton, QPlainTextEdit, QVBoxLayout, QWidget

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary


class ActionPage(QWidget):
    def __init__(
        self,
        title: str,
        api: ApiClient,
        project: ProjectSummary | None = None,
        actions: dict[str, Callable[[dict[str, str]], Any]] | None = None,
        fields: dict[str, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.api = api
        self.project = project
        self.actions = actions or {}
        self.inputs: dict[str, QLineEdit] = {}
        self.action_box = QComboBox()
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.status = QLabel("")
        self._build(title, fields or {})

    def _build(self, title: str, fields: dict[str, str]) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(title))
        form = QFormLayout()
        for key, value in fields.items():
            line = QLineEdit(value)
            self.inputs[key] = line
            form.addRow(key, line)
        if self.project is not None and "project_key" not in self.inputs:
            line = QLineEdit(self.project.key)
            self.inputs["project_key"] = line
            form.addRow("project_key", line)
        self.action_box.addItems(list(self.actions.keys()))
        run = QPushButton("Run")
        run.clicked.connect(self.run_action)
        form.addRow("action", self.action_box)
        form.addRow(run)
        layout.addLayout(form)
        layout.addWidget(self.output)
        layout.addWidget(self.status)

    def values(self) -> dict[str, str]:
        return {key: line.text().strip() for key, line in self.inputs.items()}

    def run_action(self) -> None:
        action_name = self.action_box.currentText()
        action = self.actions.get(action_name)
        if action is None:
            self.status.setText("No action selected")
            return
        try:
            result = action(self.values())
        except Exception as exc:
            self.status.setText(f"Action failed: {exc}")
            return
        self.output.setPlainText(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        self.status.setText(f"Completed: {action_name}")
