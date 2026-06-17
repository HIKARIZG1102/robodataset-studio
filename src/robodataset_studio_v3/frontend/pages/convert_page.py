from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFileDialog, QFormLayout, QHBoxLayout, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QWidget

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio_v3.frontend.pages.base import BasePage


class ConvertPage(BasePage):
    def __init__(self, api: ApiClient, project: ProjectSummary | None = None) -> None:
        super().__init__("Convert", api, project)
        self.root = QLineEdit()
        self.sessions = QLineEdit()
        self.output_dir = QLineEdit()
        self.session_table = QTableWidget(0, 5)
        self.session_table.setHorizontalHeaderLabels(["Use", "Session", "Episodes", "Status", "Path"])
        if project is not None:
            self.root.setText(f"{project.path}/raw_sessions")
            self.output_dir.setText(f"{project.path}/exports")
        self.active_task_id = ""
        self.task_timer = QTimer(self)
        self.task_timer.setInterval(1000)
        self.task_timer.timeout.connect(self.poll_task)
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
        self.layout.addWidget(self.session_table)
        self.finish_layout()

    def scan(self) -> None:
        self.status.setText("Scanning sessions...")
        self.run_async(self.api.post, self._finish_scan, "/api/convert/scan", {"root": self.root.text().strip()}, timeout=60.0)

    def _finish_scan(self, result: object, error: object) -> None:
        if error is not None:
            self.show_error(error if isinstance(error, Exception) else Exception(str(error)))
            return
        if isinstance(result, dict):
            payload = result.get("result", result)
            sessions = payload.get("sessions", []) if isinstance(payload, dict) else []
            if isinstance(sessions, list):
                self.populate_sessions(sessions)
                self.sessions.setText(", ".join(self.selected_session_paths()))
        self.show_result(result, "Sessions scanned")

    def merge(self) -> None:
        self._convert("/api/convert/merge", "Merge task created")

    def hdf5(self) -> None:
        self._convert("/api/convert/hdf5", "HDF5 task created")

    def _convert(self, path: str, status: str) -> None:
        selected = self.selected_session_paths() or self._split_csv(self.sessions.text())
        payload = {"sessions": selected, "output_dir": self.output_dir.text().strip()}
        self.status.setText(f"{status}...")
        self.run_async(self.api.post, lambda result, error: self._finish_convert_start(result, error, status), path, payload, timeout=20.0)

    def _finish_convert_start(self, result: object, error: object, status: str) -> None:
        if error is not None:
            self.show_error(error if isinstance(error, Exception) else Exception(str(error)))
            return
        self.show_result(result, status)
        payload = result if isinstance(result, dict) else {}
        self.active_task_id = str(payload.get("task_id") or "")
        if self.active_task_id:
            self.task_timer.start()

    def poll_task(self) -> None:
        if not self.active_task_id:
            self.task_timer.stop()
            return
        self.run_async(self.api.get, self._finish_task_poll, f"/api/tasks/{self.active_task_id}", timeout=5.0)

    def _finish_task_poll(self, result: object, error: object) -> None:
        if error is not None:
            self.status.setText(f"Task poll failed: {error}")
            self.task_timer.stop()
            return
        task = result if isinstance(result, dict) else {}
        status = str(task.get("status") or "")
        self.status.setText(f"Task {self.active_task_id}: {status} {task.get('message', '')}")
        if status in {"done", "failed", "cancelled"}:
            self.task_timer.stop()
            self.show_result(task, f"Convert {status}")

    def populate_sessions(self, sessions: list[object]) -> None:
        self.session_table.setRowCount(len(sessions))
        for row, session in enumerate(sessions):
            item = session if isinstance(session, dict) else {"path": str(session), "name": str(session).split("/")[-1]}
            use = QTableWidgetItem("")
            use.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            use.setCheckState(Qt.Checked if int(item.get("episode_count", 0) or 0) > 0 else Qt.Unchecked)
            values = [
                use,
                QTableWidgetItem(str(item.get("name", ""))),
                QTableWidgetItem(str(item.get("episode_count", ""))),
                QTableWidgetItem(str(item.get("status", ""))),
                QTableWidgetItem(str(item.get("path", ""))),
            ]
            for col, value in enumerate(values):
                self.session_table.setItem(row, col, value)
        self.session_table.resizeColumnsToContents()

    def selected_session_paths(self) -> list[str]:
        paths = []
        for row in range(self.session_table.rowCount()):
            use = self.session_table.item(row, 0)
            path = self.session_table.item(row, 4)
            if use is not None and use.checkState() == Qt.Checked and path is not None and path.text().strip():
                paths.append(path.text().strip())
        return paths

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
