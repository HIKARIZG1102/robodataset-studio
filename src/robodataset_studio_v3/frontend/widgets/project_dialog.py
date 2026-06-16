from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget


class NewProjectDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Project")
        self.name = QLineEdit()
        self.version = QLineEdit("v1")
        self.operator = QLineEdit()
        self.root_path = QLineEdit("robodataset/projects")
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
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

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
