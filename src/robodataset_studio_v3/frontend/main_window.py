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
from robodataset_studio_v3.frontend.pages.ai_page import AiPage
from robodataset_studio_v3.frontend.pages.collect_page import CollectPage
from robodataset_studio_v3.frontend.pages.convert_page import ConvertPage
from robodataset_studio_v3.frontend.pages.logs_page import LogsPage
from robodataset_studio_v3.frontend.pages.review_page import ReviewPage
from robodataset_studio_v3.frontend.pages.ros_page import RosPage
from robodataset_studio_v3.frontend.pages.settings_page import SettingsPage
from robodataset_studio_v3.frontend.pages.tutorial_page import TutorialPage
from robodataset_studio_v3.frontend.pages.upload_page import UploadPage
from robodataset_studio_v3.frontend.widgets.inspector import InspectorDock
from robodataset_studio_v3.frontend.widgets.project_config_page import ProjectConfigPage
from robodataset_studio_v3.frontend.widgets.project_browser import ProjectBrowserDialog
from robodataset_studio_v3.frontend.widgets.project_dialog import NewProjectDialog


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("RoboDataset Studio V3")
        self.api = ApiClient()
        self.backend = BackendProcess(self.api)
        self.current_project: ProjectSummary | None = None
        self.open_tabs: dict[str, QWidget] = {}
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
        project_menu.addAction("Project Config", self.open_project_config_tab)

        tools_menu = self.menuBar().addMenu("Tools")
        tools_menu.addAction("Collect", lambda: self.open_action_tab("collect"))
        tools_menu.addAction("ROS Discovery", lambda: self.open_action_tab("ros"))
        tools_menu.addAction("Data Review", lambda: self.open_action_tab("review"))
        tools_menu.addAction("Convert", lambda: self.open_action_tab("convert"))
        tools_menu.addAction("Upload", lambda: self.open_action_tab("upload"))
        tools_menu.addAction("AI Assist", lambda: self.open_action_tab("ai"))
        tools_menu.addAction("Logs", lambda: self.open_action_tab("logs"))
        tools_menu.addSeparator()
        tools_menu.addAction("Toggle Inspector", self.toggle_inspector)

        settings_menu = self.menuBar().addMenu("Settings")
        settings_menu.addAction("Settings", lambda: self.open_action_tab("settings"))

        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction("Tutorial", lambda: self.open_action_tab("tutorial"))

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
        self.open_tabs = {}
        for tab_id in ["collect", "review", "convert", "upload", "logs"]:
            self._add_action_tab(tab_id, switch=False)
        self.setCentralWidget(self.workspace)
        self.inspector_dock.show()

    def open_project_config_tab(self) -> None:
        if self.current_project is None:
            QMessageBox.information(self, "Project Config", "Open or create a project first.")
            return
        self._ensure_workspace()
        tab_id = "project_config"
        existing = self.open_tabs.get(tab_id)
        if existing is not None:
            self.workspace.setCurrentWidget(existing)
            return
        page = ProjectConfigPage(self.api, self.current_project)
        self.open_tabs[tab_id] = page
        index = self.workspace.insertTab(0, page, "Project Config")
        self.workspace.setCurrentIndex(index)

    def open_action_tab(self, tab_id: str) -> None:
        if tab_id not in {"settings", "tutorial", "logs"} and self.current_project is None:
            QMessageBox.information(self, "Project", "Open or create a project first.")
            return
        self._ensure_workspace(allow_empty=True)
        self._add_action_tab(tab_id, switch=True)

    def _add_action_tab(self, tab_id: str, *, switch: bool) -> None:
        existing = self.open_tabs.get(tab_id)
        if existing is not None:
            if switch:
                self.workspace.setCurrentWidget(existing)
            return
        page = self._make_action_page(tab_id)
        self.open_tabs[tab_id] = page
        index = self.workspace.addTab(page, self._tab_title(tab_id))
        if switch:
            self.workspace.setCurrentIndex(index)

    def _make_action_page(self, tab_id: str) -> QWidget:
        project = self.current_project
        if tab_id == "collect":
            return CollectPage(self.api, project)
        if tab_id == "ros":
            return RosPage(self.api, project)
        if tab_id == "review":
            return ReviewPage(self.api, project)
        if tab_id == "convert":
            return ConvertPage(self.api, project)
        if tab_id == "upload":
            return UploadPage(self.api, project)
        if tab_id == "ai":
            return AiPage(self.api, project)
        if tab_id == "settings":
            return SettingsPage(self.api, project)
        if tab_id == "tutorial":
            return TutorialPage()
        return LogsPage(self.api, project)

    def _tab_title(self, tab_id: str) -> str:
        return {
            "collect": "Collect",
            "ros": "ROS",
            "review": "Review",
            "convert": "Convert",
            "upload": "Upload",
            "ai": "AI",
            "settings": "Settings",
            "tutorial": "Tutorial",
            "logs": "Logs",
        }.get(tab_id, tab_id.title())

    def _ensure_workspace(self, *, allow_empty: bool = False) -> None:
        if self.current_project is None and allow_empty and self.centralWidget() is self.empty:
            self.workspace = QTabWidget()
            self.open_tabs = {}
            self.setCentralWidget(self.workspace)
        if self.centralWidget() is not self.workspace:
            self._load_project_workspace()

    def toggle_inspector(self) -> None:
        self.inspector_dock.setVisible(not self.inspector_dock.isVisible())

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.backend.stop()
        super().closeEvent(event)
