from __future__ import annotations

import base64
import json
from typing import Any

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from robodataset_studio_v3.frontend.api_client import ApiClient
from robodataset_studio_v3.frontend.worker import ApiWorker


class InspectorDock(QWidget):
    def __init__(self, api: ApiClient) -> None:
        super().__init__()
        self.api = api
        self.pool = QThreadPool.globalInstance()
        self.tabs = QTabWidget()
        self.node = QComboBox()
        self.node.setEditable(True)
        self.topic = QComboBox()
        self.topic.setEditable(True)
        self.image_topic = QComboBox()
        self.image_topic.setEditable(True)
        self.topic_log = QPlainTextEdit()
        self.topic_log.setReadOnly(True)
        self.node_log = QPlainTextEdit()
        self.node_log.setReadOnly(True)
        self.image_meta = QLabel("image: -")
        self.image_label = QLabel("No image")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumHeight(220)
        self.image_label.setStyleSheet("border: 1px solid #999;")
        self._topic_types: dict[str, str] = {}
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(self._toolbar())
        layout.addWidget(self.tabs)
        self.tabs.addTab(self._topic_page(), "Topic Inspector")
        self.tabs.addTab(self._image_page(), "Image Monitor")

    def _toolbar(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_graph)
        layout.addWidget(refresh)
        layout.addStretch(1)
        return widget

    def _topic_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        node_row = QHBoxLayout()
        node_row.addWidget(QLabel("Node"))
        node_row.addWidget(self.node, 1)
        node_button = QPushButton("Node Details")
        node_button.clicked.connect(self.node_details)
        node_row.addWidget(node_button)

        topic_row = QHBoxLayout()
        topic_row.addWidget(QLabel("Topic"))
        topic_row.addWidget(self.topic, 1)
        for label, path in [
            ("Info", "/api/ros/topic-info"),
            ("Echo Once", "/api/ros/topic-echo-once"),
            ("Hz", "/api/ros/topic-hz"),
        ]:
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, api_path=path: self.topic_action(api_path))
            topic_row.addWidget(button)

        layout.addLayout(node_row)
        layout.addLayout(topic_row)
        layout.addWidget(self.node_log)
        layout.addWidget(self.topic_log)
        return page

    def _image_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        row = QHBoxLayout()
        row.addWidget(QLabel("Image topic"))
        row.addWidget(self.image_topic, 1)
        snapshot = QPushButton("Snapshot")
        snapshot.clicked.connect(self.image_snapshot)
        row.addWidget(snapshot)
        layout.addLayout(row)
        layout.addWidget(self.image_label)
        layout.addWidget(self.image_meta)
        return page

    def refresh_graph(self) -> None:
        self.topic_log.appendPlainText("refreshing ROS graph...")
        worker = ApiWorker(self.api.get, "/api/ros/graph", timeout=12.0)
        worker.signals.finished.connect(self._finish_graph)
        self.pool.start(worker)

    def _finish_graph(self, result: object, error: object) -> None:
        if error is not None:
            self.topic_log.appendPlainText(f"graph error: {error}")
            return
        graph = result if isinstance(result, dict) else {}
        nodes = [str(item.get("name", "")) for item in graph.get("nodes", []) if isinstance(item, dict)]
        topics = [item for item in graph.get("topics", []) if isinstance(item, dict)]
        self._topic_types = {str(item.get("name") or item.get("topic") or ""): str(item.get("type") or item.get("message_type") or "") for item in topics}
        self._fill_combo(self.node, nodes)
        topic_names = [str(item.get("name") or item.get("topic") or "") for item in topics]
        self._fill_combo(self.topic, topic_names)
        image_names = [name for name in topic_names if self._topic_types.get(name) == "sensor_msgs/msg/Image"]
        self._fill_combo(self.image_topic, image_names)
        self.topic_log.appendPlainText(f"graph refreshed: {len(topic_names)} topics, {len(nodes)} nodes")

    def _fill_combo(self, combo: QComboBox, items: list[str]) -> None:
        current = combo.currentText().strip()
        combo.blockSignals(True)
        combo.clear()
        combo.addItems([item for item in items if item])
        if current:
            index = combo.findText(current)
            if index >= 0:
                combo.setCurrentIndex(index)
            else:
                combo.setEditText(current)
        combo.blockSignals(False)

    def node_details(self) -> None:
        node = self.node.currentText().strip()
        if not node:
            self.node_log.appendPlainText("choose a node first")
            return
        self.node_log.appendPlainText(f"$ node-details {node}")
        worker = ApiWorker(self.api.post, "/api/ros/node-details", {"node": node}, timeout=14.0)
        worker.signals.finished.connect(lambda result, error: self._finish_text(self.node_log, result, error))
        self.pool.start(worker)

    def topic_action(self, path: str) -> None:
        topic = self.topic.currentText().strip()
        if not topic:
            self.topic_log.appendPlainText("choose a topic first")
            return
        self.topic_log.appendPlainText(f"$ {path.rsplit('/', 1)[-1]} {topic}")
        worker = ApiWorker(self.api.post, path, {"topic": topic}, timeout=14.0)
        worker.signals.finished.connect(lambda result, error: self._finish_text(self.topic_log, result, error))
        self.pool.start(worker)

    def image_snapshot(self) -> None:
        topic = self.image_topic.currentText().strip()
        if not topic:
            self.image_meta.setText("image: choose an image topic first")
            return
        self.image_meta.setText(f"image: waiting for {topic}")
        worker = ApiWorker(self.api.post, "/api/ros/image-snapshot", {"topic": topic}, timeout=8.0)
        worker.signals.finished.connect(self._finish_image_snapshot)
        self.pool.start(worker)

    def _finish_text(self, output: QPlainTextEdit, result: object, error: object) -> None:
        if error is not None:
            output.appendPlainText(f"error: {error}")
            return
        output.appendPlainText(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    def _finish_image_snapshot(self, result: object, error: object) -> None:
        if error is not None:
            self.image_meta.setText(f"image error: {error}")
            return
        data = result if isinstance(result, dict) else {}
        if not data.get("ok"):
            self.image_meta.setText(f"image error: {data.get('error', 'unknown')}")
            return
        raw = base64.b64decode(str(data.get("image_ppm_base64") or ""))
        pixmap = QPixmap()
        pixmap.loadFromData(raw, "PPM")
        self.image_label.setPixmap(pixmap.scaled(self.image_label.size(), Qt.KeepAspectRatio, Qt.FastTransformation))
        meta = data.get("meta", {})
        self.image_meta.setText(json.dumps(meta, ensure_ascii=False, default=str))

    def show_topic(self) -> None:
        self.tabs.setCurrentIndex(0)

    def show_image(self) -> None:
        self.tabs.setCurrentIndex(1)
