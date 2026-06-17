from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QFileDialog, QFormLayout, QHBoxLayout, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QWidget

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio_v3.frontend.pages.base import BasePage


class ReviewPage(BasePage):
    def __init__(self, api: ApiClient, project: ProjectSummary | None = None) -> None:
        super().__init__("Review", api, project)
        self.session_dir = QLineEdit()
        self.hdf5_path = QLineEdit()
        self.folder = QLineEdit()
        self.episodes = QTableWidget(0, 5)
        self.episodes.setHorizontalHeaderLabels(["Episode", "Mark", "Status", "Issues", "Path"])
        if project is not None:
            raw_sessions = f"{project.path}/raw_sessions"
            self.session_dir.setText(raw_sessions)
            self.folder.setText(project.path)
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
        mark_buttons = QHBoxLayout()
        for label, status in [("Mark Keep", "keep"), ("Mark Warning", "warning"), ("Mark Reject", "reject"), ("Clear Mark", "")]:
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, value=status: self.mark_selected(value))
            mark_buttons.addWidget(button)
        self.layout.addLayout(mark_buttons)
        self.layout.addWidget(self.episodes)
        self.finish_layout()

    def scan_session(self) -> None:
        self._post("/api/review/session/scan", {"session_dir": self.session_dir.text().strip()}, "Session scanned", self._finish_scan)

    def check_session(self) -> None:
        self._post("/api/review/session/check", {"session_dir": self.session_dir.text().strip()}, "Session checked", self._finish_check)

    def check_hdf5(self) -> None:
        self._post("/api/review/hdf5/check", {"hdf5_path": self.hdf5_path.text().strip()}, "HDF5 checked")

    def check_layout(self) -> None:
        self._post("/api/review/layout/check", {"folder": self.folder.text().strip()}, "Layout checked")

    def _post(self, path: str, payload: dict, status: str, callback=None) -> None:
        self.status.setText(f"{status}...")
        self.run_async(self.api.post, callback or (lambda result, error: self.finish_async_result(result, error, status)), path, payload, timeout=60.0)

    def _finish_scan(self, result: object, error: object) -> None:
        if error is not None:
            self.show_error(error if isinstance(error, Exception) else Exception(str(error)))
            return
        self.show_result(result, "Session scanned")
        payload = result.get("result", result) if isinstance(result, dict) else {}
        if isinstance(payload, dict) and payload.get("session_dir"):
            self.session_dir.setText(str(payload.get("session_dir")))
        episodes = payload.get("episodes", []) if isinstance(payload, dict) else []
        self.populate_episodes(episodes if isinstance(episodes, list) else [])

    def _finish_check(self, result: object, error: object) -> None:
        if error is not None:
            self.show_error(error if isinstance(error, Exception) else Exception(str(error)))
            return
        self.show_result(result, "Session checked")
        payload = result.get("result", result) if isinstance(result, dict) else {}
        if isinstance(payload, dict) and payload.get("session_dir"):
            self.session_dir.setText(str(payload.get("session_dir")))
        summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
        rows = summary.get("episodes", []) if isinstance(summary, dict) else []
        if not rows:
            rows = payload.get("issues", []) if isinstance(payload, dict) else []
        self.populate_check_rows(rows if isinstance(rows, list) else [])

    def populate_episodes(self, episodes: list[Any]) -> None:
        self.episodes.setRowCount(len(episodes))
        for row, episode in enumerate(episodes):
            item = episode if isinstance(episode, dict) else {"path": str(episode), "name": str(episode).split("/")[-1]}
            values = [
                item.get("name", ""),
                item.get("mark", ""),
                "",
                "",
                item.get("path", ""),
            ]
            for col, value in enumerate(values):
                self.episodes.setItem(row, col, QTableWidgetItem(str(value)))
        self.episodes.resizeColumnsToContents()

    def populate_check_rows(self, rows: list[Any]) -> None:
        if not rows:
            return
        self.episodes.setRowCount(len(rows))
        for row, item in enumerate(rows):
            data = item if isinstance(item, dict) else {}
            path = str(data.get("path") or data.get("episode") or "")
            issues = data.get("quality_issues", data.get("issues", []))
            missing = str(data.get("missing", "") or "")
            if isinstance(issues, list):
                issue_text = "; ".join(str(issue) for issue in issues)
            else:
                issue_text = str(issues)
            if missing:
                issue_text = f"missing: {missing}; {issue_text}".strip("; ")
            values = [
                str(data.get("episode") or path.split("/")[-1]),
                str(data.get("mark", "")),
                str(data.get("status", "")),
                issue_text,
                path,
            ]
            for col, value in enumerate(values):
                self.episodes.setItem(row, col, QTableWidgetItem(value))
        self.episodes.resizeColumnsToContents()

    def mark_selected(self, status: str) -> None:
        row = self.episodes.currentRow()
        if row < 0:
            self.status.setText("Select an episode row first.")
            return
        episode_item = self.episodes.item(row, 0)
        episode = episode_item.text().strip() if episode_item else ""
        if not episode:
            self.status.setText("Selected row has no episode name.")
            return
        payload = {"session_dir": self.session_dir.text().strip(), "episode": episode, "status": status}
        self.run_async(self.api.post, lambda result, error: self._finish_mark(result, error, row, status), "/api/review/session/mark", payload, timeout=20.0)

    def _finish_mark(self, result: object, error: object, row: int, status: str) -> None:
        if error is not None:
            self.show_error(error if isinstance(error, Exception) else Exception(str(error)))
            return
        self.episodes.setItem(row, 1, QTableWidgetItem(status))
        self.show_result(result, "Episode mark saved")

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
