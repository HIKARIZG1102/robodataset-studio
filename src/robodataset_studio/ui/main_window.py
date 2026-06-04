from __future__ import annotations

from PySide6.QtWidgets import QListWidget, QMainWindow, QStackedWidget, QHBoxLayout, QWidget

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

        self.nav = QListWidget()
        self.stack = QStackedWidget()
        pages = [
            ("1. Project", ProjectPage(self.ctx)),
            ("2. Environment", EnvironmentPage(self.ctx)),
            ("3. Discovery", DiscoveryPage(self.ctx)),
            ("4. Inspector", InspectorPage(self.ctx)),
            ("5. Config", ConfigPage(self.ctx)),
            ("6. Recording", RecordingPage(self.ctx)),
            ("7. Review", ReviewPage(self.ctx)),
            ("8. Convert", ConvertPage(self.ctx)),
            ("9. Upload", UploadPage(self.ctx)),
            ("Process", ProcessPage(self.ctx)),
            ("Settings", SettingsPage(self.ctx)),
        ]
        for name, page in pages:
            self.nav.addItem(name)
            self.stack.addWidget(page)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.addWidget(self.nav, 1)
        layout.addWidget(self.stack, 5)
        self.setCentralWidget(root)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.ctx.process_manager.stop_all()
        super().closeEvent(event)

