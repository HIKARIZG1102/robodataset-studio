from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLineEdit, QPushButton

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio_v3.frontend.pages.base import BasePage


class UploadPage(BasePage):
    def __init__(self, api: ApiClient, project: ProjectSummary | None = None) -> None:
        super().__init__("Upload", api, project)
        self.local_path = QLineEdit()
        self.remote_path = QLineEdit()
        self.host = QLineEdit()
        self.username = QLineEdit()
        form = QFormLayout()
        form.addRow("Local file/folder", self.local_path)
        form.addRow("Remote path", self.remote_path)
        form.addRow("Host", self.host)
        form.addRow("Username", self.username)
        buttons = QHBoxLayout()
        for label, handler in [
            ("Check Dependencies", self.dependencies),
            ("Connect", self.connect),
            ("Upload", self.upload),
            ("Repair / Resume", self.repair),
            ("Verify", self.verify),
        ]:
            button = QPushButton(label)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        self.layout.addLayout(form)
        self.layout.addLayout(buttons)
        self.finish_layout()

    def payload(self) -> dict[str, str]:
        return {
            "local_path": self.local_path.text().strip(),
            "remote_path": self.remote_path.text().strip(),
            "host": self.host.text().strip(),
            "username": self.username.text().strip(),
        }

    def dependencies(self) -> None:
        try:
            self.show_result(self.api.get("/api/upload/dependencies"), "Dependencies checked")
        except Exception as exc:
            self.show_error(exc)

    def connect(self) -> None:
        data = self.payload()
        self._post("/api/upload/connect", {"host": data["host"], "username": data["username"]}, "Profile checked")

    def upload(self) -> None:
        self._post("/api/upload/start", self.payload(), "Upload task created")

    def repair(self) -> None:
        self._post("/api/upload/repair", self.payload(), "Repair task created")

    def verify(self) -> None:
        self._post("/api/upload/verify", self.payload(), "Verify task created")

    def _post(self, path: str, payload: dict, status: str) -> None:
        try:
            self.show_result(self.api.post(path, payload), status)
        except Exception as exc:
            self.show_error(exc)
