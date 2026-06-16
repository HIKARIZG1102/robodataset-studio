from __future__ import annotations

from PySide6.QtWidgets import QPushButton

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio_v3.frontend.pages.base import BasePage


class LogsPage(BasePage):
    def __init__(self, api: ApiClient, project: ProjectSummary | None = None) -> None:
        super().__init__("Logs / Tasks", api, project)
        refresh = QPushButton("Refresh Tasks")
        refresh.clicked.connect(self.refresh)
        self.layout.addWidget(refresh)
        self.finish_layout()
        self.refresh()

    def refresh(self) -> None:
        try:
            self.show_result(self.api.list_tasks(), "Tasks refreshed")
        except Exception as exc:
            self.show_error(exc)
