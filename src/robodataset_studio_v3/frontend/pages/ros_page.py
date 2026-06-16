from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLineEdit, QPushButton

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio_v3.frontend.pages.base import BasePage


class RosPage(BasePage):
    def __init__(self, api: ApiClient, project: ProjectSummary | None = None) -> None:
        super().__init__("ROS Discovery / Topic Inspector", api, project)
        self.topic = QLineEdit()
        form = QFormLayout()
        form.addRow("Topic", self.topic)
        buttons = QHBoxLayout()
        for label, handler in [
            ("Discover Graph", self.graph),
            ("Topic Info", self.topic_info),
            ("Echo Once", self.echo_once),
            ("Hz Check", self.hz),
        ]:
            button = QPushButton(label)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        self.layout.addLayout(form)
        self.layout.addLayout(buttons)
        self.finish_layout()

    def graph(self) -> None:
        try:
            self.show_result(self.api.get("/api/ros/graph", timeout=10.0), "ROS graph refreshed")
        except Exception as exc:
            self.show_error(exc)

    def topic_info(self) -> None:
        self._topic_action("/api/ros/topic-info", "Topic info complete")

    def echo_once(self) -> None:
        self._topic_action("/api/ros/topic-echo-once", "Echo complete")

    def hz(self) -> None:
        self._topic_action("/api/ros/topic-hz", "Hz check complete")

    def _topic_action(self, path: str, status: str) -> None:
        try:
            self.show_result(self.api.post(path, {"topic": self.topic.text().strip()}, timeout=12.0), status)
        except Exception as exc:
            self.show_error(exc)
