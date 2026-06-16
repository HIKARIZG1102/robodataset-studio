from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLineEdit, QPushButton

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio_v3.frontend.pages.base import BasePage


class ConvertPage(BasePage):
    def __init__(self, api: ApiClient, project: ProjectSummary | None = None) -> None:
        super().__init__("Convert", api, project)
        self.root = QLineEdit()
        self.sessions = QLineEdit()
        self.output_dir = QLineEdit()
        form = QFormLayout()
        form.addRow("Raw sessions root", self.root)
        form.addRow("Selected sessions, comma separated", self.sessions)
        form.addRow("Output dir", self.output_dir)
        buttons = QHBoxLayout()
        for label, handler in [("Scan Sessions", self.scan), ("Merge Sessions", self.merge), ("Convert To HDF5", self.hdf5)]:
            button = QPushButton(label)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        self.layout.addLayout(form)
        self.layout.addLayout(buttons)
        self.finish_layout()

    def scan(self) -> None:
        try:
            self.show_result(self.api.post("/api/convert/scan", {"root": self.root.text().strip()}), "Sessions scanned")
        except Exception as exc:
            self.show_error(exc)

    def merge(self) -> None:
        self._convert("/api/convert/merge", "Merge task created")

    def hdf5(self) -> None:
        self._convert("/api/convert/hdf5", "HDF5 task created")

    def _convert(self, path: str, status: str) -> None:
        payload = {"sessions": self._split_csv(self.sessions.text()), "output_dir": self.output_dir.text().strip()}
        try:
            self.show_result(self.api.post(path, payload), status)
        except Exception as exc:
            self.show_error(exc)

    def _split_csv(self, value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip()]
