from __future__ import annotations

import os

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QDockWidget,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
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
from robodataset_studio_v3.frontend.widgets.config_library_page import ConfigLibraryPage
from robodataset_studio_v3.frontend.widgets.inspector import InspectorDock
from robodataset_studio_v3.frontend.widgets.project_config_page import ProjectConfigPage
from robodataset_studio_v3.frontend.widgets.project_browser import ProjectBrowserDialog
from robodataset_studio_v3.frontend.widgets.project_dialog import NewProjectDialog
from robodataset_studio_v3.frontend.worker import ApiWorker


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
        self.inspector: InspectorDock | None = None
        self.inspector_dock: QDockWidget | None = None
        self.ros_graph_cache: dict | None = None
        self.refresh_graph_button: QPushButton | None = None
        self.pool = QThreadPool.globalInstance()
        self._workers: list[ApiWorker] = []
        self._build_menu()
        self._build_graph_button()
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

        config_menu = self.menuBar().addMenu("Config")
        config_menu.addAction("Config Library", self.open_config_library_tab)
        config_menu.addAction("Current Project Config", self.open_project_config_tab)

        tools_menu = self.menuBar().addMenu("Tools")
        tools_menu.addAction("Collect", lambda: self.open_action_tab("collect"))
        tools_menu.addAction("Data Review", lambda: self.open_action_tab("review"))
        tools_menu.addAction("Convert", lambda: self.open_action_tab("convert"))
        tools_menu.addAction("Upload", lambda: self.open_action_tab("upload"))
        tools_menu.addAction("AI Assist", lambda: self.open_action_tab("ai"))
        tools_menu.addAction("Logs", lambda: self.open_action_tab("logs"))

        self.menuBar().addAction("Inspector", self.toggle_inspector)

        settings_menu = self.menuBar().addMenu("Settings")
        settings_menu.addAction("Settings", lambda: self.open_action_tab("settings"))

        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction("Tutorial", lambda: self.open_action_tab("tutorial"))

    def _build_graph_button(self) -> None:
        refresh = QPushButton("Refresh Graph")
        refresh.setObjectName("refreshGraphButton")
        refresh.setToolTip("Refresh the global ROS graph for Config, Discovery, and Inspector.")
        refresh.setCursor(Qt.PointingHandCursor)
        refresh.clicked.connect(self.refresh_ros_graph)
        refresh.setStyleSheet(
            """
            QPushButton#refreshGraphButton {
                margin: 3px 8px 3px 12px;
                padding: 5px 14px;
                border: 1px solid #2f6f9f;
                border-radius: 6px;
                color: #ffffff;
                background: #1f6aa5;
                font-weight: 600;
            }
            QPushButton#refreshGraphButton:hover {
                background: #267fbe;
                border-color: #3b8fc8;
            }
            QPushButton#refreshGraphButton:pressed {
                background: #18527f;
            }
            QPushButton#refreshGraphButton:disabled {
                color: #d8dee6;
                background: #6c7a86;
                border-color: #7b8792;
            }
            """
        )
        self.refresh_graph_button = refresh
        self.menuBar().setCornerWidget(refresh, Qt.TopRightCorner)

    def _empty_workspace(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        label = QLabel("Create or open a project to start.")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        return widget

    def new_project(self) -> None:
        dialog = NewProjectDialog(self.api, self)
        if not dialog.exec():
            return
        try:
            project = self.api.create_project(
                name=dialog.name.text().strip(),
                version=dialog.version.text().strip(),
                operator=dialog.operator.text().strip(),
                root_path=dialog.root_path.text().strip(),
                config_id=dialog.selected_config_id(),
            )
        except Exception as exc:
            QMessageBox.warning(self, "New Project", f"Cannot create project:\n{exc}")
            return
        self.current_project = project
        self._load_project_workspace()

    def open_config_library_tab(self) -> None:
        self._ensure_workspace(allow_empty=True)
        tab_id = "config_library"
        existing = self.open_tabs.get(tab_id)
        if existing is not None:
            self.workspace.setCurrentWidget(existing)
            return
        page = ConfigLibraryPage(self.api, self.current_project)
        if self.ros_graph_cache:
            page.set_graph_data(self.ros_graph_cache)
        self.open_tabs[tab_id] = page
        index = self.workspace.insertTab(0, page, "Config Library")
        self.workspace.setCurrentIndex(index)

    def new_config(self) -> None:
        self.open_config_library_tab()
        page = self.open_tabs.get("config_library")
        starter = getattr(page, "start_new_config", None)
        if callable(starter):
            starter()

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
        if dialog.browsed_project is not None:
            try:
                selected = self.api.open_project_path(dialog.browsed_project.path)
            except Exception as exc:
                QMessageBox.warning(self, "Open Project", f"Cannot open project folder:\n{exc}")
                return
        self.current_project = selected
        self._load_project_workspace()

    def _load_project_workspace(self) -> None:
        if self.current_project is None:
            return
        self.workspace = QTabWidget()
        self.workspace.setTabsClosable(True)
        self.workspace.tabCloseRequested.connect(self.close_workspace_tab)
        self.open_tabs = {}
        for tab_id in ["collect", "review", "convert", "upload", "logs"]:
            self._add_action_tab(tab_id, switch=False)
        self.setCentralWidget(self.workspace)

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
        if self.ros_graph_cache:
            handler = getattr(page, "set_graph_data", None)
            if callable(handler):
                handler(self.ros_graph_cache)
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
            self.workspace.setTabsClosable(True)
            self.workspace.tabCloseRequested.connect(self.close_workspace_tab)
            self.open_tabs = {}
            self.setCentralWidget(self.workspace)
            return
        if self.centralWidget() is not self.workspace:
            self._load_project_workspace()

    def toggle_inspector(self) -> None:
        dock = self._ensure_inspector()
        dock.setVisible(not dock.isVisible())

    def show_inspector(self) -> None:
        self._ensure_inspector().show()

    def show_topic_inspector(self) -> None:
        dock = self._ensure_inspector()
        if self.inspector is not None:
            self.inspector.show_topic()
        dock.show()

    def show_image_monitor(self) -> None:
        dock = self._ensure_inspector()
        if self.inspector is not None:
            self.inspector.show_image()
        dock.show()

    def refresh_ros_graph(self) -> None:
        self.statusBar().showMessage("Refreshing ROS graph...")
        if self.refresh_graph_button is not None:
            self.refresh_graph_button.setEnabled(False)
            self.refresh_graph_button.setText("Refreshing...")
        worker = ApiWorker(self.api.get, "/api/ros/graph", timeout=12.0)
        self._workers.append(worker)

        def finish(result: object, error: object, item: ApiWorker = worker) -> None:
            try:
                if error is not None:
                    self.statusBar().showMessage(f"ROS graph refresh failed: {error}")
                    return
                graph = result if isinstance(result, dict) else {}
                self._ros_graph_updated(graph)
                topics = graph.get("topics", []) if isinstance(graph.get("topics"), list) else []
                nodes = graph.get("nodes", []) if isinstance(graph.get("nodes"), list) else []
                self.statusBar().showMessage(f"ROS graph refreshed: {len(topics)} topics, {len(nodes)} nodes")
            finally:
                if self.refresh_graph_button is not None:
                    self.refresh_graph_button.setEnabled(True)
                    self.refresh_graph_button.setText("Refresh Graph")
                if item in self._workers:
                    self._workers.remove(item)

        worker.signals.finished.connect(finish, Qt.QueuedConnection)
        self.pool.start(worker)

    def _ensure_inspector(self) -> QDockWidget:
        if self.inspector_dock is not None:
            return self.inspector_dock
        self.inspector_dock = QDockWidget("Inspector", self)
        self.inspector_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        try:
            self.inspector = InspectorDock(self.api)
            self.inspector.graphUpdated.connect(self._ros_graph_updated)
            self.inspector_dock.setWidget(self.inspector)
        except Exception as exc:
            fallback = QLabel(f"Inspector failed to initialize:\n{exc}")
            fallback.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            self.inspector_dock.setWidget(fallback)
            self.inspector = None
        self.addDockWidget(Qt.RightDockWidgetArea, self.inspector_dock)
        return self.inspector_dock

    def _ros_graph_updated(self, graph: dict) -> None:
        self.ros_graph_cache = graph
        if self.inspector is not None:
            self.inspector.set_graph_data(graph)
        for widget in self.open_tabs.values():
            handler = getattr(widget, "set_graph_data", None)
            if callable(handler):
                handler(graph)

    def close_workspace_tab(self, index: int) -> None:
        widget = self.workspace.widget(index)
        for tab_id, tab_widget in list(self.open_tabs.items()):
            if tab_widget is widget:
                self.open_tabs.pop(tab_id, None)
                break
        self.workspace.removeTab(index)
        widget.deleteLater()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self.inspector is not None:
            self.inspector.stop_workers()
        self.backend.stop()
        super().closeEvent(event)
