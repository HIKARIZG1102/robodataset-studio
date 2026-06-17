from __future__ import annotations

from pathlib import PurePosixPath

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFileDialog, QFormLayout, QHBoxLayout, QLineEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QWidget

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio_v3.frontend.pages.base import BasePage


class UploadPage(BasePage):
    def __init__(self, api: ApiClient, project: ProjectSummary | None = None) -> None:
        super().__init__("Upload", api, project)
        self.local_path = QLineEdit()
        self.remote_path = QLineEdit()
        self.host = QLineEdit()
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(22)
        self.username = QLineEdit()
        self.new_folder = QLineEdit()
        self.manifest_table = QTableWidget(0, 3)
        self.manifest_table.setHorizontalHeaderLabels(["Path", "Size", "SHA256"])
        self.remote_files = QTableWidget(0, 3)
        self.remote_files.setHorizontalHeaderLabels(["Name", "Type", "Size"])
        self.remote_files.cellDoubleClicked.connect(self.open_remote_row)
        self.active_task_id = ""
        self.task_timer = QTimer(self)
        self.task_timer.setInterval(1000)
        self.task_timer.timeout.connect(self.poll_task)
        if project is not None:
            self.local_path.setText(f"{project.path}/exports")
            self.load_upload_defaults(project.key)
        form = QFormLayout()
        form.addRow("Local file/folder", self._local_path_row())
        form.addRow("Remote path", self.remote_path)
        form.addRow("Host", self.host)
        form.addRow("Port", self.port)
        form.addRow("Username", self.username)
        form.addRow("New remote folder", self.new_folder)
        buttons = QHBoxLayout()
        for label, handler in [
            ("Check Dependencies", self.dependencies),
            ("Connect", self.connect),
            ("Build Manifest", self.manifest),
            ("Verify Local Manifest", self.verify_local_manifest),
            ("List Remote", self.list_remote),
            ("Up", self.remote_parent),
            ("Use Current Remote", self.use_current_remote),
            ("Create Remote Folder", self.create_remote_folder),
            ("Check Remote Space", self.remote_space),
            ("Upload", self.upload),
            ("Repair / Resume", self.repair),
            ("Verify", self.verify),
        ]:
            button = QPushButton(label)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        self.layout.addLayout(form)
        self.layout.addLayout(buttons)
        self.layout.addWidget(self.manifest_table)
        self.layout.addWidget(self.remote_files)
        self.finish_layout()

    def load_upload_defaults(self, project_key: str) -> None:
        try:
            config = self.api.get_project_config(project_key)
        except Exception:
            return
        upload = config.get("upload", {}) if isinstance(config.get("upload"), dict) else {}
        self.remote_path.setText(str(upload.get("remote_root", "")))
        self.host.setText(str(upload.get("host") or upload.get("lan_host") or upload.get("wan_host") or ""))
        self.username.setText(str(upload.get("username", "")))
        self.port.setValue(int(upload.get("port") or 22))

    def payload(self) -> dict[str, str]:
        return {
            "local_path": self.local_path.text().strip(),
            "remote_path": self.remote_path.text().strip(),
            "host": self.host.text().strip(),
            "port": int(self.port.value()),
            "username": self.username.text().strip(),
        }

    def dependencies(self) -> None:
        self.status.setText("Checking dependencies...")
        self.run_async(self.api.get, lambda result, error: self.finish_async_result(result, error, "Dependencies checked"), "/api/upload/dependencies", timeout=20.0)

    def connect(self) -> None:
        data = self.payload()
        self._post("/api/upload/connect", {"host": data["host"], "username": data["username"], "port": data["port"]}, "Profile checked", poll=False)

    def manifest(self) -> None:
        self._post("/api/upload/manifest", {"local_path": self.local_path.text().strip()}, "Manifest built", poll=False, callback=self._finish_manifest)

    def verify_local_manifest(self) -> None:
        self._post("/api/upload/manifest/verify", {"local_path": self.local_path.text().strip()}, "Local manifest verified", poll=False)

    def list_remote(self) -> None:
        payload = self.payload()
        self._post("/api/upload/remote/list", payload, "Remote listed", poll=False, callback=self._finish_remote_list)

    def remote_space(self) -> None:
        payload = self.payload()
        self._post("/api/upload/remote/space", payload, "Remote space checked", poll=False)

    def create_remote_folder(self) -> None:
        payload = self.payload()
        payload["folder_name"] = self.new_folder.text().strip()
        self._post("/api/upload/remote/mkdir", payload, "Remote folder created", poll=False, callback=self._finish_remote_mkdir)

    def remote_parent(self) -> None:
        path = PurePosixPath(self.remote_path.text().strip() or "/")
        parent = str(path.parent)
        self.remote_path.setText(parent if parent else "/")
        self.list_remote()

    def use_current_remote(self) -> None:
        self.status.setText(f"Remote target selected: {self.remote_path.text().strip()}")

    def upload(self) -> None:
        self._post("/api/upload/start", self.payload(), "Upload task created")

    def repair(self) -> None:
        self._post("/api/upload/repair", self.payload(), "Repair task created")

    def verify(self) -> None:
        self._post("/api/upload/verify", self.payload(), "Verify task created")

    def _post(self, path: str, payload: dict, status: str, *, poll: bool = True, callback=None) -> None:
        self.status.setText(f"{status}...")
        self.run_async(self.api.post, lambda result, error: (callback or self._finish_post)(result, error, status, poll), path, payload, timeout=20.0)

    def _finish_post(self, result: object, error: object, status: str, poll: bool) -> None:
        if error is not None:
            self.show_error(error if isinstance(error, Exception) else Exception(str(error)))
            return
        self.show_result(result, status)
        payload = result if isinstance(result, dict) else {}
        self.active_task_id = str(payload.get("task_id") or "")
        if poll and self.active_task_id:
            self.task_timer.start()

    def _finish_manifest(self, result: object, error: object, status: str, poll: bool) -> None:
        self._finish_post(result, error, status, poll)
        if error is not None:
            return
        payload = result.get("result", result) if isinstance(result, dict) else {}
        files = payload.get("preview_files", []) if isinstance(payload, dict) else []
        self.manifest_table.setRowCount(len(files) if isinstance(files, list) else 0)
        for row, item in enumerate(files if isinstance(files, list) else []):
            data = item if isinstance(item, dict) else {}
            values = [data.get("path", ""), data.get("size_bytes", ""), data.get("sha256", "")]
            for col, value in enumerate(values):
                self.manifest_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.manifest_table.resizeColumnsToContents()

    def _finish_remote_list(self, result: object, error: object, status: str, poll: bool) -> None:
        self._finish_post(result, error, status, poll)
        if error is not None:
            return
        payload = result.get("result", result) if isinstance(result, dict) else {}
        if isinstance(payload, dict) and payload.get("path"):
            self.remote_path.setText(str(payload.get("path")))
        entries = payload.get("entries", []) if isinstance(payload, dict) else []
        self.remote_files.setRowCount(len(entries) if isinstance(entries, list) else 0)
        for row, item in enumerate(entries if isinstance(entries, list) else []):
            data = item if isinstance(item, dict) else {}
            values = [data.get("name", ""), "dir" if data.get("is_dir") else "file", data.get("size", "")]
            for col, value in enumerate(values):
                self.remote_files.setItem(row, col, QTableWidgetItem(str(value)))
        self.remote_files.resizeColumnsToContents()

    def _finish_remote_mkdir(self, result: object, error: object, status: str, poll: bool) -> None:
        self._finish_post(result, error, status, poll)
        if error is not None:
            return
        payload = result.get("result", result) if isinstance(result, dict) else {}
        if isinstance(payload, dict) and payload.get("path"):
            self.remote_path.setText(str(payload.get("path")))
        self.new_folder.clear()
        self.list_remote()

    def open_remote_row(self, row: int, _column: int) -> None:
        name_item = self.remote_files.item(row, 0)
        type_item = self.remote_files.item(row, 1)
        if name_item is None or type_item is None or type_item.text() != "dir":
            return
        base = self.remote_path.text().strip().rstrip("/")
        name = name_item.text().strip()
        self.remote_path.setText(f"{base}/{name}" if base else f"/{name}")
        self.list_remote()

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
            self.show_result(task, f"Upload {status}")

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
