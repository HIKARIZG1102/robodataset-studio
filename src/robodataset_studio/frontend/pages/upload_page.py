from __future__ import annotations

import json
from pathlib import PurePosixPath
from typing import Any

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from robodataset_studio.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio.frontend.pages.base import BasePage
from robodataset_studio.frontend.ui_helpers import make_path_field, make_path_label


class UploadPage(BasePage):
    def __init__(self, api: ApiClient, project: ProjectSummary | None = None) -> None:
        super().__init__("Upload", api, project)
        self.local_path = QLineEdit()
        self.remote_path = QLineEdit("/data/dataset")
        self.host = QLineEdit()
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(22)
        self.username = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.key_path = QLineEdit()
        self.auth_hint = QLabel("auth: agent_or_default_key")
        self.new_folder = QLineEdit()
        self.path_breadcrumbs = QHBoxLayout()
        self.manifest_summary = QLabel("manifest: not built")
        self.remote_summary = QLabel("remote: not listed")
        self.task_summary = QLabel("task: idle")
        for field in [self.local_path, self.remote_path, self.key_path, self.new_folder]:
            make_path_field(field)
        for label in [self.manifest_summary, self.remote_summary, self.task_summary, self.auth_hint]:
            make_path_label(label)
        self.manifest_path = ""
        self.manifest_table = QTableWidget(0, 3)
        self.manifest_table.setHorizontalHeaderLabels(["Path", "Size", "SHA256"])
        self.manifest_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.manifest_table.horizontalHeader().setStretchLastSection(True)
        self.manifest_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.manifest_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.remote_files = QTableWidget(0, 3)
        self.remote_files.setHorizontalHeaderLabels(["Name", "Type", "Size"])
        self.remote_files.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.remote_files.horizontalHeader().setStretchLastSection(True)
        self.remote_files.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.remote_files.setSelectionMode(QAbstractItemView.SingleSelection)
        self.remote_files.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.remote_files.cellDoubleClicked.connect(self.open_remote_row)
        self.active_task_id = ""
        self.task_timer = QTimer(self)
        self.task_timer.setInterval(1000)
        self.task_timer.timeout.connect(self.poll_task)
        self.config_timer = QTimer(self)
        self.config_timer.setInterval(2000)
        self.config_timer.timeout.connect(self.reload_upload_config_silent)
        self._upload_config_signature = ""
        for field in [self.host, self.username, self.key_path]:
            field.setReadOnly(True)
        self.port.setReadOnly(True)
        if project is not None:
            self.local_path.setText(f"{project.path}/exports")
            self.load_upload_defaults(project.key)
        self.password.textChanged.connect(self.update_auth_hint)
        self.key_path.textChanged.connect(self.update_auth_hint)
        self._build()

    def _build(self) -> None:
        local_box = QGroupBox("Local source")
        local_layout = QFormLayout(local_box)
        local_layout.addRow("File or folder", self._local_path_row())
        local_actions = QHBoxLayout()
        for label, handler in [
            ("Check Dependencies", self.dependencies),
            ("Build Manifest", self.manifest),
            ("Verify Local Manifest", self.verify_local_manifest),
        ]:
            button = QPushButton(label)
            button.clicked.connect(handler)
            local_actions.addWidget(button)
        local_layout.addRow(local_actions)
        local_layout.addRow(self.manifest_summary)

        remote_box = QGroupBox("Server and remote directory")
        remote_layout = QFormLayout(remote_box)
        reload_config = QPushButton("Reload from project config")
        reload_config.clicked.connect(self.reload_upload_config)
        remote_layout.addRow(reload_config)
        remote_layout.addRow("Host / IP", self.host)
        remote_layout.addRow("Port", self.port)
        remote_layout.addRow("Username", self.username)
        remote_layout.addRow("Password", self.password)
        remote_layout.addRow("Private key path", self._key_path_row())
        remote_layout.addRow("Authentication", self.auth_hint)
        self.remote_path.textChanged.connect(self.update_remote_breadcrumbs)
        remote_layout.addRow("Remote directory", self.remote_path)
        remote_layout.addRow("Path", self._breadcrumb_widget())
        remote_actions = QHBoxLayout()
        for label, handler in [
            ("Connect and list", self.connect_and_list),
            ("Up", self.remote_parent),
            ("Use Current Directory", self.use_current_remote),
            ("Check Remote Space", self.remote_space),
        ]:
            button = QPushButton(label)
            button.clicked.connect(handler)
            remote_actions.addWidget(button)
        remote_layout.addRow(remote_actions)
        mkdir_row = QHBoxLayout()
        mkdir_row.addWidget(self.new_folder, 1)
        mkdir_button = QPushButton("Create Folder")
        mkdir_button.clicked.connect(self.create_remote_folder)
        mkdir_row.addWidget(mkdir_button)
        remote_layout.addRow("New folder", mkdir_row)
        remote_layout.addRow(self.remote_summary)

        transfer_box = QGroupBox("Transfer")
        transfer_layout = QHBoxLayout(transfer_box)
        for label, handler in [
            ("Start rsync upload", self.upload),
            ("Repair / Resume verified upload", self.repair),
            ("Verify remote manifest", self.verify),
            ("Cancel current task", self.cancel_task),
            ("Refresh task", self.poll_task),
        ]:
            button = QPushButton(label)
            button.clicked.connect(handler)
            transfer_layout.addWidget(button)
        transfer_layout.addStretch(1)

        splitter = QSplitter(Qt.Horizontal)
        manifest_panel = QWidget()
        manifest_layout = QVBoxLayout(manifest_panel)
        manifest_layout.addWidget(QLabel("Local manifest preview"))
        manifest_layout.addWidget(self.manifest_table)
        remote_panel = QWidget()
        remote_layout_panel = QVBoxLayout(remote_panel)
        remote_layout_panel.addWidget(QLabel("Remote directory listing"))
        remote_layout_panel.addWidget(self.remote_files)
        splitter.addWidget(manifest_panel)
        splitter.addWidget(remote_panel)
        splitter.setSizes([520, 520])

        self.layout.addWidget(local_box)
        self.layout.addWidget(remote_box)
        self.layout.addWidget(transfer_box)
        self.layout.addWidget(self.task_summary)
        self.layout.addWidget(splitter, 1)
        self.finish_layout()
        self.update_remote_breadcrumbs()
        if self.project is not None:
            self.config_timer.start()

    def reload_upload_config(self) -> None:
        self._reload_upload_config(silent=False)

    def on_project_config_changed(self, project: ProjectSummary | None) -> None:
        self.project = project
        self._reload_upload_config(silent=True)

    def reload_upload_config_silent(self) -> None:
        self._reload_upload_config(silent=True)

    def _reload_upload_config(self, silent: bool = False) -> None:
        if self.project is None:
            if not silent:
                self.status.setText("Open a project before loading upload config.")
            return
        self.run_async(
            self.api.get_project_config,
            lambda result, error: self._finish_reload_upload_config(result, error, silent),
            self.project.key,
            timeout=10.0,
        )

    def _finish_reload_upload_config(self, result: object, error: object, silent: bool = False) -> None:
        if error is not None:
            if not silent:
                self.show_error(error if isinstance(error, Exception) else Exception(str(error)))
            return
        config = result if isinstance(result, dict) else {}
        changed = self.apply_upload_config(config.get("upload", {}) if isinstance(config.get("upload"), dict) else {})
        if not silent:
            self.status.setText("Upload settings loaded from current project config.")
        elif changed:
            self.status.setText("Upload settings refreshed from project config.")

    def load_upload_defaults(self, project_key: str) -> None:
        try:
            config = self.api.get_project_config(project_key)
        except Exception:
            return
        self.apply_upload_config(config.get("upload", {}) if isinstance(config.get("upload"), dict) else {})

    def apply_upload_config(self, upload: dict[str, Any]) -> bool:
        signature = json.dumps(upload, sort_keys=True, ensure_ascii=False, default=str)
        if signature == self._upload_config_signature:
            return False
        self._upload_config_signature = signature
        self.host.setText(str(upload.get("host") or upload.get("lan_host") or upload.get("wan_host") or ""))
        self.username.setText(str(upload.get("username", "")))
        self.key_path.setText(str(upload.get("key_path", "")))
        self.port.setValue(int(upload.get("port") or 22))
        self.update_auth_hint()
        return True

    def payload(self) -> dict[str, Any]:
        return {
            "local_path": self.local_path.text().strip(),
            "remote_path": self.remote_path.text().strip(),
            "host": self.host.text().strip(),
            "port": int(self.port.value()),
            "username": self.username.text().strip(),
            "password": self.password.text(),
            "key_path": self.key_path.text().strip(),
        }

    def dependencies(self) -> None:
        self.status.setText("Checking dependencies...")
        self.run_async(self.api.get, lambda result, error: self.finish_async_result(result, error, "Dependencies checked"), "/api/upload/dependencies", timeout=20.0)

    def connect_and_list(self) -> None:
        data = self.payload()
        self._post(
            "/api/upload/connect",
            {"host": data["host"], "username": data["username"], "port": data["port"], "password": data["password"], "key_path": data["key_path"]},
            "Connection checked",
            poll=False,
            callback=lambda result, error, status, poll: self._finish_connect(result, error),
        )

    def _finish_connect(self, result: object, error: object) -> None:
        self._finish_post(result, error, "Connection checked", False)
        if error is None:
            self.list_remote()

    def manifest(self) -> None:
        self._post("/api/upload/manifest", {"local_path": self.local_path.text().strip()}, "Manifest built", poll=False, callback=self._finish_manifest)

    def verify_local_manifest(self) -> None:
        self._post(
            "/api/upload/manifest/verify",
            {"local_path": self.local_path.text().strip(), "manifest_path": self.manifest_path},
            "Local manifest verified",
            poll=False,
            callback=self._finish_local_verify,
        )

    def list_remote(self) -> None:
        self._post("/api/upload/remote/list", self.payload(), "Remote listed", poll=False, callback=self._finish_remote_list)

    def remote_space(self) -> None:
        self._post("/api/upload/remote/space", self.payload(), "Remote space checked", poll=False, callback=self._finish_remote_space)

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
        self.remote_summary.setText(f"remote target: {self.remote_path.text().strip() or '/'}")
        self.status.setText("Remote target selected")
        self.update_remote_breadcrumbs()

    def upload(self) -> None:
        self._post("/api/upload/start", self.payload(), "Upload task created")

    def repair(self) -> None:
        self._post("/api/upload/repair", self.payload(), "Repair task created")

    def verify(self) -> None:
        self._post("/api/upload/verify", self.payload(), "Verify task created")

    def cancel_task(self) -> None:
        if not self.active_task_id:
            self.status.setText("No active task to cancel.")
            return
        self.run_async(
            self.api.post,
            lambda result, error: self.finish_async_result(result, error, "Cancel requested"),
            f"/api/tasks/{self.active_task_id}/cancel",
            {},
            timeout=10.0,
        )

    def _post(self, path: str, payload: dict[str, Any], status: str, *, poll: bool = True, callback=None) -> None:
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
            self.task_summary.setText(f"task: {self.active_task_id} running")
            self.task_timer.start()

    def _finish_manifest(self, result: object, error: object, status: str, poll: bool) -> None:
        self._finish_post(result, error, status, poll)
        if error is not None:
            return
        payload = self._result_payload(result)
        files = payload.get("preview_files", []) if isinstance(payload, dict) else []
        count = int(payload.get("file_count", 0) or 0) if isinstance(payload, dict) else 0
        size = int(payload.get("total_size_bytes", 0) or 0) if isinstance(payload, dict) else 0
        truncated = bool(payload.get("truncated", False)) if isinstance(payload, dict) else False
        old_manifest = self.manifest_path
        self.manifest_path = str(payload.get("manifest_path", "") if isinstance(payload, dict) else "")
        if old_manifest and old_manifest != self.manifest_path:
            self.cleanup_manifest(old_manifest)
        temp_text = f"; temporary: {self.manifest_path}" if self.manifest_path else ""
        self.manifest_summary.setText(f"manifest: {count} file(s), {self._format_bytes(size)}{temp_text}" + ("; preview truncated" if truncated else ""))
        self._fill_manifest_table(files if isinstance(files, list) else [])

    def _finish_local_verify(self, result: object, error: object, status: str, poll: bool) -> None:
        self._finish_post(result, error, status, poll)
        if error is not None:
            return
        payload = self._result_payload(result)
        if not isinstance(payload, dict):
            return
        if payload.get("manifest_path"):
            self.manifest_path = str(payload.get("manifest_path"))
        self.manifest_summary.setText(
            f"local manifest: ok={payload.get('ok')} checked={payload.get('checked', 0)} "
            f"missing={len(payload.get('missing', []))} mismatched={len(payload.get('mismatched', []))} "
            f"temporary={payload.get('temporary', False)}"
        )

    def _finish_remote_space(self, result: object, error: object, status: str, poll: bool) -> None:
        self._finish_post(result, error, status, poll)
        if error is not None:
            return
        payload = self._result_payload(result)
        if not isinstance(payload, dict):
            return
        self.remote_summary.setText(
            f"remote space: available={self._format_bytes(int(payload.get('available_bytes', 0) or 0))} "
            f"free={self._format_bytes(int(payload.get('free_bytes', 0) or 0))}"
        )

    def _finish_remote_list(self, result: object, error: object, status: str, poll: bool) -> None:
        self._finish_post(result, error, status, poll)
        if error is not None:
            return
        payload = self._result_payload(result)
        if isinstance(payload, dict) and payload.get("path"):
            self.remote_path.setText(str(payload.get("path")))
        entries = payload.get("entries", []) if isinstance(payload, dict) else []
        self.remote_summary.setText(f"remote: {self.remote_path.text().strip() or '/'}; entries={len(entries) if isinstance(entries, list) else 0}")
        self.update_remote_breadcrumbs()
        self.remote_files.setRowCount(len(entries) if isinstance(entries, list) else 0)
        for row, item in enumerate(entries if isinstance(entries, list) else []):
            data = item if isinstance(item, dict) else {}
            values = [data.get("name", ""), "dir" if data.get("is_dir") else "file", data.get("size", "")]
            for col, value in enumerate(values):
                self.remote_files.setItem(row, col, QTableWidgetItem(str(value)))
        for col, width in enumerate([320, 70]):
            self.remote_files.setColumnWidth(col, width)

    def _finish_remote_mkdir(self, result: object, error: object, status: str, poll: bool) -> None:
        self._finish_post(result, error, status, poll)
        if error is not None:
            return
        payload = self._result_payload(result)
        if isinstance(payload, dict) and payload.get("path"):
            self.remote_path.setText(str(payload.get("path")))
        self.new_folder.clear()
        self.list_remote()

    def _fill_manifest_table(self, files: list[object]) -> None:
        self.manifest_table.setRowCount(len(files))
        for row, item in enumerate(files):
            data = item if isinstance(item, dict) else {}
            values = [data.get("path", ""), data.get("size_bytes", ""), data.get("sha256", "")]
            for col, value in enumerate(values):
                self.manifest_table.setItem(row, col, QTableWidgetItem(str(value)))
        for col, width in enumerate([420, 110]):
            self.manifest_table.setColumnWidth(col, width)

    def open_remote_row(self, row: int, _column: int) -> None:
        name_item = self.remote_files.item(row, 0)
        type_item = self.remote_files.item(row, 1)
        if name_item is None or type_item is None or type_item.text() != "dir":
            return
        base = self.remote_path.text().strip().rstrip("/")
        name = name_item.text().strip()
        self.remote_path.setText(f"{base}/{name}" if base else f"/{name}")
        self.list_remote()

    def _remote_path_parts(self) -> list[tuple[str, str]]:
        raw = self.remote_path.text().strip() or "/"
        absolute = raw.startswith("/")
        parts = [part for part in raw.split("/") if part]
        crumbs: list[tuple[str, str]] = [("/", "/")] if absolute else []
        current = "" if absolute else "."
        for part in parts:
            current = f"{current.rstrip('/')}/{part}" if current not in {"", "."} else (f"/{part}" if absolute else part)
            crumbs.append((part, current))
        if not crumbs:
            crumbs.append(("/", "/"))
        return crumbs

    def update_remote_breadcrumbs(self) -> None:
        while self.path_breadcrumbs.count():
            item = self.path_breadcrumbs.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for label, target in self._remote_path_parts():
            button = QPushButton(label)
            button.setToolTip(target)
            button.clicked.connect(lambda _checked=False, path=target: self.jump_remote_path(path))
            self.path_breadcrumbs.addWidget(button)
        self.path_breadcrumbs.addStretch(1)

    def jump_remote_path(self, path: str) -> None:
        self.remote_path.setText(path or "/")
        self.list_remote()

    def poll_task(self) -> None:
        if not self.active_task_id:
            self.task_timer.stop()
            self.task_summary.setText("task: idle")
            return
        self.run_async(self.api.get, self._finish_task_poll, f"/api/tasks/{self.active_task_id}", timeout=5.0)

    def _finish_task_poll(self, result: object, error: object) -> None:
        if error is not None:
            self.status.setText(f"Task poll failed: {error}")
            self.task_timer.stop()
            return
        task = result if isinstance(result, dict) else {}
        status = str(task.get("status") or "")
        message = str(task.get("message") or "")
        logs = task.get("logs", []) if isinstance(task.get("logs"), list) else []
        progress_text = self._latest_progress(logs)
        self.task_summary.setText(f"task: {self.active_task_id} {status} {message}" + (f" | {progress_text}" if progress_text else ""))
        if logs:
            self.output.setPlainText("\n".join(str(line) for line in logs[-300:]))
        if status in {"done", "failed", "cancelled"}:
            self.task_timer.stop()
            self.show_result(task, f"Upload {status}")
            result_payload = task.get("result", {}) if isinstance(task.get("result"), dict) else {}
            if task.get("kind") == "upload_verify":
                self.manifest_summary.setText(
                    f"remote verify: ok={result_payload.get('ok')} checked={result_payload.get('checked', 0)} "
                    f"missing={len(result_payload.get('missing', []))} mismatched={len(result_payload.get('mismatched', []))}"
                )

    def _latest_progress(self, logs: list[object]) -> str:
        for raw in reversed(logs):
            text = str(raw)
            if "%" in text and ("/s" in text or "B/s" in text):
                return text.strip()
        return ""

    def browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select local file", self.local_path.text().strip())
        if path:
            self.local_path.setText(path)

    def browse_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select local folder", self.local_path.text().strip())
        if path:
            self.local_path.setText(path)

    def browse_key_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select private key", self.key_path.text().strip())
        if path:
            self.key_path.setText(path)

    def update_auth_hint(self) -> None:
        if self.key_path.text().strip():
            mode = "key"
        elif self.password.text():
            mode = "password"
        else:
            mode = "agent_or_default_key"
        self.auth_hint.setText(f"auth: {mode}")

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

    def _key_path_row(self) -> QWidget:
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        browse = QPushButton("Browse")
        browse.clicked.connect(self.browse_key_file)
        row.addWidget(self.key_path)
        row.addWidget(browse)
        return widget

    def _breadcrumb_widget(self) -> QWidget:
        widget = QWidget()
        widget.setLayout(self.path_breadcrumbs)
        self.path_breadcrumbs.setContentsMargins(0, 0, 0, 0)
        return widget

    def cleanup_manifest(self, manifest_path: str) -> None:
        self.run_async(
            self.api.post,
            lambda _result, _error: None,
            "/api/upload/manifest/cleanup",
            {"local_path": self.local_path.text().strip(), "manifest_path": manifest_path},
            timeout=10.0,
        )

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self.manifest_path:
            self.cleanup_manifest(self.manifest_path)
            self.manifest_path = ""
        super().closeEvent(event)

    def _result_payload(self, result: object) -> dict[str, Any]:
        if not isinstance(result, dict):
            return {}
        payload = result.get("result", result)
        return payload if isinstance(payload, dict) else {}

    def _format_bytes(self, size: int) -> str:
        value = float(size)
        for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
            if value < 1024 or unit == "PB":
                return f"{value:.2f} {unit}"
            value /= 1024
