from __future__ import annotations

import json
import re
from typing import Any

import yaml
from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio_v3.frontend.worker import ApiWorker
from robodataset_studio_v3.frontend.widgets.topic_tree import TopicTreeWidget


class ConfigLibraryPage(QWidget):
    def __init__(self, api: ApiClient, project: ProjectSummary | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.api = api
        self.project = project
        self.pool = QThreadPool.globalInstance()
        self._workers: list[ApiWorker] = []
        self.configs: list[dict[str, Any]] = []
        self.graph_data: dict[str, Any] = {"topics": [], "nodes": [], "services": []}
        self._updating = False

        self.config_name = QLineEdit()
        self.config_select = QComboBox()
        self.config_select.currentIndexChanged.connect(self.load_selected)
        self.status = QLabel("")
        self.editor = QPlainTextEdit()
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.ai_prompt = QPlainTextEdit()
        self.ai_preview = QPlainTextEdit()

        self.env_type = self.editable_combo(["tabletop", "bin_picking", "mobile_base", "lab_bench", "simulation", "custom"])
        self.env_desc = QPlainTextEdit()
        self.env_desc.setMaximumHeight(70)
        self.env_workspace = QLineEdit()
        self.env_lighting = self.editable_combo(["normal indoor", "bright indoor", "low light", "overhead lab light", "natural light", "custom"])
        self.env_objects = QLineEdit()
        self.env_notes = QPlainTextEdit()
        self.env_notes.setMaximumHeight(70)
        self.robot_name = self.editable_combo(["wx250s", "widowx", "aloha", "ur5", "franka", "custom"])
        self.robot_model = self.editable_combo(["wx250s", "widowx", "vx300s", "ur5e", "panda", "custom"])
        self.robot_description = QLineEdit()
        self.robot_joint_count = QSpinBox()
        self.robot_joint_count.setRange(0, 512)
        self.robot_joint_order = QLineEdit()
        self.robot_base_frame = QLineEdit()
        self.robot_ee_frame = QLineEdit()
        self.instruction_text = QLineEdit()
        self.instruction_language = self.editable_combo(["en", "zh", "en+zh", "custom"])
        self.task_family = self.editable_combo(["pick_and_place", "grasp", "push", "insert", "open_close", "sorting", "custom"])
        self.success_condition = self.editable_combo(
            [
                "object is placed at the target location",
                "target object is grasped stably",
                "task reaches the requested final state",
                "operator marks the episode successful",
                "custom",
            ]
        )
        self.sample_rate = QSpinBox()
        self.sample_rate.setRange(1, 240)
        self.sample_rate.setValue(10)
        self.sample_rate.setSuffix(" Hz")
        self.stop_mode = QComboBox()
        self.stop_mode.addItem("Manual", "manual")
        self.stop_mode.addItem("Duration", "duration_sec")
        self.stop_mode.addItem("Sample count", "sample_count")
        self.episode_duration = QDoubleSpinBox()
        self.episode_duration.setRange(0.0, 3600.0)
        self.episode_duration.setDecimals(2)
        self.episode_duration.setSingleStep(0.1)
        self.target_samples = QSpinBox()
        self.target_samples.setRange(0, 1_000_000)
        self.crop_enabled = QCheckBox("Enable crop")
        self.crop_x = QSpinBox()
        self.crop_y = QSpinBox()
        self.crop_w = QSpinBox()
        self.crop_h = QSpinBox()
        self.resize_enabled = QCheckBox("Enable resize")
        self.resize_w = QSpinBox()
        self.resize_h = QSpinBox()
        for spin in [self.crop_x, self.crop_y, self.crop_w, self.crop_h, self.resize_w, self.resize_h]:
            spin.setRange(0, 8192)

        self.upload_enabled = QCheckBox("Enable upload profile")
        self.upload_profile = self.editable_combo(["local_lab_server", "internal_gpu_server", "remote_backup", "custom"])
        self.upload_lan_host = QLineEdit()
        self.upload_wan_host = QLineEdit()
        self.upload_port = QSpinBox()
        self.upload_port.setRange(1, 65535)
        self.upload_port.setValue(22)
        self.upload_username = QLineEdit()
        self.upload_key_path = QLineEdit()
        self.upload_remote_root = QLineEdit()
        self.upload_rsync = QCheckBox("Use rsync")
        self.upload_repair = QCheckBox("Repair / resume verified upload")
        self.upload_verify = QCheckBox("Verify after upload")

        self.topic_tree = TopicTreeWidget()
        self.topic_tree.selectionChanged.connect(self.update_selected_topics_preview)
        self.selected_topics = QPlainTextEdit()
        self.selected_topics.setReadOnly(True)
        self.selected_topics.setMaximumHeight(90)

        self._build()
        self.refresh_list()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        refresh = QPushButton("Refresh")
        load = QPushButton("Load")
        save = QPushButton("Save")
        duplicate = QPushButton("Duplicate")
        rename = QPushButton("Rename")
        delete = QPushButton("Delete")
        apply_project = QPushButton("Load into current project")
        refresh.clicked.connect(self.refresh_list)
        load.clicked.connect(self.load_selected)
        save.clicked.connect(self.save_selected)
        duplicate.clicked.connect(self.duplicate_selected)
        rename.clicked.connect(self.rename_selected)
        delete.clicked.connect(self.delete_selected)
        apply_project.clicked.connect(self.apply_to_project)
        top.addWidget(QLabel("Config name"))
        top.addWidget(self.config_name, 2)
        top.addWidget(QLabel("Existing"))
        top.addWidget(self.config_select, 2)
        top.addWidget(refresh)
        top.addWidget(load)
        top.addWidget(save)
        top.addWidget(duplicate)
        top.addWidget(rename)
        top.addWidget(delete)
        top.addWidget(apply_project)

        actions = QHBoxLayout()
        refresh_from_topics = QPushButton("Refresh config from selected topics")
        apply_form = QPushButton("Apply form -> YAML")
        reload_form = QPushButton("Reload form <- YAML")
        validate = QPushButton("Validate")
        refresh_from_topics.clicked.connect(self.refresh_config_from_topics)
        apply_form.clicked.connect(self.apply_form_to_yaml)
        reload_form.clicked.connect(self.reload_form_from_yaml)
        validate.clicked.connect(self.validate)
        actions.addWidget(refresh_from_topics)
        actions.addWidget(reload_form)
        actions.addWidget(apply_form)
        actions.addWidget(validate)
        actions.addStretch(1)

        form_tabs = QTabWidget()
        form_tabs.addTab(self._environment_form(), "Environment")
        form_tabs.addTab(self._robot_form(), "Robot")
        form_tabs.addTab(self._instruction_form(), "Instruction")
        form_tabs.addTab(self._recording_form(), "Recording / Image")
        form_tabs.addTab(self._topic_form(), "ROS Topics")
        form_tabs.addTab(self._upload_form(), "Upload")
        form_tabs.addTab(self._ai_form(), "AI Match Config")

        yaml_tabs = QTabWidget()
        yaml_tabs.addTab(self.editor, "total_config.yaml")
        yaml_tabs.addTab(self.preview, "Dataset preview")
        yaml_tabs.addTab(self.ai_preview, "AI config preview")

        splitter = QSplitter(Qt.Vertical)
        upper = QWidget()
        upper_layout = QVBoxLayout(upper)
        upper_layout.addLayout(actions)
        upper_layout.addWidget(form_tabs)
        lower = QWidget()
        lower_layout = QVBoxLayout(lower)
        lower_layout.addWidget(yaml_tabs)
        splitter.addWidget(upper)
        splitter.addWidget(lower)
        splitter.setSizes([520, 420])

        layout.addLayout(top)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.status)

    def editable_combo(self, values: list[str]) -> QComboBox:
        combo = QComboBox()
        combo.setEditable(True)
        combo.addItems(values)
        combo.setCurrentText("")
        combo.setInsertPolicy(QComboBox.NoInsert)
        return combo

    def add_combo_choices(self, combo: QComboBox, values: list[str]) -> None:
        current = combo.currentText()
        known = {combo.itemText(index) for index in range(combo.count())}
        for value in values:
            clean = value.strip()
            if clean and clean not in known:
                combo.addItem(clean)
                known.add(clean)
        combo.setCurrentText(current)

    def _environment_form(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)
        form.addRow("Environment type", self.env_type)
        form.addRow("Description", self.env_desc)
        form.addRow("Workspace", self.env_workspace)
        form.addRow("Lighting", self.env_lighting)
        form.addRow("Objects CSV", self.env_objects)
        form.addRow("Notes", self.env_notes)
        return widget

    def _robot_form(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)
        form.addRow("Robot name", self.robot_name)
        form.addRow("Model", self.robot_model)
        form.addRow("Description", self.robot_description)
        form.addRow("Joint count", self.robot_joint_count)
        form.addRow("Joint order CSV", self.robot_joint_order)
        form.addRow("Base frame", self.robot_base_frame)
        form.addRow("End effector frame", self.robot_ee_frame)
        return widget

    def _instruction_form(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)
        form.addRow("Instruction / prompt", self.instruction_text)
        form.addRow("Language", self.instruction_language)
        form.addRow("Task family", self.task_family)
        form.addRow("Success condition", self.success_condition)
        return widget

    def _recording_form(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)
        form.addRow("Sample rate", self.sample_rate)
        form.addRow("Stop mode", self.stop_mode)
        form.addRow("Episode duration sec", self.episode_duration)
        form.addRow("Target samples", self.target_samples)
        crop = QGridLayout()
        crop.addWidget(self.crop_enabled, 0, 0)
        for col, (label, spin) in enumerate([("x", self.crop_x), ("y", self.crop_y), ("w", self.crop_w), ("h", self.crop_h)], start=1):
            crop.addWidget(QLabel(label), 0, col * 2 - 1)
            crop.addWidget(spin, 0, col * 2)
        form.addRow("Crop", crop)
        resize = QHBoxLayout()
        resize.addWidget(self.resize_enabled)
        resize.addWidget(QLabel("w"))
        resize.addWidget(self.resize_w)
        resize.addWidget(QLabel("h"))
        resize.addWidget(self.resize_h)
        form.addRow("Resize", resize)
        return widget

    def _topic_form(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel("Select ROS topics by group, then click Refresh config from selected topics."))
        layout.addWidget(self.topic_tree)
        layout.addWidget(QLabel("Selected topics"))
        layout.addWidget(self.selected_topics)
        return widget

    def _upload_form(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)
        form.addRow(self.upload_enabled)
        form.addRow("Profile name", self.upload_profile)
        form.addRow("Internal IP / Host", self.upload_lan_host)
        form.addRow("Public IP / Host", self.upload_wan_host)
        form.addRow("Port", self.upload_port)
        form.addRow("Username", self.upload_username)
        form.addRow("Private key path", self.upload_key_path)
        form.addRow("Remote root", self.upload_remote_root)
        form.addRow(self.upload_rsync)
        form.addRow(self.upload_repair)
        form.addRow(self.upload_verify)
        return widget

    def _ai_form(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        buttons = QHBoxLayout()
        default_prompt = QPushButton("Default prompt")
        send = QPushButton("Send")
        replace = QPushButton("Replace dataset_config from AI preview")
        default_prompt.clicked.connect(self.build_default_ai_prompt)
        send.clicked.connect(self.send_ai_prompt)
        replace.clicked.connect(self.replace_yaml_from_ai_preview)
        buttons.addWidget(default_prompt)
        buttons.addWidget(send)
        buttons.addWidget(replace)
        buttons.addStretch(1)
        prompt_box = QGroupBox("AI prompt")
        prompt_layout = QVBoxLayout(prompt_box)
        prompt_layout.addWidget(self.ai_prompt)
        layout.addWidget(QLabel("AI base URL, API key, model, and timeout are configured in Settings."))
        layout.addLayout(buttons)
        layout.addWidget(prompt_box, 1)
        return widget

    def refresh_list(self) -> None:
        current = self.selected_config_id() or self.config_name.text().strip()
        try:
            self.configs = self.api.list_configs()
        except Exception as exc:
            self.status.setText(f"Cannot list configs: {exc}")
            return
        self.config_select.blockSignals(True)
        self.config_select.clear()
        for config in self.configs:
            config_id = str(config.get("id") or "")
            name = str(config.get("name") or config_id)
            streams = config.get("stream_count", "")
            self.config_select.addItem(f"{name} [{config_id}] - {streams} streams", config_id)
        if current:
            idx = self.config_select.findData(current)
            if idx >= 0:
                self.config_select.setCurrentIndex(idx)
        self.config_select.blockSignals(False)
        if not self.editor.toPlainText().strip() and self.config_select.count():
            self.load_selected()

    def start_new_config(self) -> None:
        self.config_name.setText("")
        config = self.default_total_config()
        self.set_config(config)
        self.config_name.setFocus()
        self.status.setText("Enter a new config name, edit fields, then click Save.")

    def selected_config_id(self) -> str:
        return str(self.config_select.currentData() or "")

    def load_selected(self) -> None:
        config_id = self.selected_config_id()
        if not config_id:
            return
        try:
            config = self.api.get_config(config_id)
        except Exception as exc:
            self.status.setText(f"Cannot load config: {exc}")
            return
        self.config_name.setText(config_id)
        self.set_config(config)
        self.status.setText(f"Loaded config: {config_id}")

    def save_selected(self) -> None:
        name = self.config_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Save Config", "Enter a config name first.")
            return
        try:
            config = self.current_config()
            self.apply_form_values(config)
            config = self.ordered_total_config(config, name)
            saved = self.api.save_config(name, config)
        except Exception as exc:
            QMessageBox.warning(self, "Save Config", f"Cannot save config:\n{exc}")
            return
        self.status.setText(f"Saved config: {saved.get('id', name)}")
        self.refresh_list()

    def duplicate_selected(self) -> None:
        config_id = self.selected_config_id()
        if not config_id:
            QMessageBox.information(self, "Duplicate Config", "Select an existing config first.")
            return
        name = self.config_name.text().strip()
        try:
            saved = self.api.duplicate_config(config_id, name)
        except Exception as exc:
            QMessageBox.warning(self, "Duplicate Config", f"Cannot duplicate config:\n{exc}")
            return
        new_id = str(saved.get("id") or "")
        self.config_name.setText(new_id)
        self.status.setText(f"Duplicated config: {new_id or saved}")
        self.refresh_list()
        if new_id:
            idx = self.config_select.findData(new_id)
            if idx >= 0:
                self.config_select.setCurrentIndex(idx)
                self.load_selected()

    def rename_selected(self) -> None:
        config_id = self.selected_config_id()
        name = self.config_name.text().strip()
        if not config_id:
            QMessageBox.information(self, "Rename Config", "Select an existing config first.")
            return
        if not name:
            QMessageBox.warning(self, "Rename Config", "Enter the new config name in Config name first.")
            return
        try:
            saved = self.api.rename_config(config_id, name)
        except Exception as exc:
            QMessageBox.warning(self, "Rename Config", f"Cannot rename config:\n{exc}")
            return
        new_id = str(saved.get("id") or name)
        self.config_name.setText(new_id)
        self.status.setText(f"Renamed config: {config_id} -> {new_id}")
        self.refresh_list()
        idx = self.config_select.findData(new_id)
        if idx >= 0:
            self.config_select.setCurrentIndex(idx)
            self.load_selected()

    def delete_selected(self) -> None:
        config_id = self.selected_config_id()
        if not config_id:
            QMessageBox.information(self, "Delete Config", "Select an existing config first.")
            return
        answer = QMessageBox.question(
            self,
            "Delete Config",
            f"Delete config '{config_id}' from the library?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self.api.delete_config(config_id)
        except Exception as exc:
            QMessageBox.warning(self, "Delete Config", f"Cannot delete config:\n{exc}")
            return
        self.config_name.clear()
        self.editor.clear()
        self.preview.clear()
        self.status.setText(f"Deleted config: {config_id}")
        self.refresh_list()

    def apply_to_project(self) -> None:
        if self.project is None:
            QMessageBox.information(self, "Load Config", "Open or create a project first.")
            return
        if self.project.has_recorded_data:
            QMessageBox.warning(self, "Load Config", "This project already has recorded data. Create a new project version before loading another config.")
            return
        config_id = self.config_name.text().strip() or self.selected_config_id()
        if not config_id:
            return
        try:
            self.project = self.api.bind_project_config(self.project.key, config_id)
        except Exception as exc:
            QMessageBox.warning(self, "Load Config", f"Cannot load config into project:\n{exc}")
            return
        self.status.setText(f"Project {self.project.key} now uses config: {config_id}")

    def set_graph_data(self, graph: dict[str, Any]) -> None:
        self.graph_data = graph if isinstance(graph, dict) else {"topics": [], "nodes": [], "services": []}
        self.populate_topics()
        topics = self.graph_data.get("topics", []) if isinstance(self.graph_data, dict) else []
        if isinstance(topics, list) and topics:
            self.status.setText(f"ROS graph loaded into config page: {len(topics)} topics.")
        else:
            self.status.setText(self._graph_error_summary(self.graph_data) or "ROS graph loaded but no topics were found.")

    def refresh_ros_graph(self) -> None:
        self.status.setText("Refreshing ROS graph...")
        self.run_async(self.api.get, self.finish_ros_graph, "/api/ros/graph", timeout=12.0)

    def finish_ros_graph(self, result: object, error: object) -> None:
        if error is not None:
            self.status.setText(f"ROS graph failed: {error}")
            return
        self.set_graph_data(result if isinstance(result, dict) else {})

    def populate_topics(self) -> None:
        topics = [item for item in self.graph_data.get("topics", []) if isinstance(item, dict)]
        self.update_ros_based_choices(topics)
        selected = {item.get("topic") or item.get("name") for item in self.selected_topic_rows()}
        selected.update(self.configured_selected_topic_names())
        self.topic_tree.populate(topics, selected)
        self.update_selected_topics_preview()

    def update_ros_based_choices(self, topics: list[dict[str, Any]]) -> None:
        robot_names: list[str] = []
        for topic in topics:
            name = str(topic.get("name") or topic.get("topic") or "")
            msg_type = str(topic.get("type") or topic.get("message_type") or "")
            parts = [part for part in name.split("/") if part]
            if msg_type == "sensor_msgs/msg/JointState" and parts:
                robot_names.append(parts[0])
        self.add_combo_choices(self.robot_name, robot_names)
        self.add_combo_choices(self.robot_model, robot_names)

    def selected_topic_rows(self) -> list[dict[str, str]]:
        selected = self.topic_tree.selected_topics()
        if selected:
            return selected
        try:
            config = self.current_config(default=False)
        except Exception:
            return []
        dataset = config.get("dataset_config", {}) if isinstance(config.get("dataset_config"), dict) else {}
        ros = dataset.get("ros", {}) if isinstance(dataset.get("ros"), dict) else {}
        rows = ros.get("selected_topics", []) if isinstance(ros.get("selected_topics"), list) else []
        return [dict(row) for row in rows if isinstance(row, dict)]

    def configured_selected_topic_names(self) -> set[str]:
        try:
            config = self.current_config(default=False)
        except Exception:
            return set()
        dataset = config.get("dataset_config", {}) if isinstance(config.get("dataset_config"), dict) else {}
        ros = dataset.get("ros", {}) if isinstance(dataset.get("ros"), dict) else {}
        rows = ros.get("selected_topics", []) if isinstance(ros.get("selected_topics"), list) else []
        return {str(row.get("topic") or row.get("name") or "") for row in rows if isinstance(row, dict)}

    def _graph_error_summary(self, graph: dict[str, Any]) -> str:
        errors = graph.get("errors", {}) if isinstance(graph, dict) else {}
        if not isinstance(errors, dict):
            return ""
        parts = []
        for key in ["topics", "nodes", "services"]:
            text = str(errors.get(key) or "").strip()
            if text:
                parts.append(f"{key}: {text.splitlines()[0]}")
        return "ROS graph returned no topics. " + " | ".join(parts) if parts else ""

    def update_selected_topics_preview(self) -> None:
        rows = self.selected_topic_rows()
        self.selected_topics.setPlainText("\n".join(f"{row['topic']} [{row['type']}]" for row in rows) or "(none)")

    def refresh_config_from_topics(self) -> None:
        config = self.current_config(default=True)
        dataset = config.setdefault("dataset_config", {})
        selected = self.selected_topic_rows()
        dataset.setdefault("ros", {})
        dataset["ros"]["selected_topics"] = selected
        dataset["ros"]["discovery_snapshot"] = self.graph_data.get("topics", [])
        streams = []
        cameras = []
        state_keys = []
        joint_topic = ""
        for topic in selected:
            name = topic["topic"]
            msg_type = topic["type"]
            if msg_type == "sensor_msgs/msg/Image":
                stream_name = self.stream_name_from_topic(name, len(streams))
                crop, resize = self.image_preprocess()
                cameras.append({"name": stream_name, "role": self.camera_role(stream_name), "topic": name, "type": msg_type, "encoding": "", "fps_target": self.sample_rate.value(), "crop": crop, "resize": resize})
                streams.append({"name": stream_name, "modality": "rgb" if "depth" not in name.lower() else "depth", "source": "ros2_topic", "topic": name, "message_type": msg_type, "dtype": "uint8", "shape": [], "encoding": "", "training_role": "observation", "calvin_key": stream_name, "required": True, "preview": {"renderer": "image_rgb", "crop": crop, "resize": resize}})
            elif msg_type == "sensor_msgs/msg/JointState":
                joint_topic = name
                state_keys.append({"name": "robot_obs", "source_topic": name, "type": msg_type, "output_dim": int(self.robot_joint_count.value()), "fields": ["joint_position"], "joint_order": self.split_csv(self.robot_joint_order.text())})
        dataset["cameras"] = cameras
        dataset["streams"] = streams
        dataset.setdefault("state", {})["keys"] = state_keys
        dataset.setdefault("robot", {})["joint_state_topic"] = joint_topic
        dataset.setdefault("action", {})
        dataset["action"]["source_topic"] = joint_topic
        dataset["action"]["source"] = "derived_from_robot_obs" if joint_topic else ""
        dataset["action"]["dim"] = int(self.robot_joint_count.value()) if joint_topic else 0
        self.apply_form_values(config)
        self.set_config(config)
        self.status.setText(f"Config refreshed from {len(selected)} selected topic(s).")

    def current_config(self, default: bool = False) -> dict[str, Any]:
        text = self.editor.toPlainText().strip()
        if not text and default:
            return self.default_total_config()
        data = yaml.safe_load(text) if text else {}
        if not isinstance(data, dict):
            raise ValueError("YAML must be a mapping")
        return data

    def set_config(self, config: dict[str, Any]) -> None:
        config = self.ordered_total_config(config, self.config_name.text().strip())
        self._updating = True
        self.editor.setPlainText(yaml.safe_dump(config, sort_keys=False, allow_unicode=True))
        self.reload_form_from_yaml()
        self._updating = False
        self.refresh_preview(config)

    def reload_form_from_yaml(self) -> None:
        try:
            config = self.current_config(default=True)
        except Exception as exc:
            self.status.setText(f"Cannot reload form: {exc}")
            return
        dataset = config.get("dataset_config", {}) if isinstance(config.get("dataset_config"), dict) else {}
        env = dataset.get("environment", {}) if isinstance(dataset.get("environment"), dict) else {}
        robot = dataset.get("robot", {}) if isinstance(dataset.get("robot"), dict) else {}
        instr = dataset.get("instruction", {}) if isinstance(dataset.get("instruction"), dict) else {}
        rec = dataset.get("recording", {}) if isinstance(dataset.get("recording"), dict) else {}
        upload = config.get("upload", {}) if isinstance(config.get("upload"), dict) else {}
        self.env_type.setCurrentText(str(env.get("type", "")))
        self.env_desc.setPlainText(str(env.get("description") or env.get("scene_description") or ""))
        self.env_workspace.setText(str(env.get("workspace", "")))
        self.env_lighting.setCurrentText(str(env.get("lighting", "")))
        self.env_objects.setText(", ".join(str(x) for x in env.get("objects", [])) if isinstance(env.get("objects"), list) else str(env.get("objects", "")))
        self.env_notes.setPlainText(str(env.get("notes", "")))
        self.robot_name.setCurrentText(str(robot.get("name", "")))
        self.robot_model.setCurrentText(str(robot.get("model", "")))
        self.robot_description.setText(str(robot.get("description", "")))
        self.robot_joint_count.setValue(int(robot.get("joint_count") or 0))
        self.robot_joint_order.setText(", ".join(str(x) for x in robot.get("joint_order", [])) if isinstance(robot.get("joint_order"), list) else str(robot.get("joint_order", "")))
        self.robot_base_frame.setText(str(robot.get("base_frame", "")))
        self.robot_ee_frame.setText(str(robot.get("end_effector_frame", "")))
        self.instruction_text.setText(str(instr.get("text", "")))
        self.instruction_language.setCurrentText(str(instr.get("language", "")))
        self.task_family.setCurrentText(str(instr.get("task_family", "")))
        self.success_condition.setCurrentText(str(instr.get("success_condition", "")))
        self.sample_rate.setValue(int(rec.get("sample_rate_hz") or 10))
        idx = self.stop_mode.findData(str(rec.get("stop_mode") or "manual"))
        self.stop_mode.setCurrentIndex(idx if idx >= 0 else 0)
        self.episode_duration.setValue(float(rec.get("episode_duration_sec") or 0.0))
        self.target_samples.setValue(int(rec.get("target_samples") or 0))
        crop, resize = self.first_preprocess(dataset)
        self.crop_enabled.setChecked(bool(crop.get("enabled", False)))
        self.crop_x.setValue(int(crop.get("x", 0) or 0))
        self.crop_y.setValue(int(crop.get("y", 0) or 0))
        self.crop_w.setValue(int(crop.get("width", 0) or 0))
        self.crop_h.setValue(int(crop.get("height", 0) or 0))
        self.resize_enabled.setChecked(bool(resize.get("enabled", False)))
        self.resize_w.setValue(int(resize.get("width", 0) or 0))
        self.resize_h.setValue(int(resize.get("height", 0) or 0))
        self.upload_enabled.setChecked(bool(upload.get("enabled", False)))
        self.upload_profile.setCurrentText(str(upload.get("profile_name", "")))
        self.upload_lan_host.setText(str(upload.get("lan_host") or upload.get("host") or ""))
        self.upload_wan_host.setText(str(upload.get("wan_host", "")))
        self.upload_port.setValue(int(upload.get("port") or 22))
        self.upload_username.setText(str(upload.get("username", "")))
        self.upload_key_path.setText(str(upload.get("key_path", "")))
        self.upload_remote_root.setText(str(upload.get("remote_root", "")))
        self.upload_rsync.setChecked(bool(upload.get("use_rsync", True)))
        self.upload_repair.setChecked(bool(upload.get("repair_resume_enabled", True)))
        self.upload_verify.setChecked(bool(upload.get("verify_after_upload", True)))
        self.refresh_preview(config)

    def apply_form_to_yaml(self) -> None:
        try:
            config = self.current_config(default=True)
            self.apply_form_values(config)
            self.set_config(self.ordered_total_config(config, self.config_name.text().strip()))
            self.status.setText("Applied form values to YAML.")
        except Exception as exc:
            QMessageBox.warning(self, "Apply Form", str(exc))

    def apply_form_values(self, config: dict[str, Any]) -> None:
        dataset = config.setdefault("dataset_config", self.default_dataset_config())
        env = dataset.setdefault("environment", {})
        env["type"] = self.env_type.currentText().strip()
        env["description"] = self.env_desc.toPlainText().strip()
        env["workspace"] = self.env_workspace.text().strip()
        env["lighting"] = self.env_lighting.currentText().strip()
        env["objects"] = self.split_csv(self.env_objects.text())
        env["notes"] = self.env_notes.toPlainText().strip()
        robot = dataset.setdefault("robot", {})
        robot["name"] = self.robot_name.currentText().strip()
        robot["model"] = self.robot_model.currentText().strip()
        robot["description"] = self.robot_description.text().strip()
        robot["joint_count"] = int(self.robot_joint_count.value())
        robot["joint_order"] = self.split_csv(self.robot_joint_order.text())
        robot["base_frame"] = self.robot_base_frame.text().strip()
        robot["end_effector_frame"] = self.robot_ee_frame.text().strip()
        instr = dataset.setdefault("instruction", {})
        instr["text"] = self.instruction_text.text().strip()
        instr["language"] = self.instruction_language.currentText().strip()
        instr["task_family"] = self.task_family.currentText().strip()
        instr["success_condition"] = self.success_condition.currentText().strip()
        rec = dataset.setdefault("recording", {})
        rec["sample_rate_hz"] = int(self.sample_rate.value())
        rec["stop_mode"] = str(self.stop_mode.currentData() or "manual")
        rec["episode_duration_sec"] = float(self.episode_duration.value())
        rec["target_samples"] = int(self.target_samples.value())
        crop, resize = self.image_preprocess()
        for camera in dataset.get("cameras", []) if isinstance(dataset.get("cameras"), list) else []:
            if isinstance(camera, dict):
                camera["crop"] = dict(crop)
                camera["resize"] = dict(resize)
        for stream in dataset.get("streams", []) if isinstance(dataset.get("streams"), list) else []:
            if isinstance(stream, dict):
                stream.setdefault("preview", {})["crop"] = dict(crop)
                stream.setdefault("preview", {})["resize"] = dict(resize)
        config["upload"] = {
            "enabled": self.upload_enabled.isChecked(),
            "profile_name": self.upload_profile.currentText().strip(),
            "host": self.upload_lan_host.text().strip() or self.upload_wan_host.text().strip(),
            "lan_host": self.upload_lan_host.text().strip(),
            "wan_host": self.upload_wan_host.text().strip(),
            "port": int(self.upload_port.value()),
            "username": self.upload_username.text().strip(),
            "key_path": self.upload_key_path.text().strip(),
            "remote_root": self.upload_remote_root.text().strip(),
            "use_rsync": self.upload_rsync.isChecked(),
            "repair_resume_enabled": self.upload_repair.isChecked(),
            "verify_after_upload": self.upload_verify.isChecked(),
        }
        config.pop("project", None)

    def validate(self) -> None:
        try:
            config = self.current_config()
            dataset = config.get("dataset_config", {})
            warnings = []
            if not isinstance(dataset, dict):
                warnings.append("dataset_config is missing")
            elif not dataset.get("streams"):
                warnings.append("no streams configured")
            if not config.get("upload", {}).get("host") and config.get("upload", {}).get("enabled"):
                warnings.append("upload enabled but host is empty")
            self.status.setText("OK" if not warnings else "Warnings: " + "; ".join(warnings))
            self.refresh_preview(config)
        except Exception as exc:
            self.status.setText(f"Invalid YAML: {exc}")

    def refresh_preview(self, config: dict[str, Any]) -> None:
        dataset = config.get("dataset_config", {}) if isinstance(config.get("dataset_config"), dict) else {}
        lines = ["total_config.yaml", "dataset_config:"]
        streams = dataset.get("streams", []) if isinstance(dataset.get("streams"), list) else []
        state_keys = dataset.get("state", {}).get("keys", []) if isinstance(dataset.get("state"), dict) else []
        action = dataset.get("action", {}) if isinstance(dataset.get("action"), dict) else {}
        lines.append(f"  streams: {len(streams)}")
        for stream in streams:
            if isinstance(stream, dict):
                lines.append(f"    {stream.get('calvin_key') or stream.get('name')}: {stream.get('message_type')} <- {stream.get('topic')}")
        lines.append(f"  state keys: {len(state_keys)}")
        for key in state_keys:
            if isinstance(key, dict):
                lines.append(f"    {key.get('name')}: dim={key.get('output_dim')} <- {key.get('source_topic')}")
        lines.append(f"  action: {action.get('name', 'rel_actions')} dim={action.get('dim', 0)} <- {action.get('source_topic', '')}")
        upload = config.get("upload", {}) if isinstance(config.get("upload"), dict) else {}
        lines.append(f"upload: {'enabled' if upload.get('enabled') else 'disabled'} host={upload.get('host', '')} remote={upload.get('remote_root', '')}")
        self.preview.setPlainText("\n".join(lines))

    def build_default_ai_prompt(self) -> None:
        config = self.current_config(default=True)
        self.apply_form_values(config)
        dataset = config.get("dataset_config", {}) if isinstance(config.get("dataset_config"), dict) else {}
        selected_topics = self.selected_topic_rows()
        self.status.setText("Generating AI prompt from selected ROS topics in background...")
        self.run_async(self.build_prompt_with_ros_probes, self.finish_prompt, dataset, selected_topics, timeout=90.0)

    def build_prompt_with_ros_probes(self, dataset: dict[str, Any], selected_topics: list[dict[str, str]], timeout: float = 90.0) -> object:
        topic_probes = []
        per_call_timeout = max(min(timeout / max(len(selected_topics) * 3, 1), 8.0), 2.0)
        for topic in selected_topics:
            name = str(topic.get("topic") or topic.get("name") or "")
            if not name:
                continue
            probe: dict[str, Any] = {"selected": topic}
            for key, path in [
                ("topic_info", "/api/ros/topic-info"),
                ("echo_once", "/api/ros/topic-echo-once"),
                ("hz", "/api/ros/topic-hz"),
            ]:
                try:
                    probe[key] = self.api.post(path, {"topic": name}, timeout=per_call_timeout)
                except Exception as exc:
                    probe[key] = {"ok": False, "error": str(exc)}
            topic_probes.append(
                probe
            )
        ros_context = {
            "selected_topics": selected_topics,
            "selected_topic_probes": topic_probes,
            "graph_topics": self.graph_data.get("topics", []),
            "graph_nodes": self.graph_data.get("nodes", []),
            "required_output": "dataset_config YAML only; do not include upload, config_meta, paths, collection, review, convert, AI API settings, project name, or project version",
        }
        return self.api.post("/api/ai/config-prompt", {"dataset_config": dataset, "ros_context": ros_context}, timeout=30.0)

    def finish_prompt(self, result: object, error: object) -> None:
        if error is not None:
            self.status.setText(f"Prompt failed: {error}")
            return
        payload = result.get("result", result) if isinstance(result, dict) else {}
        self.ai_prompt.setPlainText(str(payload.get("prompt", "")) if isinstance(payload, dict) else "")
        self.status.setText("Default AI prompt generated.")

    def send_ai_prompt(self) -> None:
        prompt = self.ai_prompt.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "AI", "Generate or enter a prompt first.")
            return
        self.ai_preview.setPlainText("AI request running...")
        self.run_async(self.send_ai_with_settings, self.finish_ai_send, prompt)

    def send_ai_with_settings(self, prompt: str) -> object:
        settings = self.api.get("/api/settings", timeout=5.0)
        ai = settings.get("ai", {}) if isinstance(settings, dict) and isinstance(settings.get("ai"), dict) else {}
        if not ai.get("enabled"):
            raise RuntimeError("Enable AI in Settings first.")
        if not ai.get("base_url") or not ai.get("model"):
            raise RuntimeError("Set AI base URL and model in Settings first.")
        return self.api.post(
            "/api/ai/send",
            {
                "prompt": prompt,
                "kind": "ai_config",
                "base_url": str(ai.get("base_url", "")),
                "model": str(ai.get("model", "")),
                "api_key": str(ai.get("api_key", "")),
            },
            timeout=float(ai.get("timeout_sec") or 120),
        )

    def finish_ai_send(self, result: object, error: object) -> None:
        if error is not None:
            self.ai_preview.setPlainText(f"AI failed:\n{error}")
            self.status.setText(f"AI failed: {error}")
            return
        payload = result.get("result", result) if isinstance(result, dict) else {}
        text = str(payload.get("response", "")) if isinstance(payload, dict) else str(result)
        self.ai_preview.setPlainText(text)
        self.status.setText("AI response received.")

    def replace_yaml_from_ai_preview(self) -> None:
        text = self.ai_preview.toPlainText().strip()
        match = re.search(r"```(?:yaml|yml|json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
        if match:
            text = match.group(1).strip()
        try:
            config = yaml.safe_load(text)
            if not isinstance(config, dict):
                raise ValueError("AI response is not a mapping")
        except Exception as exc:
            QMessageBox.warning(self, "AI Preview", f"Cannot parse AI config:\n{exc}")
            return
        dataset_config = config.get("dataset_config", config)
        if not isinstance(dataset_config, dict):
            QMessageBox.warning(self, "AI Preview", "AI response did not contain a dataset_config mapping.")
            return
        current = self.current_config(default=True)
        current["dataset_config"] = dataset_config
        self.set_config(current)
        self.status.setText("Replaced dataset_config from AI preview.")

    def run_async(self, fn, callback, *args, **kwargs) -> None:
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

    def split_csv(self, text: str) -> list[str]:
        return [part.strip() for part in text.split(",") if part.strip()]

    def image_preprocess(self) -> tuple[dict[str, Any], dict[str, Any]]:
        crop = {"enabled": self.crop_enabled.isChecked(), "x": int(self.crop_x.value()), "y": int(self.crop_y.value()), "width": int(self.crop_w.value()), "height": int(self.crop_h.value())}
        resize = {"enabled": self.resize_enabled.isChecked(), "width": int(self.resize_w.value()), "height": int(self.resize_h.value())}
        return crop, resize

    def first_preprocess(self, dataset: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        cameras = dataset.get("cameras", []) if isinstance(dataset.get("cameras"), list) else []
        if cameras and isinstance(cameras[0], dict):
            return cameras[0].get("crop", {}), cameras[0].get("resize", {})
        streams = dataset.get("streams", []) if isinstance(dataset.get("streams"), list) else []
        if streams and isinstance(streams[0], dict):
            preview = streams[0].get("preview", {}) if isinstance(streams[0].get("preview"), dict) else {}
            return preview.get("crop", {}), preview.get("resize", {})
        return {}, {}

    def stream_name_from_topic(self, topic: str, index: int) -> str:
        lower = topic.lower()
        if "wrist" in lower:
            return "rgb_wrist"
        if "static" in lower or "/camera/color" in lower or "/camera/image" in lower:
            return "rgb_static"
        if "overhead" in lower:
            return "rgb_overhead"
        if "depth" in lower:
            return f"depth_{index}"
        return f"rgb_{index}"

    def camera_role(self, name: str) -> str:
        if "wrist" in name:
            return "wrist"
        if "overhead" in name:
            return "overhead"
        return "static"

    def default_upload_config(self) -> dict[str, Any]:
        return {"enabled": False, "profile_name": "", "host": "", "lan_host": "", "wan_host": "", "port": 22, "username": "", "key_path": "", "remote_root": "", "use_rsync": True, "repair_resume_enabled": True, "verify_after_upload": True}

    def default_dataset_config(self) -> dict[str, Any]:
        return {"environment": {}, "instruction": {}, "ros": {"selected_topics": [], "discovery_snapshot": []}, "robot": {}, "cameras": [], "streams": [], "state": {"keys": []}, "action": {"name": "rel_actions", "source": "", "source_topic": "", "format": "delta_state", "dim": 0, "fields": []}, "recording": {"sample_rate_hz": 10, "stop_mode": "manual", "episode_duration_sec": 0.0, "target_samples": 0}, "dataset": {"output_format": ["npz", "hdf5"], "schema": "calvin_style", "split": "training", "episode_prefix": "episode_", "write_language_annotations": True, "language_annotation_file": "lang_annotations/auto_lang_ann.npy"}}

    def default_total_config(self) -> dict[str, Any]:
        return self.ordered_total_config(
            {
                "config_meta": {"id": "", "name": ""},
                "paths": {"project_root": "", "raw_sessions": "raw_sessions", "review": "review", "exports": "exports", "logs": "logs"},
                "collection": {"default_mode": "manual", "preflight_required": True, "auto_start_monitor": True, "write_session_config_snapshot": True},
                "review": {"local_checks_enabled": True, "ai_review_enabled": False, "marks_file": "review/review_marks.json"},
                "convert": {"default_output_dir": "exports", "write_hdf5": True, "merge_selected_sessions": True},
                "upload": self.default_upload_config(),
                "dataset_config": self.default_dataset_config(),
            },
            "",
        )

    def ordered_total_config(self, config: dict[str, Any], name: str) -> dict[str, Any]:
        meta = config.get("config_meta", {}) if isinstance(config.get("config_meta"), dict) else {}
        meta["id"] = name or str(meta.get("id", ""))
        meta["name"] = name or str(meta.get("name", ""))
        ordered: dict[str, Any] = {
            "config_meta": meta,
            "paths": config.get("paths", {"project_root": "", "raw_sessions": "raw_sessions", "review": "review", "exports": "exports", "logs": "logs"}),
            "collection": config.get("collection", {}),
            "review": config.get("review", {}),
            "convert": config.get("convert", {}),
            "upload": config.get("upload", self.default_upload_config()),
            "dataset_config": config.get("dataset_config", self.default_dataset_config()),
        }
        return ordered
