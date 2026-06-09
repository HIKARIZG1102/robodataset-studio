from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .pages import (
    AppContext,
    ConfigPage,
    ConvertPage,
    DiscoveryPage,
    EnvironmentPage,
    InspectorPage,
    ProcessPage,
    ProjectPage,
    RecordingPage,
    ReviewPage,
    SettingsPage,
    UploadPage,
)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("RoboDataset Studio")
        self.resize(1280, 820)
        self.ctx = AppContext()
        self._tool_windows: list[QMainWindow] = []
        self.inspector_page: InspectorPage | None = None

        self.nav = QListWidget()
        self.stack = QStackedWidget()
        pages = [
            ("1. 配置与 ROS Topic", self._config_workspace()),
            ("2. 采集", self._single_page_workspace(RecordingPage(self.ctx))),
            ("3. 数据 Review", self._single_page_workspace(ReviewPage(self.ctx))),
            ("4. 数据转换", self._single_page_workspace(ConvertPage(self.ctx))),
            ("5. 上传", self._single_page_workspace(UploadPage(self.ctx))),
        ]
        for name, page in pages:
            self.nav.addItem(name)
            self.stack.addWidget(page)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        process_button = QPushButton("Process")
        settings_button = QPushButton("Settings")
        process_button.clicked.connect(self.open_process)
        settings_button.clicked.connect(self.open_settings)

        side = QVBoxLayout()
        side.addWidget(self.nav)
        side.addStretch(1)
        side.addWidget(process_button)
        side.addWidget(settings_button)

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.addLayout(side, 1)
        layout.addWidget(self.stack, 5)
        self.setCentralWidget(root)

    def _config_workspace(self) -> QTabWidget:
        tabs = QTabWidget()
        self.inspector_page = InspectorPage(self.ctx)
        tabs.addTab(ProjectPage(self.ctx), "Project")
        tabs.addTab(EnvironmentPage(self.ctx), "Environment")
        tabs.addTab(DiscoveryPage(self.ctx), "Discovery")
        tabs.addTab(self.inspector_page, "Inspector")
        tabs.addTab(ConfigPage(self.ctx), "Config")
        return tabs

    def _single_page_workspace(self, page: QWidget) -> QWidget:
        return page

    def open_process(self) -> None:
        self._open_tool_window("Process", ProcessPage(self.ctx))

    def open_settings(self) -> None:
        self._open_tool_window("Settings", SettingsPage(self.ctx))

    def _open_tool_window(self, title: str, page: QWidget) -> None:
        window = QMainWindow(self)
        window.setWindowTitle(f"RoboDataset Studio - {title}")
        window.resize(980, 640)
        window.setCentralWidget(page)
        self._tool_windows.append(window)
        window.destroyed.connect(lambda: self._tool_windows.remove(window) if window in self._tool_windows else None)
        window.show()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self.inspector_page is not None:
            self.inspector_page.stop_all_inspector_tasks()
        self.ctx.process_manager.stop_all()
        super().closeEvent(event)
