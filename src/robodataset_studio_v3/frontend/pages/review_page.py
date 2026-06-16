from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QFormLayout, QHBoxLayout, QLineEdit, QPushButton, QWidget

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio_v3.frontend.pages.base import BasePage


class ReviewPage(BasePage):
    def __init__(self, api: ApiClient, project: ProjectSummary | None = None) -> None:
        super().__init__("Review", api, project)
        self.session_dir = QLineEdit()
        self.hdf5_path = QLineEdit()
        self.folder = QLineEdit()
        form = QFormLayout()
        form.addRow("Session dir", self._path_row(self.session_dir, self.browse_session))
        form.addRow("HDF5 file", self._path_row(self.hdf5_path, self.browse_hdf5))
        form.addRow("Layout folder", self._path_row(self.folder, self.browse_folder))
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
        self.status.setText(f"{status}...")
        self.run_async(self.api.post, lambda result, error: self.finish_async_result(result, error, status), path, payload, timeout=60.0)

    def browse_session(self) -> None:
        self._browse_dir(self.session_dir, "Select CALVIN session")

    def browse_hdf5(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select HDF5 file", self.hdf5_path.text().strip(), "HDF5 (*.hdf5 *.h5);;All files (*)")
        if path:
            self.hdf5_path.setText(path)

    def browse_folder(self) -> None:
        self._browse_dir(self.folder, "Select CALVIN layout folder")

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
