from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QFormLayout, QHBoxLayout, QLabel, QPushButton

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio_v3.frontend.pages.base import BasePage


class CollectPage(BasePage):
    def __init__(self, api: ApiClient, project: ProjectSummary) -> None:
        super().__init__(f"Collect - {project.key}", api, project)
        self.mode = QComboBox()
        self.mode.addItems(["manual", "duration_sec", "sample_count"])
        form = QFormLayout()
        form.addRow("Recording mode", self.mode)
        buttons = QHBoxLayout()
        for label, handler in [
            ("Preflight", self.preflight),
            ("Start Recording", self.start_recording),
            ("Stop Recording", self.stop_recording),
            ("Refresh Plan", self.refresh_plan),
        ]:
            button = QPushButton(label)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        self.layout.addLayout(form)
        self.layout.addLayout(buttons)
        self.layout.addWidget(QLabel("Recording uses the current project_config.yaml and writes a dataset_config snapshot into each session."))
        self.finish_layout()

    def refresh_plan(self) -> None:
        try:
            config = self.api.get_project_config(self.project_key())
            preview = self.api.post("/api/config/project/preview", config)
            self.show_result(preview, "Plan refreshed")
        except Exception as exc:
            self.show_error(exc)

    def preflight(self) -> None:
        try:
            self.show_result(self.api.post("/api/recording/preflight", {"project_key": self.project_key()}), "Preflight complete")
        except Exception as exc:
            self.show_error(exc)

    def start_recording(self) -> None:
        try:
            self.show_result(
                self.api.post("/api/recording/start", {"project_key": self.project_key(), "mode": self.mode.currentText()}),
                "Recording started",
            )
        except Exception as exc:
            self.show_error(exc)

    def stop_recording(self) -> None:
        try:
            self.show_result(self.api.post("/api/recording/stop", {"project_key": self.project_key()}), "Recording stopped")
        except Exception as exc:
            self.show_error(exc)
