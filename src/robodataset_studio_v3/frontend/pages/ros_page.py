from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio_v3.frontend.pages.base import BasePage
from robodataset_studio_v3.frontend.worker import ApiWorker
from robodataset_studio_v3.frontend.widgets.topic_tree import TopicTreeWidget
from robodataset_studio_v3.ros.image_conversion import is_image_message_type
from robodataset_studio_v3.ros.message_conversion import message_type_to_stream_defaults, unsupported_message_type_warning


class RosPage(BasePage):
    def __init__(self, api: ApiClient, project: ProjectSummary | None = None) -> None:
        super().__init__("ROS Discovery", api, project)
        self.pool = QThreadPool.globalInstance()
        self.graph_data: dict[str, Any] = {"nodes": [], "topics": [], "services": []}
        self.node_combo = QComboBox()
        self.node_combo.setEditable(True)
        self.topic_tree = TopicTreeWidget()
        self.topic_tree.selectionChanged.connect(self._selected_topics_changed)
        self.selection_status = QLabel("selected topics: 0")
        self._workers: list[ApiWorker] = []
        self._build_page()

    def _build_page(self) -> None:
        controls = QHBoxLayout()
        save = QPushButton("Apply Selected Topics To Config")
        save.clicked.connect(self.apply_selection_to_config)
        node_info = QPushButton("Node Details")
        node_info.clicked.connect(self.node_details)
        controls.addWidget(QLabel("Use the top toolbar Refresh Nodes/Topics button to update the global ROS graph."))
        controls.addWidget(save)
        controls.addStretch(1)

        node_row = QHBoxLayout()
        node_row.addWidget(QLabel("Selected node"))
        node_row.addWidget(self.node_combo, 1)
        node_row.addWidget(node_info)

        topics_box = QGroupBox("Discovered topics")
        topics_layout = QVBoxLayout(topics_box)
        topics_layout.addWidget(QLabel("Topics are grouped by their top-level ROS namespace. Expand a group to choose individual topics."))
        topics_layout.addWidget(self.topic_tree)
        topics_layout.addWidget(self.selection_status)

        self.layout.addLayout(controls)
        self.layout.addLayout(node_row)
        self.layout.addWidget(topics_box)
        self.finish_layout()

    def graph(self) -> None:
        self.status.setText("Refreshing ROS graph...")
        self._start_worker(self.api.get, self._finish_graph, "/api/ros/graph", timeout=30.0)

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

    def set_graph_data(self, graph: dict[str, Any]) -> None:
        self.graph_data = graph if isinstance(graph, dict) else {"nodes": [], "topics": [], "services": []}
        self._populate_graph(self.graph_data)
        topic_count = len(self.graph_data.get("topics", [])) if isinstance(self.graph_data.get("topics"), list) else 0
        node_count = len(self.graph_data.get("nodes", [])) if isinstance(self.graph_data.get("nodes"), list) else 0
        self.status.setText(f"Using global ROS graph: {topic_count} topics, {node_count} nodes")

    def _populate_graph(self, graph: dict[str, Any]) -> None:
        nodes = [str(node.get("name", "")) for node in graph.get("nodes", []) if isinstance(node, dict)]
        graph_topics = [topic for topic in graph.get("topics", []) if isinstance(topic, dict)]
        configured_topics = self._configured_selected_topic_rows()
        topics = self._merge_topic_rows(graph_topics, configured_topics)
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
        self.topic_tree.populate(topics, selected)
        self._selected_topics_changed()
        if not topics:
            error_text = self._graph_error_summary(graph)
            self.status.setText(error_text or "No ROS topics found. Check ROS setup and running nodes, then Refresh Nodes/Topics.")

    def _configured_selected_topic_names(self) -> set[str]:
        return {str(topic.get("name") or topic.get("topic") or "") for topic in self._configured_selected_topic_rows()}

    def _configured_selected_topic_rows(self) -> list[dict[str, Any]]:
        if self.project is None:
            return []
        try:
            config = self.api.get_project_config(self.project.key)
        except Exception:
            return []
        ros = config.get("ros", {}) if isinstance(config, dict) else {}
        selected = ros.get("selected_topics", []) if isinstance(ros, dict) else []
        if isinstance(selected, list):
            return [dict(topic) for topic in selected if isinstance(topic, dict)]
        return []

    def _merge_topic_rows(self, graph_topics: list[dict[str, Any]], configured_topics: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for row in [*graph_topics, *configured_topics]:
            name = str(row.get("topic") or row.get("name") or "")
            if not name:
                continue
            msg_type = str(row.get("type") or row.get("message_type") or "")
            merged[name] = {"name": name, "topic": name, "type": msg_type, "message_type": msg_type}
        return [merged[name] for name in sorted(merged)]

    def _selected_topics_changed(self) -> None:
        self.selection_status.setText(f"selected topics: {len(self.selected_topics())}")

    def selected_topics(self) -> list[dict[str, str]]:
        return self.topic_tree.selected_topics()

    def _graph_error_summary(self, graph: dict[str, Any]) -> str:
        errors = graph.get("errors", {}) if isinstance(graph, dict) else {}
        if not isinstance(errors, dict):
            return ""
        parts = []
        for key in ["topics", "nodes", "services"]:
            text = str(errors.get(key) or "").strip()
            if text:
                line = text.splitlines()[0]
                parts.append(f"{key}: {line}")
        return "ROS graph returned no topics. " + " | ".join(parts) if parts else ""

    def apply_selection_to_config(self) -> None:
        if self.project is None:
            QMessageBox.information(self, "ROS Discovery", "Open or create a project first.")
            return
        selected = self.selected_topics()
        try:
            project_config = self.api.get_project_config(self.project.key)
            dataset = project_config.get("dataset_config", {}) if isinstance(project_config.get("dataset_config"), dict) else {}
            dataset = self._merge_dataset_streams(dataset, selected)
            project_config["dataset_config"] = dataset
            project_config["ros"] = self._selected_ros_config(selected)
            self.api.put(f"/api/config/project/{self.project.key}", project_config)
        except Exception as exc:
            self.show_error(exc)
            return
        self.show_result(project_config, f"Applied {len(selected)} selected topic(s) to project total config")

    def _selected_ros_config(self, selected: list[dict[str, str]]) -> dict[str, Any]:
        graph_topics = self.graph_data.get("topics", []) if isinstance(self.graph_data, dict) else []
        node = self.node_combo.currentText().strip()
        return {
            "selected_nodes": [node] if node else [],
            "selected_topics": selected,
            "discovery_snapshot": graph_topics if isinstance(graph_topics, list) else [],
        }

    def _merge_dataset_streams(self, config: dict[str, Any], selected: list[dict[str, str]]) -> dict[str, Any]:
        config = dict(config or {})
        config.pop("ros", None)

        streams = []
        state_keys = []
        action_source_topic = ""
        warnings = []
        for topic in selected:
            name = topic.get("name", "")
            msg_type = topic.get("type", "")
            if is_image_message_type(msg_type):
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
            else:
                defaults = message_type_to_stream_defaults(msg_type, name)
                if defaults is None:
                    warnings.append(unsupported_message_type_warning(name, msg_type))
                    continue
                stream_name = self._stream_name_from_topic(name)
                streams.append(
                    {
                        "name": stream_name,
                        "source": "ros2_topic",
                        "topic": name,
                        "message_type": msg_type,
                        **defaults,
                    }
                )
        config["streams"] = streams
        config.setdefault("warnings", {})
        config["warnings"]["unsupported_topics"] = warnings
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
