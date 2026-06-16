from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLineEdit, QPushButton

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio_v3.frontend.pages.base import BasePage


class ReviewPage(BasePage):
    def __init__(self, api: ApiClient, project: ProjectSummary | None = None) -> None:
        super().__init__("Review", api, project)
        self.session_dir = QLineEdit()
        self.hdf5_path = QLineEdit()
        self.folder = QLineEdit()
        form = QFormLayout()
        form.addRow("Session dir", self.session_dir)
        form.addRow("HDF5 file", self.hdf5_path)
        form.addRow("Layout folder", self.folder)
        buttons = QHBoxLayout()
        for label, handler in [
            ("Scan Session", self.scan_session),
            ("Check Session", self.check_session),
            ("Check HDF5", self.check_hdf5),
            ("Check Layout", self.check_layout),
        ]:
            button = QPushButton(label)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        self.layout.addLayout(form)
        self.layout.addLayout(buttons)
        self.finish_layout()

    def scan_session(self) -> None:
        self._post("/api/review/session/scan", {"session_dir": self.session_dir.text().strip()}, "Session scanned")

    def check_session(self) -> None:
        self._post("/api/review/session/check", {"session_dir": self.session_dir.text().strip()}, "Session checked")

    def check_hdf5(self) -> None:
        self._post("/api/review/hdf5/check", {"hdf5_path": self.hdf5_path.text().strip()}, "HDF5 checked")

    def check_layout(self) -> None:
        self._post("/api/review/layout/check", {"folder": self.folder.text().strip()}, "Layout checked")

    def _post(self, path: str, payload: dict, status: str) -> None:
        try:
            self.show_result(self.api.post(path, payload), status)
        except Exception as exc:
            self.show_error(exc)
