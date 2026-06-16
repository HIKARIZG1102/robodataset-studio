from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QFormLayout, QHBoxLayout, QLineEdit, QPushButton, QWidget

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio_v3.frontend.pages.base import BasePage


class ConvertPage(BasePage):
    def __init__(self, api: ApiClient, project: ProjectSummary | None = None) -> None:
        super().__init__("Convert", api, project)
        self.root = QLineEdit()
        self.sessions = QLineEdit()
        self.output_dir = QLineEdit()
        form = QFormLayout()
        form.addRow("Raw sessions root", self._path_row(self.root, self.browse_root))
        form.addRow("Selected sessions, comma separated", self.sessions)
        form.addRow("Output dir", self._path_row(self.output_dir, self.browse_output))
        buttons = QHBoxLayout()
        for label, handler in [("Scan Sessions", self.scan), ("Merge Sessions", self.merge), ("Convert To HDF5", self.hdf5)]:
            button = QPushButton(label)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        self.layout.addLayout(form)
        self.layout.addLayout(buttons)
        self.finish_layout()

    def scan(self) -> None:
        self.status.setText("Scanning sessions...")
        self.run_async(self.api.post, self._finish_scan, "/api/convert/scan", {"root": self.root.text().strip()}, timeout=60.0)

    def _finish_scan(self, result: object, error: object) -> None:
        if error is not None:
            self.show_error(error if isinstance(error, Exception) else Exception(str(error)))
            return
        if isinstance(result, dict):
            sessions = result.get("sessions", [])
            if isinstance(sessions, list):
                self.sessions.setText(", ".join(str(item) for item in sessions))
        self.show_result(result, "Sessions scanned")

    def merge(self) -> None:
        self._convert("/api/convert/merge", "Merge task created")

    def hdf5(self) -> None:
        self._convert("/api/convert/hdf5", "HDF5 task created")

    def _convert(self, path: str, status: str) -> None:
        payload = {"sessions": self._split_csv(self.sessions.text()), "output_dir": self.output_dir.text().strip()}
        self.status.setText(f"{status}...")
        self.run_async(self.api.post, lambda result, error: self.finish_async_result(result, error, status), path, payload, timeout=120.0)

    def _split_csv(self, value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip()]

    def browse_root(self) -> None:
        self._browse_dir(self.root, "Select raw sessions root")

    def browse_output(self) -> None:
        self._browse_dir(self.output_dir, "Select output directory")

    def _browse_dir(self, target: QLineEdit, title: str) -> None:
        path = QFileDialog.getExistingDirectory(self, title, target.text().strip())
        if path:
            target.setText(path)

    def _path_row(self, field: QLineEdit, handler) -> QWidget:
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        browse = QPushButton("Browse")
        browse.clicked.connect(handler)
        row.addWidget(field)
        row.addWidget(browse)
        return widget
