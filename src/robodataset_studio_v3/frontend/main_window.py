from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool, QUrl
from PySide6.QtGui import QDesktopServices, QFontMetrics, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QInputDialog,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTabBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio_v3.frontend.backend_process import BackendProcess
from robodataset_studio_v3.frontend.i18n import apply_i18n, normalize_language, text
from robodataset_studio_v3.frontend.pages.collect_page import CollectPage
from robodataset_studio_v3.frontend.pages.convert_page import ConvertPage
from robodataset_studio_v3.frontend.pages.logs_page import LogsPage
from robodataset_studio_v3.frontend.pages.project_page import ProjectPage
from robodataset_studio_v3.frontend.pages.review_page import ReviewPage
from robodataset_studio_v3.frontend.pages.ros_page import RosPage
from robodataset_studio_v3.frontend.pages.settings_page import SettingsPage
from robodataset_studio_v3.frontend.pages.tutorial_page import TutorialPage
from robodataset_studio_v3.frontend.pages.upload_page import UploadPage
from robodataset_studio_v3.frontend.widgets.config_library_page import ConfigLibraryPage
from robodataset_studio_v3.frontend.widgets.inspector import InspectorDock
from robodataset_studio_v3.frontend.widgets.project_config_page import ProjectConfigPage
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
        self.workspace_host: QWidget | None = None
        self.workspace = QTabWidget()
        self._configure_workspace(self.workspace)
        self.setTabPosition(Qt.LeftDockWidgetArea, QTabWidget.North)
        self.setTabPosition(Qt.RightDockWidgetArea, QTabWidget.North)
        self.empty = self._empty_workspace()
        self.setCentralWidget(self.empty)
        self.inspector: InspectorDock | None = None
        self.inspector_dock: QDockWidget | None = None
        self.project_dock: QDockWidget | None = None
        self.config_dock: QDockWidget | None = None
        self.logs_dock: QDockWidget | None = None
        self.project_list: QListWidget | None = None
        self.config_list: QListWidget | None = None
        self.logs_list: QListWidget | None = None
        self.ros_graph_cache: dict | None = None
        self.refresh_graph_button: QPushButton | None = None
        self.project_summary = QLabel("")
        self.project_folder_status = QLabel("")
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
        self.menuBar().setStyleSheet(
            """
            QMenuBar {
                text-decoration: none;
            }
            QMenuBar::item {
                border: 0;
                border-bottom: 0;
                padding: 4px 9px;
                text-decoration: none;
            }
            QMenuBar::item:selected {
                border: 0;
                border-bottom: 0;
                background: palette(midlight);
                text-decoration: none;
            }
            """
        )

        file_menu = self.menuBar().addMenu("File")
        file_menu.aboutToShow.connect(self._show_project_sidebar_from_menu)
        file_menu.addAction("New Project", self.new_project)
        file_menu.addAction("Open Project Folder", self.open_project_folder)
        file_menu.addSeparator()
        file_menu.addAction("Refresh Projects", self.refresh_project_sidebar)

        config_menu = self.menuBar().addMenu("Config")
        config_menu.aboutToShow.connect(self._show_config_sidebar_from_menu)
        config_menu.addAction("New Config", self.new_config)
        config_menu.addAction("Config Library", self.open_config_library_tab)
        config_menu.addSeparator()
        config_menu.addAction("Refresh Configs", self.refresh_config_sidebar)

        tools_menu = self.menuBar().addMenu("Tools")
        tools_menu.addAction("Collect", lambda: self.open_action_tab("collect"))
        tools_menu.addAction("Data Review", lambda: self.open_action_tab("review"))
        tools_menu.addAction("Convert", lambda: self.open_action_tab("convert"))
        tools_menu.addAction("Upload", lambda: self.open_action_tab("upload"))

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

        self.menuBar().addAction("Logs", self.toggle_logs_sidebar)

        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction("Tutorial", self.open_tutorial_guide)
        help_menu.addAction("About", self.show_about)

    def _build_graph_button(self) -> None:
        refresh = QPushButton("Refresh Nodes/Topics")
        refresh.setObjectName("refreshGraphButton")
        refresh.setToolTip("Refresh the global ROS nodes and topics for Config, Discovery, and Inspector.")
        refresh.setCursor(Qt.PointingHandCursor)
        refresh.clicked.connect(self.refresh_ros_graph)
        refresh.setStyleSheet(
            """
            QPushButton#refreshGraphButton {
                margin: 1px 8px 1px 12px;
                padding: 2px 10px;
                border: 1px solid #2f6f9f;
                border-radius: 4px;
                color: #ffffff;
                background: #1f6aa5;
                font-weight: 600;
                min-height: 18px;
                max-height: 22px;
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
        self.project_summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.project_summary.setWordWrap(False)
        self.project_summary.setMinimumWidth(0)
        self.project_summary.setMaximumWidth(520)
        self.project_summary.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.project_folder_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.project_folder_status.setWordWrap(False)
        self.project_folder_status.setMinimumWidth(220)
        self.project_folder_status.setMaximumWidth(520)
        self.project_folder_status.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.statusBar().addWidget(self.project_summary, 1)
        self.statusBar().addPermanentWidget(self.project_folder_status, 0)
        self.update_project_summary()

    def update_project_summary(self) -> None:
        if self.current_project is None:
            self.project_summary.setText(text("Project: none | Config: none", self.language))
            self.project_folder_status.setText("Project folder: none")
            self.project_folder_status.setToolTip("")
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
        self._set_project_folder_status(self.current_project.path)

    def _set_project_folder_status(self, path: str) -> None:
        text_value = f"Project folder: {path}"
        metrics = QFontMetrics(self.project_folder_status.font())
        width = max(self.project_folder_status.maximumWidth() - 12, 80)
        self.project_folder_status.setText(metrics.elidedText(text_value, Qt.ElideMiddle, width))
        self.project_folder_status.setToolTip(text_value)

    def _empty_workspace(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        label = QLabel("Create or open a project to start.")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        return widget

    def toggle_project_sidebar(self) -> None:
        dock = self._ensure_project_sidebar()
        self._activate_sidebar_dock(dock)
        self.refresh_project_sidebar()

    def _show_project_sidebar_from_menu(self) -> None:
        dock = self._ensure_project_sidebar()
        self._activate_sidebar_dock(dock)
        self.refresh_project_sidebar()

    def _ensure_project_sidebar(self) -> QDockWidget:
        if self.project_dock is not None:
            return self.project_dock
        dock = QDockWidget("Projects", self)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea)
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.project_list = QListWidget()
        self._style_sidebar_list(self.project_list)
        self.project_list.currentItemChanged.connect(lambda item, _prev: self._preview_project_item(item))
        self.project_list.itemDoubleClicked.connect(self._open_project_item)
        self.project_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.project_list.customContextMenuRequested.connect(self._show_project_context_menu)
        layout.addWidget(self.project_list, 1)
        dock.setWidget(widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        self.project_dock = dock
        self._tabify_sidebar_dock(dock)
        self.refresh_project_sidebar()
        apply_i18n(dock, self.language)
        return dock

    def refresh_project_sidebar(self) -> None:
        if self.project_list is None:
            return
        self.project_list.blockSignals(True)
        self.project_list.clear()
        try:
            projects = self.api.list_projects()
        except Exception as exc:
            self.project_list.blockSignals(False)
            self.statusBar().showMessage(f"Cannot list projects: {exc}")
            return
        selected_item: QListWidgetItem | None = None
        for project in projects:
            marker = "▸" if self.current_project is not None and project.key == self.current_project.key else "•"
            item = QListWidgetItem(f"{marker}   {project.name} {project.version}")
            item.setToolTip(project.path)
            item.setData(Qt.UserRole, project)
            self.project_list.addItem(item)
            if self.current_project is not None and project.key == self.current_project.key:
                selected_item = item
        if selected_item is not None:
            self.project_list.setCurrentItem(selected_item)
        self.project_list.blockSignals(False)

    def _open_project_item(self, item: QListWidgetItem) -> None:
        project = item.data(Qt.UserRole)
        if isinstance(project, ProjectSummary):
            self.current_project = project
            self._remember_project(project)
            self.update_project_summary()
            self._load_project_workspace()
            self._update_project_sidebar_markers()

    def _update_project_sidebar_markers(self) -> None:
        if self.project_list is None:
            return
        self.project_list.blockSignals(True)
        selected_item: QListWidgetItem | None = None
        for row in range(self.project_list.count()):
            item = self.project_list.item(row)
            project = item.data(Qt.UserRole) if item is not None else None
            if not isinstance(project, ProjectSummary):
                continue
            is_current = self.current_project is not None and project.key == self.current_project.key
            marker = "▸" if is_current else "•"
            item.setText(f"{marker}   {project.name} {project.version}")
            if is_current:
                selected_item = item
        if selected_item is not None:
            self.project_list.setCurrentItem(selected_item)
        self.project_list.blockSignals(False)

    def _show_project_context_menu(self, pos) -> None:
        if self.project_list is None:
            return
        item = self.project_list.itemAt(pos)
        menu = QMenu(self)
        refresh_action = menu.addAction("Refresh")
        menu.addSeparator()
        open_action = menu.addAction("Open Project")
        info_action = menu.addAction("Properties")
        config_action = menu.addAction("Current Project Config")
        collect_action = menu.addAction("Collect")
        review_action = menu.addAction("Review")
        convert_action = menu.addAction("Convert")
        upload_action = menu.addAction("Upload")
        menu.addSeparator()
        rename_action = menu.addAction("Rename")
        delete_action = menu.addAction("Delete")
        permanent_delete_action = menu.addAction("Permanent Delete")
        menu.addSeparator()
        new_action = menu.addAction("New Project")
        if item is None:
            for action in [
                open_action,
                info_action,
                config_action,
                collect_action,
                review_action,
                convert_action,
                upload_action,
                rename_action,
                delete_action,
                permanent_delete_action,
            ]:
                action.setEnabled(False)
        action = menu.exec(self.project_list.mapToGlobal(pos))
        if action is None:
            return
        if action is refresh_action:
            self.refresh_project_sidebar()
            return
        if action is new_action:
            self.new_project()
            return
        if item is None:
            return
        if action is open_action:
            self._open_project_item(item)
        elif action is info_action:
            self._open_project_item(item)
            self.open_action_tab("project")
        elif action is config_action:
            self._open_project_item(item)
            self.open_project_config_tab(read_only=True)
        elif action is collect_action:
            self._open_project_item(item)
            self.open_action_tab("collect")
        elif action is review_action:
            self._open_project_item(item)
            self.open_action_tab("review")
        elif action is convert_action:
            self._open_project_item(item)
            self.open_action_tab("convert")
        elif action is upload_action:
            self._open_project_item(item)
            self.open_action_tab("upload")
        elif action is rename_action:
            project = item.data(Qt.UserRole)
            if isinstance(project, ProjectSummary):
                new_name, ok = QInputDialog.getText(self, "Rename Project", "New project key:", text=project.key)
                if ok and new_name.strip():
                    try:
                        renamed = self.api.rename_project(project.key, new_name.strip())
                        if self.current_project and self.current_project.key == project.key:
                            self.current_project = renamed
                            self._load_project_workspace()
                        self.refresh_project_sidebar()
                    except Exception as exc:
                        QMessageBox.warning(self, "Rename Project", f"Cannot rename project:\n{exc}")
        elif action is delete_action:
            project = item.data(Qt.UserRole)
            if isinstance(project, ProjectSummary):
                if QMessageBox.question(self, "Delete Project", f"Move project '{project.key}' to .deleted_projects?") == QMessageBox.Yes:
                    try:
                        self.api.delete_project(project.key)
                        if self.current_project and self.current_project.key == project.key:
                            self._clear_current_project_workspace()
                        self.refresh_project_sidebar()
                    except Exception as exc:
                        QMessageBox.warning(self, "Delete Project", f"Cannot delete project:\n{exc}")
        elif action is permanent_delete_action:
            project = item.data(Qt.UserRole)
            if isinstance(project, ProjectSummary):
                message = (
                    f"Permanently delete project '{project.key}'?\n\n"
                    f"This will remove the project directory from disk and cannot be undone:\n{project.path}"
                )
                answer = QMessageBox.warning(
                    self,
                    "Permanent Delete Project",
                    message,
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer == QMessageBox.Yes:
                    try:
                        self.api.permanently_delete_project(project.key)
                        if self.current_project and self.current_project.key == project.key:
                            self._clear_current_project_workspace()
                        self.refresh_project_sidebar()
                    except Exception as exc:
                        QMessageBox.warning(self, "Permanent Delete Project", f"Cannot permanently delete project:\n{exc}")

    def toggle_config_sidebar(self) -> None:
        dock = self._ensure_config_sidebar()
        self._activate_sidebar_dock(dock)
        self.refresh_config_sidebar()

    def _show_config_sidebar_from_menu(self) -> None:
        dock = self._ensure_config_sidebar()
        self._activate_sidebar_dock(dock)
        self.refresh_config_sidebar()

    def _ensure_config_sidebar(self) -> QDockWidget:
        if self.config_dock is not None:
            return self.config_dock
        dock = QDockWidget("Configs", self)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea)
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.config_list = QListWidget()
        self._style_sidebar_list(self.config_list)
        self.config_list.currentItemChanged.connect(lambda item, _prev: self._preview_config_item(item))
        self.config_list.itemDoubleClicked.connect(self._open_config_item)
        self.config_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.config_list.customContextMenuRequested.connect(self._show_config_context_menu)
        layout.addWidget(self.config_list, 1)
        dock.setWidget(widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        self.config_dock = dock
        self._tabify_sidebar_dock(dock)
        self.refresh_config_sidebar()
        apply_i18n(dock, self.language)
        return dock

    def refresh_config_sidebar(self) -> None:
        if self.config_list is None:
            return
        self.config_list.clear()
        selected_id = ""
        page = self.open_tabs.get("config_library")
        if isinstance(page, ConfigLibraryPage):
            selected_id = str(page.loaded_config_id or page.selected_config_id() or "")
        try:
            configs = self.api.list_configs()
        except Exception as exc:
            self.statusBar().showMessage(f"Cannot list configs: {exc}")
            return
        for config in configs:
            config_id = str(config.get("id") or "")
            marker = "▸" if selected_id and config_id == selected_id else "•"
            item = QListWidgetItem(f"{marker}   {config_id}")
            item.setData(Qt.UserRole, config_id)
            self.config_list.addItem(item)
            if selected_id and config_id == selected_id:
                self.config_list.setCurrentItem(item)

    def _refresh_open_config_library(self, select_config_id: str = "") -> None:
        page = self.open_tabs.get("config_library")
        if not isinstance(page, ConfigLibraryPage):
            return
        page.refresh_list()
        if select_config_id:
            index = page.config_select.findData(select_config_id)
            if index >= 0:
                page.config_select.setCurrentIndex(index)
                page.load_selected()
                self.refresh_config_sidebar()

    def _open_config_item(self, item: QListWidgetItem) -> None:
        config_id = str(item.data(Qt.UserRole) or "")
        self.open_config_library_tab()
        page = self.open_tabs.get("config_library")
        if isinstance(page, ConfigLibraryPage):
            index = page.config_select.findData(config_id)
            if index >= 0:
                page.config_select.setCurrentIndex(index)
                page.load_selected()

    def _show_config_context_menu(self, pos) -> None:
        if self.config_list is None:
            return
        item = self.config_list.itemAt(pos)
        menu = QMenu(self)
        open_action = menu.addAction("Open Config")
        duplicate_action = menu.addAction("Duplicate")
        rename_action = menu.addAction("Rename")
        delete_action = menu.addAction("Delete")
        menu.addSeparator()
        new_action = menu.addAction("New")
        if item is None:
            for action in [open_action, duplicate_action, rename_action, delete_action]:
                action.setEnabled(False)
        action = menu.exec(self.config_list.mapToGlobal(pos))
        if action is None:
            return
        if action is new_action:
            self.open_config_library_tab()
            self.new_config()
            return
        if item is None:
            return
        if action is open_action:
            self._open_config_item(item)
        elif action is duplicate_action:
            config_id = str(item.data(Qt.UserRole) or "")
            try:
                copied = self.api.duplicate_config(config_id)
                self._config_library_changed(str(copied.get("id") or ""))
            except Exception as exc:
                QMessageBox.warning(self, "Duplicate Config", f"Cannot duplicate config:\n{exc}")
        elif action is rename_action:
            config_id = str(item.data(Qt.UserRole) or "")
            new_name, ok = QInputDialog.getText(self, "Rename Config", "New config name:", text=config_id)
            if ok and new_name.strip():
                if self._warn_if_config_in_use(config_id, "rename"):
                    return
                try:
                    renamed = self.api.rename_config(config_id, new_name.strip())
                    new_id = str(renamed.get("id") or new_name.strip())
                    self._config_library_changed(new_id)
                    for row in range(self.config_list.count()):
                        candidate = self.config_list.item(row)
                        if candidate and str(candidate.data(Qt.UserRole) or "") == new_id:
                            self.config_list.setCurrentItem(candidate)
                            break
                except Exception as exc:
                    QMessageBox.warning(self, "Rename Config", f"Cannot rename config:\n{exc}")
        elif action is delete_action:
            config_id = str(item.data(Qt.UserRole) or "")
            if self._warn_if_config_in_use(config_id, "delete"):
                return
            if QMessageBox.question(self, "Delete Config", f"Delete config '{config_id}'?") == QMessageBox.Yes:
                try:
                    self.api.delete_config(config_id)
                    self._config_library_changed("")
                except Exception as exc:
                    QMessageBox.warning(self, "Delete Config", f"Cannot delete config:\n{exc}")

    def toggle_logs_sidebar(self) -> None:
        dock = self._ensure_logs_sidebar()
        self._activate_sidebar_dock(dock)
        self.refresh_logs_sidebar()

    def _ensure_logs_sidebar(self) -> QDockWidget:
        if self.logs_dock is not None:
            return self.logs_dock
        dock = QDockWidget("Logs", self)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        widget = QWidget()
        layout = QVBoxLayout(widget)
        open_button = QPushButton("Open Logs")
        self.logs_list = QListWidget()
        self.logs_list.currentItemChanged.connect(lambda item, _prev: self._preview_log_item(item))
        self.logs_list.itemDoubleClicked.connect(self._open_log_item)
        open_button.clicked.connect(lambda: self.open_action_tab("logs"))
        layout.addWidget(open_button)
        layout.addWidget(self.logs_list, 1)
        dock.setWidget(widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        self.logs_dock = dock
        self._tabify_sidebar_dock(dock)
        self.refresh_logs_sidebar()
        apply_i18n(dock, self.language)
        return dock

    def refresh_logs_sidebar(self) -> None:
        if self.logs_list is None:
            return
        self.logs_list.clear()
        try:
            tasks = self.api.list_tasks()
        except Exception as exc:
            self.statusBar().showMessage(f"Cannot list logs/tasks: {exc}")
            return
        for task in tasks:
            if not isinstance(task, dict):
                continue
            task_id = str(task.get("id") or task.get("task_id") or "-")
            status = str(task.get("status") or "-")
            kind = str(task.get("kind") or task.get("name") or task.get("action") or "task")
            item = QListWidgetItem(f"{status} | {kind} | {task_id}")
            item.setToolTip(str(task))
            item.setData(Qt.UserRole, task)
            self.logs_list.addItem(item)

    def _activate_sidebar_dock(self, dock: QDockWidget) -> None:
        dock.show()
        dock.raise_()

    def _tabify_sidebar_dock(self, dock: QDockWidget) -> None:
        self.setTabPosition(Qt.LeftDockWidgetArea, QTabWidget.North)
        self.setTabPosition(Qt.RightDockWidgetArea, QTabWidget.North)
        for existing in [self.project_dock, self.config_dock, self.logs_dock]:
            if existing is not None and existing is not dock:
                self.tabifyDockWidget(existing, dock)
                self.setTabPosition(Qt.LeftDockWidgetArea, QTabWidget.North)
                self.setTabPosition(Qt.RightDockWidgetArea, QTabWidget.North)
                dock.raise_()
                return

    def _style_sidebar_list(self, widget: QListWidget) -> None:
        widget.setStyleSheet(
            """
            QListWidget {
                outline: 0;
            }
            QListWidget::item {
                padding: 7px 8px 7px 10px;
                border: 0;
                border-left: 3px solid transparent;
            }
            QListWidget::item:selected {
                border-left-color: #1f6aa5;
                background: #d9ecfb;
                color: #10202f;
                font-weight: 600;
            }
            """
        )

    def _preview_project_item(self, item: QListWidgetItem | None) -> None:
        if item is None:
            return
        project = item.data(Qt.UserRole)
        if isinstance(project, ProjectSummary):
            status = "recorded" if project.has_recorded_data else "editable"
            self.statusBar().showMessage(f"{project.key} | config={project.config_id or '-'} | {status} | {project.path}")

    def _clear_current_project_workspace(self) -> None:
        self.current_project = None
        self.open_tabs = {}
        self.workspace_panes = []
        self.workspace_splitter = None
        self.workspace_host = None
        self.setCentralWidget(self.empty)
        self.update_project_summary()
        self._sync_inspector_project()

    def _preview_config_item(self, item: QListWidgetItem | None) -> None:
        if item is None:
            return
        config_id = str(item.data(Qt.UserRole) or "")
        if config_id:
            self.statusBar().showMessage(f"Config selected: {config_id}")

    def _warn_if_config_in_use(self, config_id: str, action: str) -> bool:
        try:
            projects = self.api.list_projects()
        except Exception as exc:
            QMessageBox.warning(self, "Config In Use Check", f"Cannot check project references:\n{exc}")
            return True
        references = [project for project in projects if project.config_id == config_id]
        if not references:
            return False
        rows = "\n".join(f"- {project.name} {project.version} ({project.key})" for project in references[:12])
        if len(references) > 12:
            rows += f"\n... and {len(references) - 12} more"
        QMessageBox.warning(
            self,
            "Config In Use",
            f"Cannot {action} config '{config_id}' because it is used by project(s):\n{rows}\n\n"
            "Open a new project version or switch those projects to another config first.",
        )
        return True

    def _config_library_changed(self, select_config_id: str = "") -> None:
        self.refresh_config_sidebar()
        self._refresh_open_config_library(select_config_id)
        for widget in self.open_tabs.values():
            refresh_library = getattr(widget, "refresh_library", None)
            if callable(refresh_library):
                refresh_library()
        if select_config_id and self.config_list is not None:
            for row in range(self.config_list.count()):
                item = self.config_list.item(row)
                if item is not None and str(item.data(Qt.UserRole) or "") == select_config_id:
                    self.config_list.setCurrentItem(item)
                    break
        self.statusBar().showMessage("Config library refreshed")

    def _preview_log_item(self, item: QListWidgetItem | None) -> None:
        if item is None:
            return
        task = item.data(Qt.UserRole)
        if isinstance(task, dict):
            self.statusBar().showMessage(
                f"Task selected: {task.get('task_id', '-')} | {task.get('status', '-')} | {task.get('message', '')}"
            )

    def _open_log_item(self, item: QListWidgetItem) -> None:
        self.open_action_tab("logs")
        page = self.open_tabs.get("logs")
        selector = getattr(page, "select_task", None)
        task = item.data(Qt.UserRole)
        task_id = str(task.get("task_id") or "") if isinstance(task, dict) else ""
        if task_id and callable(selector):
            selector(task_id)

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

    def _workspace_central_widget(self, splitter: QSplitter) -> QWidget:
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 7, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(splitter)
        self.workspace_host = host
        return host

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
        dialog = NewProjectDialog(self.api, self, default_root=self._project_folder_start_dir())
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
        self.refresh_project_sidebar()

    def open_config_library_tab(self) -> None:
        self._ensure_workspace(allow_empty=True)
        tab_id = "config_library"
        existing = self.open_tabs.get(tab_id)
        if existing is not None:
            self._focus_widget_tab(existing)
            return
        page = ConfigLibraryPage(self.api, self.current_project)
        page.projectConfigChanged.connect(self._project_config_changed)
        page.libraryChanged.connect(self._config_library_changed)
        if self.ros_graph_cache:
            page.set_graph_data(self.ros_graph_cache)
        self.open_tabs[tab_id] = page
        target = self._active_workspace()
        index = target.insertTab(0, page, "Config Library")
        apply_i18n(page, self.language)
        target.setTabText(index, self._translated_tab_title(tab_id))
        self._apply_tab_close_policy(target, tab_id, index)
        target.setCurrentIndex(index)
        self.workspace = target

    def new_config(self) -> None:
        self.open_config_library_tab()
        page = self.open_tabs.get("config_library")
        starter = getattr(page, "start_new_config", None)
        if callable(starter):
            starter()

    def open_project_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open Project Folder", self._project_folder_start_dir())
        if not path:
            return
        try:
            project = self.api.open_project_path(path)
        except Exception as exc:
            QMessageBox.warning(self, "Open Project Folder", f"Cannot open project folder:\n{exc}")
            return
        self.current_project = project
        self._remember_project(project)
        self.update_project_summary()
        self._load_project_workspace()
        self.refresh_project_sidebar()

    def _project_folder_start_dir(self) -> str:
        ui = self._ui_settings()
        last_parent = str(ui.get("last_project_parent_path") or "")
        if last_parent and Path(last_parent).exists():
            return last_parent
        if self.current_project is not None:
            parent = str(Path(self.current_project.path).parent)
            if Path(parent).exists():
                return parent
        try:
            default_root = self.api.default_project_root()
        except Exception:
            default_root = ""
        return default_root if default_root and Path(default_root).exists() else str(Path.cwd())

    def _load_project_workspace(self) -> None:
        if self.current_project is None:
            return
        if self._has_core_workspace():
            self._restoring_workspace = True
            self._sync_open_pages_to_project()
            self._ensure_core_tabs()
            self._restoring_workspace = False
        else:
            container = self._create_workspace_container()
            self.open_tabs = {}
            self._restoring_workspace = True
            self.setCentralWidget(self._workspace_central_widget(container))
            self._ensure_core_tabs()
            self._restoring_workspace = False
        self._sync_inspector_project()
        self.update_project_summary()
        last_tab = self._ui_settings().get("last_active_tab", "")
        if isinstance(last_tab, str) and last_tab in self.open_tabs:
            self._focus_widget_tab(self.open_tabs[last_tab])

    def _has_core_workspace(self) -> bool:
        if self.workspace_splitter is None or self.centralWidget() is not self.workspace_host:
            return False
        return all(tab_id in self.open_tabs for tab_id in ["project", "collect", "review", "convert", "upload"])

    def _ensure_core_tabs(self) -> None:
        for tab_id in ["project", "collect", "review", "convert", "upload"]:
            self._add_action_tab(tab_id, switch=False)

    def _sync_open_pages_to_project(self) -> None:
        for widget in self.open_tabs.values():
            setattr(widget, "project", self.current_project)
            refresh = getattr(widget, "on_project_config_changed", None)
            if callable(refresh):
                refresh(self.current_project)

    def open_project_config_tab(self, *, read_only: bool = False) -> None:
        if self.current_project is None:
            QMessageBox.information(self, "Project Config", "Open or create a project first.")
            return
        self._ensure_workspace()
        tab_id = "project_config_readonly" if read_only else "project_config"
        existing = self.open_tabs.get(tab_id)
        if existing is not None:
            self._focus_widget_tab(existing)
            return
        page = ProjectConfigPage(self.api, self.current_project, read_only=read_only)
        page.projectConfigChanged.connect(self._project_config_changed)
        self.open_tabs[tab_id] = page
        target = self._active_workspace()
        index = target.insertTab(0, page, "Project Config")
        apply_i18n(page, self.language)
        target.setTabText(index, self._translated_tab_title(tab_id))
        self._apply_tab_close_policy(target, tab_id, index)
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
        self._apply_tab_close_policy(target, tab_id, index)
        if switch:
            target.setCurrentIndex(index)
            self.workspace = target

    def _make_action_page(self, tab_id: str) -> QWidget:
        project = self.current_project
        if tab_id == "project":
            return ProjectPage(self.api, project)
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
        if tab_id == "settings":
            return SettingsPage(self.api, project)
        if tab_id == "tutorial":
            return TutorialPage()
        return LogsPage(self.api, project)

    def _tab_title(self, tab_id: str) -> str:
        return {
            "collect": "Collect",
            "project": "Properties",
            "ros": "ROS",
            "review": "Review",
            "convert": "Convert",
            "upload": "Upload",
            "settings": "Settings",
            "tutorial": "Tutorial",
            "logs": "Logs",
            "project_config_readonly": "Project Config",
        }.get(tab_id, tab_id.title())

    def _translated_tab_title(self, tab_id: str) -> str:
        title = self._tab_title(tab_id)
        return text(title, self.language)

    def _ensure_workspace(self, *, allow_empty: bool = False) -> None:
        if self.current_project is None and allow_empty and self.centralWidget() is self.empty:
            container = self._create_workspace_container()
            self.open_tabs = {}
            self.setCentralWidget(self._workspace_central_widget(container))
            return
        if self.workspace_splitter is None or self.centralWidget() is not self.workspace_host:
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
                    self.refresh_graph_button.setText("Refresh Nodes/Topics")
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
        tab_id = self._tab_id_for_widget(widget)
        if tab_id in {"project", "collect", "review", "convert", "upload"}:
            self.statusBar().showMessage("Core project tabs cannot be closed.")
            return
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
        settings["ui"]["last_project_parent_path"] = str(Path(project.path).parent)
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

    def _apply_tab_close_policy(self, pane: QTabWidget, tab_id: str, index: int) -> None:
        if tab_id in {"project", "collect", "review", "convert", "upload"}:
            pane.tabBar().setTabButton(index, QTabBar.ButtonPosition.RightSide, None)
            pane.tabBar().setTabButton(index, QTabBar.ButtonPosition.LeftSide, None)

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
        menu.addSeparator()
        merge_all = menu.addAction("Merge All Panes")
        if len(self.workspace_panes) >= 3:
            for action in [split_left, split_right, split_up, split_down]:
                action.setEnabled(False)
                action.setToolTip("Maximum 3 panes")
        if len(self.workspace_panes) <= 1:
            merge_all.setEnabled(False)
        split_left.triggered.connect(lambda: self.split_current_tab("left"))
        split_right.triggered.connect(lambda: self.split_current_tab("right"))
        split_up.triggered.connect(lambda: self.split_current_tab("up"))
        split_down.triggered.connect(lambda: self.split_current_tab("down"))
        merge_all.triggered.connect(self.merge_workspace_panes)
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
        new_index = target.addTab(widget, title)
        target.setCurrentWidget(widget)
        self._insert_workspace_pane(target, direction, source)
        self.workspace = target
        if tab_id:
            target.setTabText(new_index, self._translated_tab_title(tab_id))
            self._apply_tab_close_policy(target, tab_id, new_index)
        self._rebalance_workspace_panes()
        self.statusBar().showMessage(f"Split tab {direction}; panes={len(self.workspace_panes)}/3")

    def merge_workspace_panes(self) -> None:
        if not self.workspace_panes:
            return
        target = self.workspace_panes[0]
        for pane in list(self.workspace_panes[1:]):
            while pane.count():
                widget = pane.widget(0)
                title = pane.tabText(0)
                tab_id = self._tab_id_for_widget(widget)
                pane.removeTab(0)
                index = target.addTab(widget, self._translated_tab_title(tab_id) if tab_id else title)
                if tab_id:
                    self._apply_tab_close_policy(target, tab_id, index)
            self.workspace_panes.remove(pane)
            pane.setParent(None)
            pane.deleteLater()
        self.workspace = target
        if self.workspace_splitter is not None:
            self.workspace_splitter.setOrientation(Qt.Horizontal)
        self._rebalance_workspace_panes()
        self.statusBar().showMessage("Workspace panes merged.")

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

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            "About RoboDataset Studio V3",
            "\n".join(
                [
                    "RoboDataset Studio V3",
                    "Copyright (c) 2026 RoboDataset Studio contributors.",
                    "",
                    "Developers:",
                    "  HIKARIZG1102",
                    "  RoboDataset Studio contributors",
                    "",
                    "Purpose: ROS2 listener-only robot dataset collection, review, conversion, and upload.",
                    "License/copyright: project-local repository metadata applies.",
                ]
            ),
        )

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
        if self.project_dock is not None:
            apply_i18n(self.project_dock, self.language)
        if self.config_dock is not None:
            apply_i18n(self.config_dock, self.language)
        if self.logs_dock is not None:
            apply_i18n(self.logs_dock, self.language)
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
