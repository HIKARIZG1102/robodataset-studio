from __future__ import annotations

import yaml
from PySide6.QtWidgets import QHBoxLayout, QPushButton

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio_v3.frontend.pages.base import BasePage


class SettingsPage(BasePage):
    def __init__(self, api: ApiClient, project: ProjectSummary | None = None) -> None:
        super().__init__("Settings", api, project)
        self.output.setReadOnly(False)
        buttons = QHBoxLayout()
        load = QPushButton("Load Settings")
        save = QPushButton("Save Settings")
        load.clicked.connect(self.load)
        save.clicked.connect(self.save)
        buttons.addWidget(load)
        buttons.addWidget(save)
        self.layout.addLayout(buttons)
        self.finish_layout()
        self.load()

    def load(self) -> None:
        try:
            result = self.api.get("/api/settings")
            self.output.setPlainText(yaml.safe_dump(result, sort_keys=False, allow_unicode=True))
            self.status.setText("Settings loaded")
        except Exception as exc:
            self.show_error(exc)

    def save(self) -> None:
        try:
            settings = yaml.safe_load(self.output.toPlainText())
            if not isinstance(settings, dict):
                raise ValueError("settings must be a mapping")
            self.show_result(self.api.put("/api/settings", settings), "Settings saved")
        except Exception as exc:
            self.show_error(exc)
