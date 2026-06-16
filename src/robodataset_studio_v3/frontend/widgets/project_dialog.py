from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QVBoxLayout


class NewProjectDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Project")
        self.name = QLineEdit()
        self.version = QLineEdit("v1")
        self.operator = QLineEdit()
        form = QFormLayout()
        form.addRow("Project name", self.name)
        form.addRow("Version", self.version)
        form.addRow("Operator", self.operator)
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
