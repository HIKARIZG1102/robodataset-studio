from __future__ import annotations

from PySide6.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget


class InspectorDock(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        topic_page = QWidget()
        topic_layout = QVBoxLayout(topic_page)
        topic_layout.addWidget(QLabel("Topic Inspector: info / echo once / hz"))
        image_page = QWidget()
        image_layout = QVBoxLayout(image_page)
        image_layout.addWidget(QLabel("Image Monitor: preview / FPS / brightness / crop"))
        tabs.addTab(topic_page, "Topic Inspector")
        tabs.addTab(image_page, "Image Monitor")
        layout.addWidget(tabs)
