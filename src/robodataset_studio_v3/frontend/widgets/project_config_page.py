from __future__ import annotations

import yaml
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QPlainTextEdit, QTabWidget, QVBoxLayout, QWidget

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary


class ProjectConfigPage(QWidget):
    def __init__(self, api: ApiClient, project: ProjectSummary, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.api = api
        self.project = project
        self.project_yaml = QPlainTextEdit()
        self.dataset_yaml = QPlainTextEdit()
        self.status = QLabel("")
        self._build()
        self.refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel(f"Project Config: {self.project.key}")
        refresh = QPushButton("Refresh From Project")
        refresh.clicked.connect(self.refresh)
        preview = QPushButton("Preview")
        preview.clicked.connect(self.preview)
        save = QPushButton("Save Project Config")
        save.clicked.connect(self.save)

        tabs = QTabWidget()
        tabs.addTab(self.project_yaml, "project_config.yaml")
        tabs.addTab(self.dataset_yaml, "dataset_config.yaml")

        buttons = QHBoxLayout()
        buttons.addWidget(refresh)
        buttons.addWidget(preview)
        buttons.addWidget(save)

        layout.addWidget(title)
        layout.addLayout(buttons)
        layout.addWidget(tabs)
        layout.addWidget(self.status)

    def refresh(self) -> None:
        try:
            project_config = self.api.get_project_config(self.project.key)
            dataset_config = self.api.get_dataset_config(self.project.key)
        except Exception as exc:
            self.status.setText(f"Cannot load config: {exc}")
            return
        self.project_yaml.setPlainText(yaml.safe_dump(project_config, sort_keys=False, allow_unicode=True))
        self.dataset_yaml.setPlainText(yaml.safe_dump(dataset_config, sort_keys=False, allow_unicode=True))
        self.status.setText("Loaded project_config.yaml and dataset_config.yaml")

    def preview(self) -> None:
        try:
            project_config = self._project_config_from_text()
            result = self.api.post("/api/config/project/preview", project_config)
        except Exception as exc:
            self.status.setText(f"Cannot preview config: {exc}")
            return
        self.status.setText(str(result))

    def save(self) -> None:
        try:
            project_config = self._project_config_from_text()
            result = self.api.put(f"/api/config/project/{self.project.key}", project_config)
        except Exception as exc:
            self.status.setText(f"Cannot save config: {exc}")
            return
        self.status.setText(str(result))
        self.refresh()

    def _project_config_from_text(self) -> dict:
        data = yaml.safe_load(self.project_yaml.toPlainText())
        if not isinstance(data, dict):
            raise ValueError("project_config.yaml must be a mapping")
        return data
