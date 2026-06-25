from __future__ import annotations

import yaml
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QPlainTextEdit, QScrollArea, QSizePolicy, QTabWidget, QVBoxLayout, QWidget

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary


class ProjectConfigPage(QWidget):
    projectConfigChanged = Signal(object)

    def __init__(self, api: ApiClient, project: ProjectSummary, parent: QWidget | None = None, *, read_only: bool = False) -> None:
        super().__init__(parent)
        self.api = api
        self.project = project
        self.read_only = read_only
        self.config_select = QComboBox()
        self.configs: list[dict] = []
        self.project_yaml = QPlainTextEdit()
        self.dataset_yaml = QPlainTextEdit()
        self.preview_output = QPlainTextEdit()
        self.preview_output.setReadOnly(True)
        self.preview_output.setMaximumHeight(180)
        self.status = QLabel("")
        self._build()
        self.refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(content)
        self.title = QLabel(self._title_text())
        refresh = QPushButton("Refresh From Project")
        refresh.clicked.connect(self.refresh)
        refresh_library = QPushButton("Refresh Library")
        refresh_library.clicked.connect(self.refresh_library)
        load_config = QPushButton("Load Config Into Project")
        load_config.clicked.connect(self.load_config_into_project)
        preview = QPushButton("Validate Preview")
        preview.clicked.connect(self.preview)
        save = QPushButton("Save Project Config")
        save.clicked.connect(self.save)
        self.project_yaml.setReadOnly(self.read_only)
        self.dataset_yaml.setReadOnly(True)

        tabs = QTabWidget()
        tabs.addTab(self.project_yaml, "project_config.yaml")
        tabs.addTab(self.dataset_yaml, "dataset_config.yaml")

        buttons = QHBoxLayout()
        if not self.read_only:
            buttons.addWidget(QLabel("Library config"))
            buttons.addWidget(self.config_select, 2)
            buttons.addWidget(refresh_library)
            buttons.addWidget(load_config)
        buttons.addWidget(refresh)
        buttons.addWidget(preview)
        if not self.read_only:
            buttons.addWidget(save)

        layout.addWidget(self.title)
        layout.addLayout(buttons)
        layout.addWidget(tabs)
        layout.addWidget(QLabel("Preview result"))
        layout.addWidget(self.preview_output)
        layout.addWidget(self.status)
        scroll.setWidget(content)
        root.addWidget(scroll)

    def refresh_library(self) -> None:
        try:
            self.configs = self.api.list_configs()
        except Exception as exc:
            self.status.setText(f"Cannot list configs: {exc}")
            return
        current = self.project.config_id
        self.config_select.blockSignals(True)
        self.config_select.clear()
        for config in self.configs:
            config_id = str(config.get("id") or "")
            name = str(config.get("name") or config_id)
            streams = config.get("stream_count", "")
            self.config_select.addItem(f"{name} [{config_id}] - {streams} streams", config_id)
        if current:
            index = self.config_select.findData(current)
            if index >= 0:
                self.config_select.setCurrentIndex(index)
        self.config_select.blockSignals(False)

    def on_project_config_changed(self, project: ProjectSummary | None) -> None:
        if project is not None:
            self.project = project
        self.title.setText(self._title_text())
        self.refresh()

    def _title_text(self) -> str:
        return f"Project Config: {self.project.key}" + (" (read only)" if self.read_only else "")

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
        if not self.read_only:
            self.refresh_library()

    def load_config_into_project(self) -> None:
        if self.read_only:
            self.status.setText("Project config is read only in this view.")
            return
        config_id = str(self.config_select.currentData() or "")
        if not config_id:
            QMessageBox.information(self, "Load Config", "Select a library config first.")
            return
        if self.project.has_recorded_data and config_id != self.project.config_id:
            QMessageBox.warning(
                self,
                "Load Config",
                "This project already has recorded data. You can reload the current library config, but create a new project version before switching to another config.",
            )
            return
        try:
            self.project = self.api.bind_project_config(self.project.key, config_id)
        except Exception as exc:
            self.status.setText(f"Cannot load config into project: {exc}")
            return
        self.status.setText(f"Loaded config into project: {config_id}")
        self.projectConfigChanged.emit(self.project)
        self.refresh()

    def preview(self) -> None:
        try:
            project_config = self._project_config_from_text()
            result = self.api.post("/api/config/project/preview", project_config)
        except Exception as exc:
            self.status.setText(f"Cannot preview config: {exc}")
            self.preview_output.setPlainText("")
            return
        self.preview_output.setPlainText(yaml.safe_dump(result, sort_keys=False, allow_unicode=True))
        self.status.setText("Preview generated")

    def save(self) -> None:
        if self.read_only:
            self.status.setText("Project config is read only in this view.")
            return
        if self.project.has_recorded_data:
            QMessageBox.warning(
                self,
                "Project Config",
                "This project already has recorded data. Create a new project version before changing its config.",
            )
            return
        try:
            project_config = self._project_config_from_text()
            result = self.api.put(f"/api/config/project/{self.project.key}", project_config)
        except Exception as exc:
            self.status.setText(f"Cannot save config: {exc}")
            return
        self.status.setText(str(result))
        self.projectConfigChanged.emit(self.project)
        self.refresh()

    def _project_config_from_text(self) -> dict:
        data = yaml.safe_load(self.project_yaml.toPlainText())
        if not isinstance(data, dict):
            raise ValueError("project_config.yaml must be a mapping")
        return data
