from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QFormLayout, QHBoxLayout, QLineEdit, QPushButton, QWidget

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
        form.addRow("Local file/folder", self._local_path_row())
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
        self.status.setText("Checking dependencies...")
        self.run_async(self.api.get, lambda result, error: self.finish_async_result(result, error, "Dependencies checked"), "/api/upload/dependencies", timeout=20.0)

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
        self.status.setText(f"{status}...")
        self.run_async(self.api.post, lambda result, error: self.finish_async_result(result, error, status), path, payload, timeout=180.0)

    def browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select local file", self.local_path.text().strip())
        if path:
            self.local_path.setText(path)

    def browse_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select local folder", self.local_path.text().strip())
        if path:
            self.local_path.setText(path)

    def _local_path_row(self) -> QWidget:
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        file_button = QPushButton("File")
        folder_button = QPushButton("Folder")
        file_button.clicked.connect(self.browse_file)
        folder_button.clicked.connect(self.browse_folder)
        row.addWidget(self.local_path)
        row.addWidget(file_button)
        row.addWidget(folder_button)
        return widget
