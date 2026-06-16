from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio_v3.frontend.pages.base import BasePage
from robodataset_studio_v3.frontend.worker import ApiWorker


class RosPage(BasePage):
    def __init__(self, api: ApiClient, project: ProjectSummary | None = None) -> None:
        super().__init__("ROS Discovery", api, project)
        self.pool = QThreadPool.globalInstance()
        self.graph_data: dict[str, Any] = {"nodes": [], "topics": [], "services": []}
        self.node_combo = QComboBox()
        self.node_combo.setEditable(True)
        self.topic_table = QTableWidget(0, 3)
        self.topic_table.setHorizontalHeaderLabels(["Use", "Topic", "Type"])
        self.topic_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.topic_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.topic_table.setWordWrap(False)
        self.topic_table.itemChanged.connect(self._selected_topics_changed)
        self.selection_status = QLabel("selected topics: 0")
        self._workers: list[ApiWorker] = []
        self._build_page()

    def _build_page(self) -> None:
        controls = QHBoxLayout()
        refresh = QPushButton("Refresh ROS Graph")
        refresh.clicked.connect(self.graph)
        save = QPushButton("Apply Selected Topics To Config")
        save.clicked.connect(self.apply_selection_to_config)
        node_info = QPushButton("Node Details")
        node_info.clicked.connect(self.node_details)
        controls.addWidget(refresh)
        controls.addWidget(save)
        controls.addStretch(1)

        node_row = QHBoxLayout()
        node_row.addWidget(QLabel("Selected node"))
        node_row.addWidget(self.node_combo, 1)
        node_row.addWidget(node_info)

        topics_box = QGroupBox("Discovered topics")
        topics_layout = QVBoxLayout(topics_box)
        topics_layout.addWidget(self.topic_table)
        topics_layout.addWidget(self.selection_status)

        self.layout.addLayout(controls)
        self.layout.addLayout(node_row)
        self.layout.addWidget(topics_box)
        self.finish_layout()

    def graph(self) -> None:
        self.status.setText("Refreshing ROS graph...")
        self._start_worker(self.api.get, self._finish_graph, "/api/ros/graph", timeout=12.0)

    def _finish_graph(self, result: object, error: object) -> None:
        if error is not None:
            self.show_error(error if isinstance(error, Exception) else Exception(str(error)))
            return
        graph = result if isinstance(result, dict) else {}
        self.graph_data = graph
        self._populate_graph(graph)
        topic_count = len(graph.get("topics", [])) if isinstance(graph.get("topics"), list) else 0
        node_count = len(graph.get("nodes", [])) if isinstance(graph.get("nodes"), list) else 0
        self.show_result(graph, f"ROS graph refreshed: {topic_count} topics, {node_count} nodes")

    def _populate_graph(self, graph: dict[str, Any]) -> None:
        nodes = [str(node.get("name", "")) for node in graph.get("nodes", []) if isinstance(node, dict)]
        topics = [topic for topic in graph.get("topics", []) if isinstance(topic, dict)]
        self.node_combo.blockSignals(True)
        current_node = self.node_combo.currentText().strip()
        self.node_combo.clear()
        self.node_combo.addItems(nodes)
        if current_node:
            index = self.node_combo.findText(current_node)
            if index >= 0:
                self.node_combo.setCurrentIndex(index)
            else:
                self.node_combo.setEditText(current_node)
        self.node_combo.blockSignals(False)

        selected = self._configured_selected_topic_names()
        self.topic_table.blockSignals(True)
        self.topic_table.setRowCount(len(topics))
        for row, topic in enumerate(topics):
            name = str(topic.get("name") or topic.get("topic") or "")
            typ = str(topic.get("type") or topic.get("message_type") or "")
            use = QTableWidgetItem("")
            use.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            use.setCheckState(Qt.Checked if name in selected else Qt.Unchecked)
            self.topic_table.setItem(row, 0, use)
            self.topic_table.setItem(row, 1, self._readonly_item(name))
            self.topic_table.setItem(row, 2, self._readonly_item(typ))
        self.topic_table.resizeColumnsToContents()
        self.topic_table.blockSignals(False)
        self._selected_topics_changed()

    def _configured_selected_topic_names(self) -> set[str]:
        if self.project is None:
            return set()
        try:
            config = self.api.get_dataset_config(self.project.key)
        except Exception:
            return set()
        ros = config.get("ros", {}) if isinstance(config, dict) else {}
        selected = ros.get("selected_topics", []) if isinstance(ros, dict) else []
        names = set()
        if isinstance(selected, list):
            for topic in selected:
                if isinstance(topic, dict):
                    names.add(str(topic.get("name") or topic.get("topic") or ""))
        return names

    def _selected_topics_changed(self) -> None:
        self.selection_status.setText(f"selected topics: {len(self.selected_topics())}")

    def selected_topics(self) -> list[dict[str, str]]:
        topics = []
        for row in range(self.topic_table.rowCount()):
            use = self.topic_table.item(row, 0)
            if use is None or use.checkState() != Qt.Checked:
                continue
            name = self.topic_table.item(row, 1).text() if self.topic_table.item(row, 1) else ""
            typ = self.topic_table.item(row, 2).text() if self.topic_table.item(row, 2) else ""
            if name:
                topics.append({"name": name, "topic": name, "type": typ, "message_type": typ})
        return topics

    def apply_selection_to_config(self) -> None:
        if self.project is None:
            QMessageBox.information(self, "ROS Discovery", "Open or create a project first.")
            return
        selected = self.selected_topics()
        try:
            project_config = self.api.get_project_config(self.project.key)
            dataset = self.api.get_dataset_config(self.project.key)
            dataset = self._merge_ros_selection(dataset, selected)
            project_config["dataset_config"] = dataset
            self.api.put(f"/api/config/project/{self.project.key}", project_config)
        except Exception as exc:
            self.show_error(exc)
            return
        self.show_result(dataset, f"Applied {len(selected)} selected topic(s) to dataset_config.yaml")

    def _merge_ros_selection(self, config: dict[str, Any], selected: list[dict[str, str]]) -> dict[str, Any]:
        config = dict(config or {})
        graph_topics = self.graph_data.get("topics", []) if isinstance(self.graph_data, dict) else []
        node = self.node_combo.currentText().strip()
        config.setdefault("ros", {})
        config["ros"]["selected_nodes"] = [node] if node else []
        config["ros"]["selected_topics"] = selected
        config["ros"]["discovery_snapshot"] = graph_topics if isinstance(graph_topics, list) else []

        streams = []
        state_keys = []
        action_source_topic = ""
        for topic in selected:
            name = topic.get("name", "")
            msg_type = topic.get("type", "")
            if msg_type == "sensor_msgs/msg/Image":
                stream_name = self._stream_name_from_topic(name)
                streams.append(
                    {
                        "name": stream_name,
                        "modality": "rgb" if "depth" not in name.lower() else "depth",
                        "source": "ros2_topic",
                        "topic": name,
                        "message_type": msg_type,
                        "dtype": "uint8",
                        "shape": [],
                        "encoding": "",
                        "training_role": "observation",
                        "calvin_key": stream_name,
                        "required": True,
                        "preview": {
                            "renderer": "image_rgb",
                            "crop": {"enabled": False, "x": 0, "y": 0, "width": 0, "height": 0},
                            "resize": {"enabled": False, "width": 0, "height": 0},
                        },
                    }
                )
            elif msg_type == "sensor_msgs/msg/JointState":
                action_source_topic = name
                state_keys.append(
                    {
                        "name": "robot_obs",
                        "source_topic": name,
                        "type": msg_type,
                        "output_dim": 0,
                        "fields": ["joint_position"],
                        "joint_order": [],
                    }
                )
        config["streams"] = streams
        config.setdefault("state", {})
        config["state"]["keys"] = state_keys
        config.setdefault("robot", {})
        if action_source_topic:
            config["robot"]["joint_state_topic"] = action_source_topic
        config.setdefault("action", {})
        config["action"]["source_topic"] = action_source_topic
        config["action"]["source"] = "derived_from_robot_obs" if action_source_topic else ""
        return config

    def node_details(self) -> None:
        node = self.node_combo.currentText().strip()
        if not node:
            QMessageBox.information(self, "Node Details", "Choose or type a node name first.")
            return
        self.status.setText("Loading node details...")
        self._start_worker(
            self.api.post,
            lambda result, error: self._finish_probe(result, error, "Node details loaded"),
            "/api/ros/node-details",
            {"node": node},
            timeout=14.0,
        )

    def _finish_probe(self, result: object, error: object, status: str) -> None:
        if error is not None:
            self.show_error(error if isinstance(error, Exception) else Exception(str(error)))
            return
        self.show_result(result, status)

    def _start_worker(self, fn, callback, *args, **kwargs) -> None:
        worker = ApiWorker(fn, *args, **kwargs)
        self._workers.append(worker)

        def finish(result: object, error: object, item: ApiWorker = worker) -> None:
            try:
                callback(result, error)
            finally:
                if item in self._workers:
                    self._workers.remove(item)

        worker.signals.finished.connect(finish, Qt.QueuedConnection)
        self.pool.start(worker)

    def _readonly_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        return item

    def _stream_name_from_topic(self, topic: str) -> str:
        clean = topic.strip("/").replace("/", "_").replace("-", "_") or "rgb"
        lower = clean.lower()
        if "wrist" in lower:
            return "rgb_wrist"
        if "static" in lower or "/camera/" in topic:
            return "rgb_static"
        if "depth" in lower:
            return f"depth_{clean[-24:]}"
        return f"rgb_{clean[-32:]}"
