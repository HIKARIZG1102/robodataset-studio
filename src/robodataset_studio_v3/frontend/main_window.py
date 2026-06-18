from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QToolBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio_v3.frontend.backend_process import BackendProcess
from robodataset_studio_v3.frontend.i18n import apply_i18n, normalize_language, text
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
        self.resize(1280, 860)
        self.setMinimumSize(760, 520)
        self.api = ApiClient()
        self.backend = BackendProcess(self.api)
        self.current_project: ProjectSummary | None = None
        self.open_tabs: dict[str, QWidget] = {}
        self.workspace_panes: list[QTabWidget] = []
        self.workspace_splitter: QSplitter | None = None
        self.workspace = QTabWidget()
        self._configure_workspace(self.workspace)
        self.empty = self._empty_workspace()
        self.setCentralWidget(self.empty)
        self.inspector: InspectorDock | None = None
        self.inspector_dock: QDockWidget | None = None
        self.ros_graph_cache: dict | None = None
        self.refresh_graph_button: QPushButton | None = None
        self.project_summary = QLabel("")
        self.settings: dict = {}
        self.language = "en"
        self.ui_scale = 1.0
        self._base_font_point_size = QApplication.font().pointSizeF()
        if self._base_font_point_size <= 0:
            self._base_font_point_size = 10.0
        self._restoring_workspace = False
        self.pool = QThreadPool.globalInstance()
        self._workers: list[ApiWorker] = []
        self._build_menu()
        self._build_project_summary_bar()
        self._build_graph_button()
        self._ensure_backend()
        self._restore_startup_state()

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
        tools_menu.addAction("Logs", lambda: self.open_action_tab("logs"))

        self.menuBar().addAction("Inspector", self.toggle_inspector)

        settings_menu = self.menuBar().addMenu("Settings")
        settings_menu.addAction("Settings", lambda: self.open_action_tab("settings"))
        settings_menu.addSeparator()
        zoom_in = settings_menu.addAction("Zoom In", self.zoom_in)
        zoom_in.setShortcuts([QKeySequence("Ctrl++"), QKeySequence("Ctrl+=")])
        zoom_out = settings_menu.addAction("Zoom Out", self.zoom_out)
        zoom_out.setShortcut(QKeySequence("Ctrl+-"))
        reset_zoom = settings_menu.addAction("Reset Zoom", self.reset_zoom)
        reset_zoom.setShortcut(QKeySequence("Ctrl+0"))

        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction("Tutorial", self.open_tutorial_guide)

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

    def _build_project_summary_bar(self) -> None:
        toolbar = QToolBar("Project")
        toolbar.setMovable(False)
        self.project_summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.project_summary.setWordWrap(False)
        toolbar.addWidget(self.project_summary)
        self.addToolBar(Qt.TopToolBarArea, toolbar)
        self.update_project_summary()

    def update_project_summary(self) -> None:
        if self.current_project is None:
            self.project_summary.setText(text("Project: none | Config: none", self.language))
            return
        state = "recorded" if self.current_project.has_recorded_data else "editable"
        if normalize_language(self.language) == "zh":
            self.project_summary.setText(
                f"项目: {self.current_project.name} {self.current_project.version} | "
                f"配置: {self.current_project.config_id or 'none'} | {state}"
            )
        else:
            self.project_summary.setText(
                f"Project: {self.current_project.name} {self.current_project.version} | "
                f"Config: {self.current_project.config_id or 'none'} | {state}"
            )

    def _empty_workspace(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        label = QLabel("Create or open a project to start.")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        return widget

    def _new_workspace_pane(self) -> QTabWidget:
        pane = QTabWidget()
        self._configure_workspace(pane)
        pane.setMinimumSize(320, 240)
        return pane

    def _create_workspace_container(self) -> QSplitter:
        splitter = QSplitter(Qt.Horizontal)
        self.workspace_splitter = splitter
        self.workspace_panes = [self._new_workspace_pane()]
        self.workspace = self.workspace_panes[0]
        splitter.addWidget(self.workspace)
        splitter.setChildrenCollapsible(False)
        return splitter

    def _active_workspace(self) -> QTabWidget:
        if self.workspace in self.workspace_panes:
            return self.workspace
        if self.workspace_panes:
            self.workspace = self.workspace_panes[0]
            return self.workspace
        self._create_workspace_container()
        return self.workspace

    def _pane_for_widget(self, widget: QWidget | None) -> QTabWidget | None:
        if widget is None:
            return None
        for pane in self.workspace_panes:
            if pane.indexOf(widget) >= 0:
                return pane
        return None

    def _focus_widget_tab(self, widget: QWidget) -> None:
        pane = self._pane_for_widget(widget)
        if pane is None:
            return
        self.workspace = pane
        pane.setCurrentWidget(widget)

    def _tab_id_for_widget(self, widget: QWidget | None) -> str:
        if widget is None:
            return ""
        for tab_id, tab_widget in self.open_tabs.items():
            if tab_widget is widget:
                return tab_id
        return ""

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
        self._remember_project(project)
        self.update_project_summary()
        self._load_project_workspace()

    def open_config_library_tab(self) -> None:
        self._ensure_workspace(allow_empty=True)
        tab_id = "config_library"
        existing = self.open_tabs.get(tab_id)
        if existing is not None:
            self._focus_widget_tab(existing)
            return
        page = ConfigLibraryPage(self.api, self.current_project)
        page.projectConfigChanged.connect(self._project_config_changed)
        if self.ros_graph_cache:
            page.set_graph_data(self.ros_graph_cache)
        self.open_tabs[tab_id] = page
        target = self._active_workspace()
        index = target.insertTab(0, page, "Config Library")
        apply_i18n(page, self.language)
        target.setTabText(index, self._translated_tab_title(tab_id))
        target.setCurrentIndex(index)
        self.workspace = target

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
        self._remember_project(selected)
        self.update_project_summary()
        self._load_project_workspace()

    def _load_project_workspace(self) -> None:
        if self.current_project is None:
            return
        container = self._create_workspace_container()
        self.open_tabs = {}
        self._restoring_workspace = True
        for tab_id in ["collect", "review", "convert", "upload", "logs"]:
            self._add_action_tab(tab_id, switch=False)
        self.setCentralWidget(container)
        self._restoring_workspace = False
        self._sync_inspector_project()
        self.update_project_summary()
        last_tab = self._ui_settings().get("last_active_tab", "")
        if isinstance(last_tab, str) and last_tab in self.open_tabs:
            self._focus_widget_tab(self.open_tabs[last_tab])

    def open_project_config_tab(self) -> None:
        if self.current_project is None:
            QMessageBox.information(self, "Project Config", "Open or create a project first.")
            return
        self._ensure_workspace()
        tab_id = "project_config"
        existing = self.open_tabs.get(tab_id)
        if existing is not None:
            self._focus_widget_tab(existing)
            return
        page = ProjectConfigPage(self.api, self.current_project)
        page.projectConfigChanged.connect(self._project_config_changed)
        self.open_tabs[tab_id] = page
        target = self._active_workspace()
        index = target.insertTab(0, page, "Project Config")
        apply_i18n(page, self.language)
        target.setTabText(index, self._translated_tab_title(tab_id))
        target.setCurrentIndex(index)
        self.workspace = target

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
                self._focus_widget_tab(existing)
            return
        page = self._make_action_page(tab_id)
        if hasattr(page, "settingsSaved"):
            page.settingsSaved.connect(self._settings_changed)
        if self.ros_graph_cache:
            handler = getattr(page, "set_graph_data", None)
            if callable(handler):
                handler(self.ros_graph_cache)
        self.open_tabs[tab_id] = page
        target = self._active_workspace()
        index = target.addTab(page, self._tab_title(tab_id))
        apply_i18n(page, self.language)
        target.setTabText(index, self._translated_tab_title(tab_id))
        if switch:
            target.setCurrentIndex(index)
            self.workspace = target

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

    def _translated_tab_title(self, tab_id: str) -> str:
        title = self._tab_title(tab_id)
        return text(title, self.language)

    def _ensure_workspace(self, *, allow_empty: bool = False) -> None:
        if self.current_project is None and allow_empty and self.centralWidget() is self.empty:
            container = self._create_workspace_container()
            self.open_tabs = {}
            self.setCentralWidget(container)
            return
        if self.workspace_splitter is None or self.centralWidget() is not self.workspace_splitter:
            self._load_project_workspace()

    def toggle_inspector(self) -> None:
        dock = self._ensure_inspector()
        dock.setVisible(not dock.isVisible())
        self._save_ui_state()

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
        worker = ApiWorker(self.api.get, "/api/ros/graph", timeout=30.0)
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
            self.inspector.set_project(self.current_project)
            self.inspector.graphUpdated.connect(self._ros_graph_updated)
            self.inspector_dock.setWidget(self.inspector)
        except Exception as exc:
            fallback = QLabel(f"Inspector failed to initialize:\n{exc}")
            fallback.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            self.inspector_dock.setWidget(fallback)
            self.inspector = None
        self.inspector_dock.visibilityChanged.connect(lambda _visible: self._save_ui_state())
        self.addDockWidget(Qt.RightDockWidgetArea, self.inspector_dock)
        visible = bool(self._ui_settings().get("inspector_visible", True))
        self.inspector_dock.setVisible(visible)
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
        pane = self.sender()
        if not isinstance(pane, QTabWidget):
            pane = self.workspace
        widget = pane.widget(index)
        for tab_id, tab_widget in list(self.open_tabs.items()):
            if tab_widget is widget:
                self.open_tabs.pop(tab_id, None)
                break
        pane.removeTab(index)
        if widget is not None:
            widget.deleteLater()
        self._remove_empty_workspace_panes()

    def _workspace_tab_changed(self, _index: int) -> None:
        if self._restoring_workspace:
            return
        self._save_ui_state()

    def _restore_startup_state(self) -> None:
        try:
            settings = self.api.get("/api/settings", timeout=5.0)
        except Exception:
            settings = {}
        self.settings = settings if isinstance(settings, dict) else {}
        self.language = normalize_language(str(self.settings.get("language", "en")))
        ui = self._ui_settings()
        self.apply_ui_scale(float(ui.get("scale", 1.0) or 1.0), persist=False)
        project_path = str(ui.get("last_project_path") or "")
        if project_path:
            try:
                self.current_project = self.api.open_project_path(project_path)
                self._load_project_workspace()
                self.update_project_summary()
            except Exception as exc:
                self.statusBar().showMessage(f"Could not restore last project: {exc}")
        if bool(ui.get("inspector_visible", True)):
            self._ensure_inspector()
        self.retranslate()

    def _ui_settings(self) -> dict:
        ui = self.settings.get("ui", {}) if isinstance(self.settings.get("ui"), dict) else {}
        return ui

    def _current_tab_id(self) -> str:
        active = self._active_workspace()
        return self._tab_id_for_widget(active.currentWidget())

    def _remember_project(self, project: ProjectSummary) -> None:
        settings = dict(self.settings or {})
        recent = settings.get("recent_projects", []) if isinstance(settings.get("recent_projects"), list) else []
        row = {"key": project.key, "name": project.name, "version": project.version, "path": project.path, "config_id": project.config_id}
        recent = [item for item in recent if not (isinstance(item, dict) and str(item.get("path", "")) == project.path)]
        recent.insert(0, row)
        settings["recent_projects"] = recent[:20]
        settings.setdefault("ui", {})
        settings["ui"]["last_project_path"] = project.path
        self._write_settings(settings)

    def _sync_inspector_project(self) -> None:
        if self.inspector is not None:
            self.inspector.set_project(self.current_project)

    def _configure_workspace(self, widget: QTabWidget) -> None:
        widget.setTabsClosable(True)
        widget.setMovable(True)
        widget.setDocumentMode(True)
        widget.tabCloseRequested.connect(self.close_workspace_tab)
        widget.currentChanged.connect(self._workspace_tab_changed)
        widget.tabBar().setContextMenuPolicy(Qt.CustomContextMenu)
        widget.tabBar().customContextMenuRequested.connect(lambda pos, pane=widget: self._show_tab_context_menu(pane, pos))

    def _show_tab_context_menu(self, pane: QTabWidget, pos) -> None:
        index = pane.tabBar().tabAt(pos)
        if index < 0:
            return
        pane.setCurrentIndex(index)
        self.workspace = pane
        menu = QMenu(self)
        split_left = menu.addAction("Split Left")
        split_right = menu.addAction("Split Right")
        split_up = menu.addAction("Split Up")
        split_down = menu.addAction("Split Down")
        if len(self.workspace_panes) >= 3:
            for action in [split_left, split_right, split_up, split_down]:
                action.setEnabled(False)
                action.setToolTip("Maximum 3 panes")
        split_left.triggered.connect(lambda: self.split_current_tab("left"))
        split_right.triggered.connect(lambda: self.split_current_tab("right"))
        split_up.triggered.connect(lambda: self.split_current_tab("up"))
        split_down.triggered.connect(lambda: self.split_current_tab("down"))
        apply_i18n(menu, self.language)
        menu.exec(pane.tabBar().mapToGlobal(pos))

    def split_current_tab(self, direction: str) -> None:
        source = self._active_workspace()
        index = source.currentIndex()
        if index < 0:
            return
        if len(self.workspace_panes) >= 3:
            self.statusBar().showMessage("Maximum 3 workspace panes")
            return
        widget = source.widget(index)
        if widget is None:
            return
        tab_id = self._tab_id_for_widget(widget)
        title = source.tabText(index)
        source.removeTab(index)
        target = self._new_workspace_pane()
        target.addTab(widget, title)
        target.setCurrentWidget(widget)
        self._insert_workspace_pane(target, direction, source)
        self.workspace = target
        if tab_id:
            target.setTabText(target.indexOf(widget), self._translated_tab_title(tab_id))
        self._rebalance_workspace_panes()
        self.statusBar().showMessage(f"Split tab {direction}; panes={len(self.workspace_panes)}/3")

    def _insert_workspace_pane(self, pane: QTabWidget, direction: str, source: QTabWidget) -> None:
        if self.workspace_splitter is None:
            return
        orientation = Qt.Vertical if direction in {"up", "down"} else Qt.Horizontal
        if self.workspace_splitter.orientation() != orientation and len(self.workspace_panes) == 1:
            self.workspace_splitter.setOrientation(orientation)
        elif self.workspace_splitter.orientation() != orientation:
            self.statusBar().showMessage("Mixed directions use the current splitter orientation.")
        source_index = self.workspace_splitter.indexOf(source)
        if source_index < 0:
            source_index = len(self.workspace_panes) - 1
        insert_at = source_index if direction in {"left", "up"} else source_index + 1
        self.workspace_panes.insert(max(0, min(insert_at, len(self.workspace_panes))), pane)
        self.workspace_splitter.insertWidget(max(0, min(insert_at, self.workspace_splitter.count())), pane)

    def _remove_empty_workspace_panes(self) -> None:
        if self.workspace_splitter is None:
            return
        for pane in list(self.workspace_panes):
            if pane.count() > 0 or len(self.workspace_panes) <= 1:
                continue
            self.workspace_panes.remove(pane)
            pane.setParent(None)
            pane.deleteLater()
        if self.workspace not in self.workspace_panes and self.workspace_panes:
            self.workspace = self.workspace_panes[0]
        self._rebalance_workspace_panes()

    def _rebalance_workspace_panes(self) -> None:
        if self.workspace_splitter is None or not self.workspace_panes:
            return
        self.workspace_splitter.setSizes([max(1, 1000 // len(self.workspace_panes)) for _pane in self.workspace_panes])

    def zoom_in(self) -> None:
        self.apply_ui_scale(self.ui_scale + 0.1)

    def zoom_out(self) -> None:
        self.apply_ui_scale(self.ui_scale - 0.1)

    def reset_zoom(self) -> None:
        self.apply_ui_scale(1.0)

    def apply_ui_scale(self, scale: float, *, persist: bool = True) -> None:
        scale = max(0.7, min(1.4, round(float(scale), 2)))
        self.ui_scale = scale
        app = QApplication.instance()
        if app is None:
            return
        font = app.font()
        font.setPointSizeF(max(7.0, self._base_font_point_size * scale))
        app.setFont(font)
        self.setFont(font)
        for widget in [self.centralWidget(), self.inspector_dock, self.inspector, *self.open_tabs.values()]:
            if widget is not None:
                widget.setFont(font)
                for child in widget.findChildren(QWidget):
                    child.setFont(font)
                widget.updateGeometry()
                widget.update()
        self.statusBar().showMessage(f"UI scale: {scale:.0%}")
        if persist:
            settings = dict(self.settings or {})
            settings.setdefault("ui", {})
            settings["ui"]["scale"] = scale
            self._write_settings(settings)

    def open_tutorial_guide(self) -> None:
        guide = Path(__file__).resolve().parents[3] / "RoboDataset-Studio-V3-Guide.html"
        if guide.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(guide)))
            return
        self.open_action_tab("tutorial")

    def _settings_changed(self, settings: object) -> None:
        if isinstance(settings, dict):
            self.settings = settings
            self.language = normalize_language(str(settings.get("language") or self.language or "en"))
            ui = settings.get("ui", {}) if isinstance(settings.get("ui"), dict) else {}
            self.apply_ui_scale(float(ui.get("scale", self.ui_scale) or self.ui_scale), persist=False)
            self.retranslate()

    def retranslate(self) -> None:
        apply_i18n(self, self.language)
        for tab_id, widget in self.open_tabs.items():
            apply_i18n(widget, self.language)
            pane = self._pane_for_widget(widget)
            if pane is not None:
                index = pane.indexOf(widget)
                if index >= 0:
                    pane.setTabText(index, self._translated_tab_title(tab_id))
        if self.inspector_dock is not None:
            apply_i18n(self.inspector_dock, self.language)
        self.update_project_summary()

    def _project_config_changed(self, project: object) -> None:
        if isinstance(project, ProjectSummary):
            self.current_project = project
        elif self.current_project is not None:
            try:
                self.current_project = self.api.open_project_path(self.current_project.path)
            except Exception as exc:
                self.statusBar().showMessage(f"Project refresh failed: {exc}")
                return
        self.update_project_summary()
        if self.current_project is not None:
            self._remember_project(self.current_project)
        self._sync_inspector_project()
        sender = self.sender()
        for widget in self.open_tabs.values():
            setattr(widget, "project", self.current_project)
            refresh = getattr(widget, "on_project_config_changed", None)
            if callable(refresh):
                refresh(self.current_project)
            elif widget is not sender:
                fallback = getattr(widget, "refresh", None)
                if callable(fallback) and widget.__class__.__name__ == "ProjectConfigPage":
                    fallback()
        self.statusBar().showMessage("Project config refreshed across open tabs")

    def _save_ui_state(self) -> None:
        settings = dict(self.settings or {})
        settings.setdefault("ui", {})
        settings["ui"]["last_active_tab"] = self._current_tab_id()
        settings["ui"]["inspector_visible"] = bool(self.inspector_dock and self.inspector_dock.isVisible())
        settings["ui"]["scale"] = self.ui_scale
        if self.current_project is not None:
            settings["ui"]["last_project_path"] = self.current_project.path
        self._write_settings(settings)

    def _write_settings(self, settings: dict) -> None:
        try:
            saved = self.api.put("/api/settings", settings, timeout=10.0)
            self.settings = saved if isinstance(saved, dict) else settings
        except Exception as exc:
            self.statusBar().showMessage(f"Settings save failed: {exc}")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._save_ui_state()
        if self.inspector is not None:
            self.inspector.stop_workers()
        self.backend.stop()
        super().closeEvent(event)
