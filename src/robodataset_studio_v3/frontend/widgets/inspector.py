from __future__ import annotations

from PySide6.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget


class InspectorDock(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.tabs = QTabWidget()
        layout = QVBoxLayout(self)
        topic_page = QWidget()
        topic_layout = QVBoxLayout(topic_page)
        topic_layout.addWidget(QLabel("Topic Inspector: info / echo once / hz"))
        image_page = QWidget()
        image_layout = QVBoxLayout(image_page)
        image_layout.addWidget(QLabel("Image Monitor: preview / FPS / brightness / crop"))
        self.tabs.addTab(topic_page, "Topic Inspector")
        self.tabs.addTab(image_page, "Image Monitor")
        layout.addWidget(self.tabs)

    def show_topic(self) -> None:
        self.tabs.setCurrentIndex(0)

    def show_image(self) -> None:
        self.tabs.setCurrentIndex(1)
