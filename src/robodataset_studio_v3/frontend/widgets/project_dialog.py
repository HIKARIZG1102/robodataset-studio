from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget

from robodataset_studio_v3.frontend.api_client import ApiClient


class NewProjectDialog(QDialog):
    def __init__(self, api: ApiClient | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Project")
        self.api = api
        self.configs: list[dict] = []
        self.name = QLineEdit()
        self.version = QLineEdit("v1")
        self.operator = QLineEdit()
        self.root_path = QLineEdit("robodataset/projects")
        self.config_combo = QComboBox()
        self.config_combo.setMinimumWidth(260)
        browse = QPushButton("Browse")
        browse.clicked.connect(self.browse_root)
        root_row = QWidget()
        root_layout = QHBoxLayout(root_row)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(self.root_path)
        root_layout.addWidget(browse)
        form = QFormLayout()
        form.addRow("Project name", self.name)
        form.addRow("Version", self.version)
        form.addRow("Operator", self.operator)
        form.addRow("Project root", root_row)
        form.addRow("Total config", self.config_combo)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.load_configs()

    def project_key(self) -> str:
        name = self.name.text().strip() or "untitled_project"
        version = self.version.text().strip() or "v1"
        return f"{name}_{version}"

    def browse_root(self) -> None:
        current = self.root_path.text().strip()
        start = str(Path(current).expanduser()) if current else str(Path(__file__).resolve().parents[4] / "robodataset" / "projects")
        path = QFileDialog.getExistingDirectory(self, "Select project root", start)
        if path:
            self.root_path.setText(path)

    def load_configs(self) -> None:
        self.config_combo.clear()
        self.configs = []
        if self.api is not None:
            try:
                self.configs = self.api.list_configs()
            except Exception:
                self.configs = []
        if not self.configs:
            self.configs = [{"id": "default_calvin", "name": "Default CALVIN config"}]
        for config in self.configs:
            config_id = str(config.get("id") or "")
            name = str(config.get("name") or config_id)
            streams = config.get("stream_count", "")
            suffix = f" ({streams} streams)" if streams != "" else ""
            self.config_combo.addItem(f"{name} [{config_id}]{suffix}", config_id)

    def selected_config_id(self) -> str:
        return str(self.config_combo.currentData() or self.config_combo.currentText().strip() or "default_calvin")
