from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio_v3.frontend.backend_process import BackendProcess
from robodataset_studio_v3.frontend.widgets.inspector import InspectorDock
from robodataset_studio_v3.frontend.widgets.project_browser import ProjectBrowserDialog
from robodataset_studio_v3.frontend.widgets.project_dialog import NewProjectDialog


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("RoboDataset Studio V3")
        self.api = ApiClient()
        self.backend = BackendProcess(self.api)
        self.current_project: ProjectSummary | None = None
        self.workspace = QTabWidget()
        self.empty = self._empty_workspace()
        self.setCentralWidget(self.empty)
        self.inspector = InspectorDock()
        self.inspector_dock = QDockWidget("Inspector", self)
        self.inspector_dock.setWidget(self.inspector)
        self.addDockWidget(Qt.RightDockWidgetArea, self.inspector_dock)
        self.inspector_dock.hide()
        self._build_menu()
        self._ensure_backend()

    def _ensure_backend(self) -> None:
        try:
            self.backend.ensure_running()
        except Exception as exc:
            self.statusBar().showMessage(f"Backend unavailable: {exc}")
            if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
                QMessageBox.warning(self, "Backend", f"Cannot start local FastAPI backend:\n{exc}")
        else:
            self.statusBar().showMessage("Backend connected")

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        new_project = file_menu.addAction("New Project")
        open_project = file_menu.addAction("Open Project")
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)
        new_project.triggered.connect(self.new_project)
        open_project.triggered.connect(self.open_project)

        project_menu = self.menuBar().addMenu("Project")
        project_menu.addAction("Project Config", lambda: QMessageBox.information(self, "Project Config", "Project config dialog is planned."))

        tools_menu = self.menuBar().addMenu("Tools")
        tools_menu.addAction("Toggle Inspector", self.toggle_inspector)

        settings_menu = self.menuBar().addMenu("Settings")
        settings_menu.addAction("Environment", lambda: QMessageBox.information(self, "Settings", "Environment settings are planned."))
        settings_menu.addAction("Server Profiles", lambda: QMessageBox.information(self, "Settings", "Server profile settings are planned."))
        settings_menu.addAction("AI Provider", lambda: QMessageBox.information(self, "Settings", "AI provider settings are planned."))

        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction("Tutorial", lambda: QMessageBox.information(self, "Tutorial", "Tutorial page is planned."))

    def _empty_workspace(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        label = QLabel("Create or open a project to start.")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        return widget

    def new_project(self) -> None:
        dialog = NewProjectDialog(self)
        if not dialog.exec():
            return
        try:
            project = self.api.create_project(
                name=dialog.name.text().strip(),
                version=dialog.version.text().strip(),
                operator=dialog.operator.text().strip(),
            )
        except Exception as exc:
            QMessageBox.warning(self, "New Project", f"Cannot create project:\n{exc}")
            return
        self.current_project = project
        self._load_project_workspace()

    def open_project(self) -> None:
        try:
            projects = self.api.list_projects()
        except Exception as exc:
            QMessageBox.warning(self, "Open Project", f"Cannot list projects:\n{exc}")
            return
        if not projects:
            QMessageBox.information(self, "Open Project", "No projects found. Create a project first.")
            return
        dialog = ProjectBrowserDialog(projects, self)
        if not dialog.exec():
            return
        selected = dialog.selected_project()
        if selected is None:
            QMessageBox.information(self, "Open Project", "Select a project first.")
            return
        self.current_project = selected
        self._load_project_workspace()

    def _load_project_workspace(self) -> None:
        if self.current_project is None:
            return
        self.workspace = QTabWidget()
        for name in ["Collect", "Review", "Convert", "Upload", "Logs"]:
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.addWidget(QLabel(f"{name} workspace for {self.current_project.key}"))
            self.workspace.addTab(page, name)
        self.setCentralWidget(self.workspace)
        self.inspector_dock.show()

    def toggle_inspector(self) -> None:
        self.inspector_dock.setVisible(not self.inspector_dock.isVisible())

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.backend.stop()
        super().closeEvent(event)
