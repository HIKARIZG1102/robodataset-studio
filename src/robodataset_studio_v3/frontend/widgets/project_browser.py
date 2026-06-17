from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QDialog, QDialogButtonBox, QListWidget, QPushButton, QVBoxLayout

from robodataset_studio_v3.frontend.api_client import ProjectSummary


class ProjectBrowserDialog(QDialog):
    def __init__(self, projects: list[ProjectSummary], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Open Project")
        self.projects = projects
        self.browsed_project: ProjectSummary | None = None
        self.list_widget = QListWidget()
        for project in projects:
            lock = "locked" if project.has_recorded_data else "editable"
            config = project.config_id or "no config"
            self.list_widget.addItem(f"{project.name}\n  _{project.version} | {config} | {lock}")
        buttons = QDialogButtonBox(QDialogButtonBox.Open | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.list_widget)
        browse = QPushButton("Browse Project Folder")
        browse.clicked.connect(self.browse_project_folder)
        layout.addWidget(browse)
        layout.addWidget(buttons)

    def selected_project(self) -> ProjectSummary | None:
        if self.browsed_project is not None:
            return self.browsed_project
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self.projects):
            return None
        return self.projects[row]

    def browse_project_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select project folder")
        if not path:
            return
        folder = Path(path)
        key = folder.name
        if "_v" in key:
            name, version = key.rsplit("_", 1)
        else:
            name, version = key, "v1"
        self.browsed_project = ProjectSummary(key=key, name=name, version=version, path=str(folder))
        self.accept()
