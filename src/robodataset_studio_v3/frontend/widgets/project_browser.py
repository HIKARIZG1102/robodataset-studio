from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QListWidget, QVBoxLayout

from robodataset_studio_v3.frontend.api_client import ProjectSummary


class ProjectBrowserDialog(QDialog):
    def __init__(self, projects: list[ProjectSummary], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Open Project")
        self.projects = projects
        self.list_widget = QListWidget()
        for project in projects:
            self.list_widget.addItem(f"{project.name}\n  _{project.version}")
        buttons = QDialogButtonBox(QDialogButtonBox.Open | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.list_widget)
        layout.addWidget(buttons)

    def selected_project(self) -> ProjectSummary | None:
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self.projects):
            return None
        return self.projects[row]
