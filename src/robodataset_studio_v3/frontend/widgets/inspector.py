from __future__ import annotations

import json
import os
import shlex
import sys
import time
from pathlib import Path
from typing import Any
import base64

import numpy as np
from PySide6.QtCore import QProcess, QProcessEnvironment, QTimer, Qt, QThreadPool, Signal
from PySide6.QtGui import QImage, QPainter, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio_v3.frontend.worker import ApiWorker
from robodataset_studio_v3.core.runtime_env import select_rmw
from robodataset_studio_v3.ros.image_conversion import is_image_message_type


class InspectorTerminal(QPlainTextEdit):
    def __init__(self, max_blocks: int = 1500, max_append_chars: int = 20000) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setMaximumBlockCount(max_blocks)
        self._max_append_chars = max_append_chars
        self._auto_scroll = True
        self.verticalScrollBar().valueChanged.connect(self._track_scroll_position)

    def reset_text(self, text: str) -> None:
        self._auto_scroll = True
        self.setPlainText(self._trim_append(text))
        self.scroll_to_latest()

    def append_output(self, text: str) -> None:
        text = self._trim_append(text)
        if not text:
            return
        bar = self.verticalScrollBar()
        previous_value = bar.value()
        follow_latest = self._auto_scroll or self._is_at_bottom()
        self.appendPlainText(text)
        if follow_latest:
            self.scroll_to_latest()
        else:
            bar.setValue(min(previous_value, bar.maximum()))

    def scroll_to_latest(self) -> None:
        self._auto_scroll = True
        self.moveCursor(QTextCursor.End)
        self.ensureCursorVisible()
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def _track_scroll_position(self, value: int) -> None:
        self._auto_scroll = value >= self.verticalScrollBar().maximum() - 4

    def _is_at_bottom(self) -> bool:
        return self.verticalScrollBar().value() >= self.verticalScrollBar().maximum() - 4

    def _trim_append(self, text: str) -> str:
        if len(text) <= self._max_append_chars:
            return text
        keep = max(int((self._max_append_chars - 120) / 2), 1)
        return (
            text[:keep]
            + f"\n...[inspector truncated {len(text) - keep * 2} overflow chars from one update]...\n"
            + text[-keep:]
        )


class ImagePreviewWidget(QWidget):
    sampled = Signal(int, int, int, int, int)

    def __init__(self) -> None:
        super().__init__()
        self.setMouseTracking(True)
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background-color: #101010; border: 1px solid #555;")
        self._frame: np.ndarray | None = None
        self._image: QImage | None = None
        self._image_bytes: bytes = b""
        self._target_rect: tuple[int, int, int, int] | None = None
        self._paint_count = 0
        self._placeholder = "preview not started"

    def set_frame(self, frame: np.ndarray) -> bool:
        if frame.ndim != 3 or frame.shape[2] != 3:
            return False
        contiguous = np.ascontiguousarray(frame.astype(np.uint8, copy=False))
        h, w, _ = contiguous.shape
        self._image_bytes = contiguous.tobytes()
        image = QImage(self._image_bytes, w, h, w * 3, QImage.Format_RGB888)
        if image.isNull():
            return False
        self._frame = contiguous.copy()
        self._image = image.convertToFormat(QImage.Format_RGB888)
        self.update()
        return True

    def clear_frame(self) -> None:
        self._frame = None
        self._image = None
        self._image_bytes = b""
        self._target_rect = None
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.black)
        if self._image is None or self._image.isNull():
            painter.setPen(Qt.white)
            painter.drawText(self.rect(), Qt.AlignCenter, self._placeholder)
            painter.end()
            return
        scaled = self._image.scaled(self.size(), Qt.KeepAspectRatio, Qt.FastTransformation)
        x = int((self.width() - scaled.width()) / 2)
        y = int((self.height() - scaled.height()) / 2)
        self._target_rect = (x, y, scaled.width(), scaled.height())
        painter.drawImage(x, y, scaled)
        self._paint_count += 1
        painter.end()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._frame is None or self._target_rect is None:
            return
        frame_h, frame_w, _ = self._frame.shape
        x0, y0, pix_w, pix_h = self._target_rect
        px = int((event.position().x() - x0) * frame_w / max(pix_w, 1))
        py = int((event.position().y() - y0) * frame_h / max(pix_h, 1))
        if 0 <= px < frame_w and 0 <= py < frame_h:
            r, g, b = [int(v) for v in self._frame[py, px]]
            self.sampled.emit(px, py, r, g, b)


class InspectorDock(QWidget):
    graphUpdated = Signal(dict)

    def __init__(self, api: ApiClient) -> None:
        super().__init__()
        self.api = api
        self.project: ProjectSummary | None = None
        self.pool = QThreadPool.globalInstance()
        self.tabs = QTabWidget()
        self.node = QComboBox()
        self.node.setEditable(True)
        self.topic = QComboBox()
        self.topic.setEditable(True)
        self.image_topic = QComboBox()
        self.image_topic.setEditable(True)
        self.type_label = QLabel("type: -")
        self.image_type_label = QLabel("image type: -")
        self.node_log = self._terminal()
        self.echo_log = self._terminal()
        self.hz_log = self._terminal()
        self.preview_log = self._terminal()
        self.frame_stats = self._terminal(max_blocks=300)
        self.preview = ImagePreviewWidget()
        self.preview.sampled.connect(self.update_sample)
        self.preview_status = QLabel("preview: stopped")
        self.image_meta = QLabel("image: -")
        self.preview_fps = QLabel("preview fps: 0.0")
        self.camera_fps = QLabel("source fps: 0.0")
        self.sample = QLabel("sample: x=- y=- rgb=(-, -, -)")
        self.auto_contrast = QCheckBox("Auto contrast preview")
        self.auto_contrast.setChecked(True)
        self.playback_fps = QSpinBox()
        self.playback_fps.setRange(1, 120)
        self.playback_fps.setValue(30)
        self.playback_fps.setSuffix(" fps")
        self._topic_types: dict[str, str] = {}
        self._project_image_topics: list[str] = []
        self._workers: list[ApiWorker] = []
        self._processes: dict[str, QProcess] = {}
        self._closing = False
        self._preview_process: QProcess | None = None
        self._preview_buffer = ""
        self._latest_frame: np.ndarray | None = None
        self._latest_meta: dict[str, Any] = {}
        self._latest_sequence = 0
        self._displayed_sequence = -1
        self._displayed_frames = 0
        self._last_display_fps_at = time.time()
        self._last_source_fps_at = time.time()
        self._last_source_received = 0
        self._source_fps_window_at = 0.0
        self._source_fps_window_received = 0
        self._max_observed_source_fps = 0.0
        self._auto_tuning_fps = False
        self._paused = False
        self._low_light_warned = False
        self._preview_watchdog = QTimer(self)
        self._preview_watchdog.setSingleShot(True)
        self._preview_watchdog.timeout.connect(self._check_preview_started)
        self._build()
        self._append(self.preview_log, "Inspector image monitor ready. Use Refresh Nodes/Topics, then choose an image topic and start.")

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        self.tabs.addTab(self._topic_page(), "Topic Inspector")
        self.tabs.addTab(self._image_page(), "Image Monitor")
        self.refresh_graph()

    def _topic_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        node_row = QHBoxLayout()
        node_row.addWidget(QLabel("Node"))
        node_row.addWidget(self.node, 1)
        start_node = QPushButton("Start node info")
        stop_node = QPushButton("Stop node info")
        start_node.clicked.connect(self.start_node_info)
        stop_node.clicked.connect(lambda: self.stop_process("node_info"))
        node_row.addWidget(start_node)
        node_row.addWidget(stop_node)

        topic_row = QHBoxLayout()
        topic_row.addWidget(QLabel("Generic topic"))
        topic_row.addWidget(self.topic, 1)
        topic_row.addWidget(self.type_label)
        self.topic.currentTextChanged.connect(self.update_topic_type)

        echo_row = QHBoxLayout()
        start_echo = QPushButton("Start topic echo")
        stop_echo = QPushButton("Stop topic echo")
        start_echo.clicked.connect(lambda: self.start_topic_process("echo"))
        stop_echo.clicked.connect(lambda: self.stop_process("echo"))
        echo_row.addWidget(start_echo)
        echo_row.addWidget(stop_echo)

        hz_row = QHBoxLayout()
        start_hz = QPushButton("Start topic hz")
        stop_hz = QPushButton("Stop topic hz")
        start_hz.clicked.connect(lambda: self.start_topic_process("hz"))
        stop_hz.clicked.connect(lambda: self.stop_process("hz"))
        hz_row.addWidget(start_hz)
        hz_row.addWidget(stop_hz)

        terminals = QTabWidget()
        terminals.addTab(self.node_log, "Node Info")
        terminals.addTab(self.echo_log, "Topic Echo")
        terminals.addTab(self.hz_log, "Topic Hz")
        layout.addLayout(node_row)
        layout.addLayout(topic_row)
        layout.addLayout(echo_row)
        layout.addLayout(hz_row)
        layout.addWidget(terminals)
        return page

    def _image_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        topic_row = QHBoxLayout()
        topic_row.addWidget(QLabel("Image monitor topic"))
        topic_row.addWidget(self.image_topic, 1)
        topic_row.addWidget(self.image_type_label)
        self.image_topic.currentTextChanged.connect(self.update_image_topic_type)
        controls = QHBoxLayout()
        project_monitor = QPushButton("Monitor project image")
        start = QPushButton("Start image monitor")
        stop = QPushButton("Stop image monitor")
        pause = QPushButton("Pause / Resume")
        stats = QPushButton("Frame stats")
        project_monitor.clicked.connect(self.start_project_image_monitor)
        start.clicked.connect(self.start_image_preview)
        stop.clicked.connect(self.stop_image_preview)
        pause.clicked.connect(self.toggle_pause)
        stats.clicked.connect(self.show_frame_stats)
        self.playback_fps.valueChanged.connect(self._update_display_timer)
        controls.addWidget(project_monitor)
        controls.addWidget(start)
        controls.addWidget(stop)
        controls.addWidget(pause)
        controls.addWidget(stats)
        controls.addWidget(self.auto_contrast)
        controls.addWidget(self.playback_fps)
        preview_row = QHBoxLayout()
        preview_row.addWidget(self.preview, 3)
        info = QVBoxLayout()
        for label in [self.preview_status, self.image_meta, self.preview_fps, self.camera_fps, self.sample]:
            label.setWordWrap(True)
            info.addWidget(label)
        info.addStretch(1)
        preview_row.addLayout(info, 1)
        logs = QTabWidget()
        logs.addTab(self.preview_log, "Preview Log")
        logs.addTab(self.frame_stats, "Frame Stats")
        layout.addLayout(topic_row)
        layout.addLayout(controls)
        layout.addLayout(preview_row)
        layout.addWidget(logs)
        return page

    def refresh_graph(self) -> None:
        self._append(self.echo_log, "refreshing ROS graph...")
        self._append(self.preview_log, "refreshing ROS graph for image topics...")
        self._start_worker(self.api.get, self._finish_graph, "/api/ros/graph", timeout=30.0)

    def _finish_graph(self, result: object, error: object) -> None:
        if error is not None:
            self._append(self.echo_log, f"graph error: {error}")
            return
        graph = result if isinstance(result, dict) else {}
        self.set_graph_data(graph)
        self.graphUpdated.emit(graph)

    def set_graph_data(self, graph: dict[str, Any]) -> None:
        nodes = [str(item.get("name", "")) for item in graph.get("nodes", []) if isinstance(item, dict)]
        topics = [item for item in graph.get("topics", []) if isinstance(item, dict)]
        self._topic_types = {str(item.get("name") or item.get("topic") or ""): str(item.get("type") or item.get("message_type") or "") for item in topics}
        topic_names = [str(item.get("name") or item.get("topic") or "") for item in topics]
        self._fill_combo(self.node, nodes)
        self._fill_combo(self.topic, topic_names)
        image_topics = self._image_topic_names(topic_names)
        self._fill_combo(self.image_topic, image_topics, keep_missing=False)
        if topic_names:
            self._append(self.echo_log, f"graph refreshed: {len(topic_names)} topics, {len(nodes)} nodes")
        else:
            self._append(self.echo_log, self._graph_error_summary(graph) or f"graph refreshed: 0 topics, {len(nodes)} nodes")
        if image_topics:
            self._append(self.preview_log, "image topics: " + ", ".join(image_topics))
            if not self._selected_image_topic_name():
                self.image_topic.setCurrentIndex(0)
        else:
            summary = self._graph_error_summary(graph)
            self._append(self.preview_log, summary or "no image topics found in current ROS graph")
        self.update_topic_type(self.topic.currentText())
        self.update_image_topic_type(self.image_topic.currentText())

    def start_node_info(self) -> None:
        node = self.node.currentText().strip()
        if not node:
            return
        self.start_process("node_info", ["ros2", "node", "info", "--no-daemon", node], self.node_log)

    def start_topic_process(self, mode: str) -> None:
        topic = self._selected_topic_name()
        if not topic:
            return
        if mode == "echo":
            command = ["ros2", "topic", "echo", "--no-daemon", "--truncate-length", "512", topic]
        else:
            command = ["ros2", "topic", "hz", topic, "--window", "10"]
        self.start_process(mode, command, self.echo_log if mode == "echo" else self.hz_log)

    def start_process(self, role: str, command: list[str], output: InspectorTerminal) -> None:
        self.stop_process(role)
        process = QProcess(self)
        program, arguments = self._ros_shell_command(command)
        process.setProgram(program)
        process.setArguments(arguments)
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.setProcessEnvironment(self._process_environment())
        process.readyReadStandardOutput.connect(lambda proc=process, pane=output: self._drain_process(proc, pane))
        process.finished.connect(lambda code, status, pane=output, item=role: self._process_finished(item, pane, code, status))
        self._processes[role] = process
        output.reset_text("$ " + " ".join(command))
        process.start()

    def _ros_shell_command(self, command: list[str]) -> tuple[str, list[str]]:
        ros_setup = os.environ.get("ROS_SETUP", "/opt/ros/humble/setup.bash")
        quoted = " ".join(shlex.quote(item) for item in command)
        source = f"source {shlex.quote(ros_setup)} >/dev/null 2>&1 || true"
        return "/bin/bash", ["-lc", f"{source}; exec {quoted}"]

    def _process_environment(self) -> QProcessEnvironment:
        env = QProcessEnvironment.systemEnvironment()
        for key, value in os.environ.items():
            env.insert(key, value)
        rmw = select_rmw(os.environ.get("RMW_IMPLEMENTATION") or os.environ.get("ROBODATASET_RMW_IMPLEMENTATION"))
        env.insert("RMW_IMPLEMENTATION", rmw)
        env.insert("ROBODATASET_RMW_IMPLEMENTATION", rmw)
        env.insert("ROS_LOG_DIR", os.environ.get("ROS_LOG_DIR", "/tmp/robodataset_ros_logs"))
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
        src_dir = os.path.join(root_dir, "src")
        current_pythonpath = env.value("PYTHONPATH", "")
        if src_dir not in current_pythonpath.split(os.pathsep):
            env.insert("PYTHONPATH", f"{src_dir}{os.pathsep}{current_pythonpath}" if current_pythonpath else src_dir)
        return env

    def _graph_error_summary(self, graph: dict[str, Any]) -> str:
        errors = graph.get("errors", {}) if isinstance(graph, dict) else {}
        if not isinstance(errors, dict):
            return ""
        parts = []
        for key in ["topics", "nodes", "services"]:
            text = str(errors.get(key) or "").strip()
            if text:
                parts.append(f"{key}: {text.splitlines()[0]}")
        return "graph returned no topics. " + " | ".join(parts) if parts else ""

    def stop_process(self, role: str) -> None:
        process = self._processes.pop(role, None)
        if process is None:
            return
        process.terminate()
        if not process.waitForFinished(1000):
            process.kill()
            process.waitForFinished(1000)

    def _drain_process(self, process: QProcess, output: InspectorTerminal) -> None:
        data = bytes(process.readAllStandardOutput()).decode(errors="replace")
        if data:
            output.append_output(data.rstrip())

    def _process_finished(self, role: str, output: InspectorTerminal, code: int, status) -> None:
        self._processes.pop(role, None)
        output.append_output(f"[process exited] code={code} status={status}")

    def start_image_preview(self) -> None:
        topic = self._selected_image_topic_name()
        if not topic:
            self.preview_status.setText("preview error: no image topic selected")
            self._append(self.preview_log, "no image topic selected; use Refresh Nodes/Topics and choose an image topic")
            self.refresh_graph()
            return
        topic_type = self._topic_types.get(topic, "")
        if topic_type and not is_image_message_type(topic_type):
            self.preview_status.setText(f"preview error: expected image topic, got {topic_type}")
            self._append(self.preview_log, f"refusing non-image topic {topic} [{topic_type}]")
            return
        if not topic_type:
            self._append(self.preview_log, f"topic type for {topic} is unknown; assuming sensor_msgs/msg/Image")
        self.stop_image_preview(clear_display=False)
        self.preview._placeholder = f"starting {topic}"
        self.preview.update()
        self._latest_frame = None
        self._latest_meta = {}
        self._latest_sequence = 0
        self._displayed_sequence = -1
        self._displayed_frames = 0
        self._last_display_fps_at = time.time()
        self._last_source_fps_at = time.time()
        self._last_source_received = 0
        self._source_fps_window_at = time.time()
        self._source_fps_window_received = 0
        self._max_observed_source_fps = 0.0
        self._low_light_warned = False
        self._paused = False
        process = QProcess(self)
        command = [
            sys.executable,
            "-m",
            "robodataset_studio_v3.ros.image_preview_cli",
            "--topic",
            topic,
            "--message-type",
            topic_type or "sensor_msgs/msg/Image",
            "--max-fps",
            str(self.playback_fps.value()),
        ]
        program, arguments = self._ros_shell_command(command)
        process.setProgram(program)
        process.setArguments(arguments)
        process.setProcessChannelMode(QProcess.SeparateChannels)
        process.setProcessEnvironment(self._process_environment())
        process.readyReadStandardOutput.connect(self._read_preview_stdout)
        process.readyReadStandardError.connect(self._read_preview_stderr)
        process.started.connect(lambda item=topic: self._preview_process_started(item))
        process.errorOccurred.connect(self._preview_process_error)
        process.finished.connect(self._preview_process_finished)
        self._preview_process = process
        self._preview_buffer = ""
        process.start()
        self.preview_status.setText(f"preview: starting {topic}")
        self._append(self.preview_log, f"$ image-monitor subscribe {topic}")
        self._preview_watchdog.start(5000)

    def start_project_image_monitor(self) -> None:
        if self.project is None:
            self.preview_status.setText("preview error: no project is open")
            return
        self._start_worker(self.api.get_project_config, self._finish_project_monitor_config, self.project.key)

    def _finish_project_monitor_config(self, result: object, error: object) -> None:
        if error is not None:
            self.preview_status.setText(f"preview error: {error}")
            self._append(self.preview_log, f"project monitor config error: {error}")
            return
        config = result if isinstance(result, dict) else {}
        project_topics = self._project_image_topics_from_config(config)
        self._project_image_topics = project_topics
        self._fill_combo(self.image_topic, self._image_topic_names(list(self._topic_types)), keep_missing=False)
        graph_images = {topic for topic, msg_type in self._topic_types.items() if is_image_message_type(msg_type)}
        config_only = [topic for topic in project_topics if topic not in graph_images]
        if config_only:
            self._append(self.preview_log, "project config image topics not in current ROS graph: " + ", ".join(config_only))
        current = self._selected_image_topic_name()
        topic = current if self._is_monitorable_image_topic(current, project_topics) else self._first_project_image_topic(config)
        if not topic:
            self.preview_status.setText("preview error: current project config has no image topic")
            return
        index = self.image_topic.findText(topic)
        if index >= 0:
            self.image_topic.setCurrentIndex(index)
        else:
            self.image_topic.setEditText(topic)
        self.show_image()
        self.start_image_preview()

    def _first_project_image_topic(self, config: dict[str, Any]) -> str:
        topics = self._project_image_topics_from_config(config)
        if topics:
            return topics[0]
        return ""

    def _project_image_topics_from_config(self, config: dict[str, Any]) -> list[str]:
        topics: list[str] = []
        dataset_config = config.get("dataset_config", {}) if isinstance(config.get("dataset_config"), dict) else config
        streams = dataset_config.get("streams", [])
        if isinstance(streams, list):
            for item in streams:
                if not isinstance(item, dict):
                    continue
                message_type = str(item.get("message_type") or item.get("type") or "")
                topic = str(item.get("topic") or "")
                if topic and is_image_message_type(message_type):
                    topics.append(topic)
            for item in streams:
                if isinstance(item, dict) and item.get("topic"):
                    topic = str(item.get("topic") or "")
                    if is_image_message_type(self._topic_types.get(topic, "")):
                        topics.append(topic)
        cameras = dataset_config.get("cameras", [])
        if isinstance(cameras, list):
            for item in cameras:
                if isinstance(item, dict) and item.get("topic"):
                    topics.append(str(item.get("topic")))
        ros = config.get("ros", {}) if isinstance(config.get("ros"), dict) else {}
        for key in ["selected_topics", "discovery_snapshot"]:
            rows = ros.get(key, [])
            if not isinstance(rows, list):
                continue
            for item in rows:
                if not isinstance(item, dict):
                    continue
                topic = str(item.get("topic") or item.get("name") or "")
                message_type = str(item.get("message_type") or item.get("type") or "")
                if topic and is_image_message_type(message_type):
                    topics.append(topic)
                    self._topic_types.setdefault(topic, message_type)
        return list(dict.fromkeys(topic for topic in topics if topic))

    def _image_topic_names(self, graph_topic_names: list[str]) -> list[str]:
        graph_images = [name for name in graph_topic_names if is_image_message_type(self._topic_types.get(name, ""))]
        return list(dict.fromkeys([*graph_images, *self._project_image_topics]))

    def _is_monitorable_image_topic(self, topic: str, project_topics: list[str]) -> bool:
        if not topic:
            return False
        topic_type = self._topic_types.get(topic, "")
        return is_image_message_type(topic_type) or topic in project_topics

    def stop_image_preview(self, clear_display: bool = True) -> None:
        process = self._preview_process
        self._preview_process = None
        if process is not None:
            self._preview_watchdog.stop()
            process.terminate()
            if not process.waitForFinished(1500):
                process.kill()
                process.waitForFinished(1500)
            process.deleteLater()
        if clear_display:
            self.preview.clear_frame()
            self.image_meta.setText("image: -")
        self.preview_status.setText("preview: stopped")

    def _read_preview_stdout(self) -> None:
        process = self._preview_process
        if process is None:
            return
        self._preview_buffer += bytes(process.readAllStandardOutput()).decode(errors="replace")
        while "\n" in self._preview_buffer:
            line, self._preview_buffer = self._preview_buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                self._append(self.preview_log, line)
                continue
            self._handle_preview_payload(payload)

    def _read_preview_stderr(self) -> None:
        process = self._preview_process
        if process is None:
            return
        text = bytes(process.readAllStandardError()).decode(errors="replace").strip()
        if text:
            self._append(self.preview_log, text)

    def _preview_process_finished(self, code: int, status) -> None:
        self._preview_watchdog.stop()
        if self._preview_process is not None:
            self._append(self.preview_log, f"[preview exited] code={code} status={status}")
            self._preview_process = None
        self.preview_status.setText("preview: stopped")

    def _preview_process_started(self, topic: str) -> None:
        self._append(self.preview_log, f"preview process started for {topic}")

    def _preview_process_error(self, error) -> None:
        process = self._preview_process
        detail = process.errorString() if process is not None else str(error)
        self.preview_status.setText(f"preview error: process failed: {detail}")
        self._append(self.preview_log, f"preview process error: {detail}")

    def _check_preview_started(self) -> None:
        if self._preview_process is None or self._latest_frame is not None:
            return
        topic = self._selected_image_topic_name()
        self.preview_status.setText("preview warning: subscribed but no frame received yet")
        self._append(
            self.preview_log,
            f"no image frame received after 5s for {topic or '(empty topic)'}; check topic selection, publisher, ROS_DOMAIN_ID, and RMW",
        )

    def _handle_preview_payload(self, payload: dict[str, Any]) -> None:
        kind = str(payload.get("type") or "")
        if kind == "status":
            text = str(payload.get("text") or "")
            self.preview_status.setText(text)
            self._append(self.preview_log, text)
            self._update_source_fps_from_status(payload)
            return
        if kind == "error":
            text = str(payload.get("error") or "preview error")
            self.preview_status.setText(f"preview error: {text}")
            self._append(self.preview_log, text)
            return
        if kind != "frame" or self._paused:
            return
        meta = payload.get("meta", {}) if isinstance(payload.get("meta"), dict) else {}
        received = int(meta.get("received", 0) or 0)
        if received <= self._displayed_sequence:
            return
        frame = self._frame_from_preview_payload(payload, meta)
        if frame is None:
            self._append(self.preview_log, "preview frame decode failed")
            return
        self._latest_frame = frame
        self._latest_meta = meta
        self._latest_sequence = received
        self._warn_if_low_light(frame, meta)
        display_frame = self._display_frame(frame)
        if not self.preview.set_frame(display_frame):
            self._append(self.preview_log, "preview QImage creation failed for RGB888 display frame")
            return
        self._log_display_frame_stats(display_frame, meta)
        self._displayed_sequence = received
        self._displayed_frames += 1
        self._update_fps_labels()

    def _display_frame(self, frame: np.ndarray) -> np.ndarray:
        if not self.auto_contrast.isChecked():
            return frame
        values = frame.astype(np.float32)
        low = float(np.percentile(values, 1))
        high = float(np.percentile(values, 99))
        if high <= low + 1.0:
            return frame
        return np.clip((values - low) * 255.0 / (high - low), 0, 255).astype(np.uint8)

    def _warn_if_low_light(self, frame: np.ndarray, meta: dict[str, Any]) -> None:
        luminance = 0.2126 * frame[:, :, 0] + 0.7152 * frame[:, :, 1] + 0.0722 * frame[:, :, 2]
        mean = float(luminance.mean())
        maximum = float(luminance.max())
        meta["luminance_mean"] = round(mean, 2)
        meta["luminance_max"] = round(maximum, 2)
        if self._low_light_warned or mean >= 30.0:
            return
        self._low_light_warned = True
        self._append(
            self.preview_log,
            f"low-light frame detected: luminance mean={mean:.1f}, max={maximum:.1f}; Auto contrast preview is display-only and does not change recorded data",
        )

    def _log_display_frame_stats(self, frame: np.ndarray, meta: dict[str, Any]) -> None:
        published = int(meta.get("published", 0) or 0)
        if published not in {1, 30, 120}:
            return
        luminance = 0.2126 * frame[:, :, 0] + 0.7152 * frame[:, :, 1] + 0.0722 * frame[:, :, 2]
        path_text = ""
        if published == 1:
            try:
                path = Path("/tmp/robodataset_inspector_display_frame.png")
                self.preview._image.save(str(path), "PNG")
                path_text = f"; saved display frame: {path}"
            except Exception as exc:
                path_text = f"; display frame save failed: {exc}"
        self._append(
            self.preview_log,
            "display frame stats: "
            f"shape={frame.shape[1]}x{frame.shape[0]} "
            f"rgb_mean={frame.mean(axis=(0, 1)).round(1).tolist()} "
            f"luma_mean={float(luminance.mean()):.1f} luma_max={float(luminance.max()):.1f} "
            f"widget={self.preview.width()}x{self.preview.height()} paints={self.preview._paint_count}"
            + path_text,
        )

    def _frame_from_preview_payload(self, payload: dict[str, Any], meta: dict[str, Any]) -> np.ndarray | None:
        raw_rgb = str(payload.get("rgb_base64") or "")
        width = int(meta.get("rgb_width") or meta.get("width") or 0)
        height = int(meta.get("rgb_height") or meta.get("height") or 0)
        if raw_rgb and width > 0 and height > 0:
            try:
                data = base64.b64decode(raw_rgb)
                expected = width * height * 3
                if len(data) == expected:
                    return np.frombuffer(data, dtype=np.uint8).reshape((height, width, 3)).copy()
                self._append(self.preview_log, f"preview rgb payload has {len(data)} bytes, expected {expected}")
            except Exception as exc:
                self._append(self.preview_log, f"preview rgb decode failed: {exc}")

        ppm = str(payload.get("ppm_base64") or "")
        if not ppm:
            return None
        try:
            image_data = base64.b64decode(ppm)
        except Exception as exc:
            self._append(self.preview_log, f"preview ppm base64 decode failed: {exc}")
            return None
        pixmap = QPixmap()
        pixmap.loadFromData(image_data, "PPM")
        if pixmap.isNull():
            return None
        image = pixmap.toImage().convertToFormat(QImage.Format_RGB888)
        width = image.width()
        height = image.height()
        ptr = image.constBits()
        return np.frombuffer(ptr, dtype=np.uint8).reshape((height, image.bytesPerLine()))[:, : width * 3].reshape((height, width, 3)).copy()

    def _update_fps_labels(self) -> None:
        now = time.time()
        if now - self._last_display_fps_at >= 1.0:
            self.preview_fps.setText(f"preview fps: {self._displayed_frames / max(now - self._last_display_fps_at, 0.001):.1f}")
            self._displayed_frames = 0
            self._last_display_fps_at = now
        if now - self._last_source_fps_at >= 1.0:
            received = self._latest_sequence
            fps = (received - self._last_source_received) / max(now - self._last_source_fps_at, 0.001)
            self.camera_fps.setText(f"source fps: {fps:.1f}")
            self._last_source_received = received
            self._last_source_fps_at = now
        if self._latest_meta:
            self.image_meta.setText(
                f"image: {self._latest_meta.get('width')}x{self._latest_meta.get('height')} {self._latest_meta.get('encoding')} "
                f"luma={self._latest_meta.get('luminance_mean', '-')}"
            )

    def _update_source_fps_from_status(self, payload: dict[str, Any]) -> None:
        received = int(payload.get("received", 0) or 0)
        now = time.time()
        if received <= 0:
            self._source_fps_window_at = now
            self._source_fps_window_received = received
            return
        if self._source_fps_window_at <= 0:
            self._source_fps_window_at = now
            self._source_fps_window_received = received
            return
        elapsed = now - self._source_fps_window_at
        delta = received - self._source_fps_window_received
        if elapsed < 2.0 or delta <= 0:
            return
        fps = delta / max(elapsed, 0.001)
        self._source_fps_window_at = now
        self._source_fps_window_received = received
        if fps <= self._max_observed_source_fps + 0.05:
            return
        self._max_observed_source_fps = fps
        target = max(1, int(round(fps)) - 1)
        if target == self.playback_fps.value():
            return
        self._auto_tuning_fps = True
        self.playback_fps.setValue(target)
        self._auto_tuning_fps = False
        self._append(self.preview_log, f"auto preview fps set to {target} from max observed source fps {fps:.1f}")

    def toggle_pause(self) -> None:
        self._paused = not self._paused
        self.preview_status.setText("preview: paused" if self._paused else "preview: playing")
        if self._paused:
            self.show_frame_stats()

    def show_frame_stats(self) -> None:
        if self._latest_frame is None:
            self.frame_stats.reset_text("No frame available.")
            return
        frame = self._latest_frame.astype(np.float32)
        luminance = 0.2126 * frame[:, :, 0] + 0.7152 * frame[:, :, 1] + 0.0722 * frame[:, :, 2]
        means = frame.mean(axis=(0, 1))
        stds = frame.std(axis=(0, 1))
        text = (
            f"shape: {self._latest_frame.shape[0]}x{self._latest_frame.shape[1]} rgb\n"
            f"luminance mean/std/min/max: {luminance.mean():.2f} / {luminance.std():.2f} / {luminance.min():.0f} / {luminance.max():.0f}\n"
            f"underexposed <=5: {(luminance <= 5).mean() * 100:.2f}%\n"
            f"overexposed >=250: {(luminance >= 250).mean() * 100:.2f}%\n"
            f"rgb mean: R={means[0]:.2f} G={means[1]:.2f} B={means[2]:.2f}\n"
            f"rgb std: R={stds[0]:.2f} G={stds[1]:.2f} B={stds[2]:.2f}"
        )
        self.frame_stats.reset_text(text)

    def update_sample(self, x: int, y: int, r: int, g: int, b: int) -> None:
        self.sample.setText(f"sample: x={x} y={y} rgb=({r}, {g}, {b})")

    def _update_display_timer(self) -> None:
        if self._auto_tuning_fps:
            return
        process = self._preview_process
        if process is not None:
            topic = self._selected_image_topic_name()
            self.stop_image_preview(clear_display=False)
            if topic:
                self.start_image_preview()

    def _start_worker(self, fn, callback, *args, **kwargs) -> None:
        worker = ApiWorker(fn, *args, **kwargs)
        self._workers.append(worker)

        def finish(result: object, error: object, item: ApiWorker = worker) -> None:
            try:
                if not self._closing:
                    callback(result, error)
            finally:
                if item in self._workers:
                    self._workers.remove(item)

        worker.signals.finished.connect(finish, Qt.QueuedConnection)
        self.pool.start(worker)

    def _fill_combo(self, combo: QComboBox, items: list[str], *, keep_missing: bool = True) -> None:
        current = combo.currentText().strip()
        combo.blockSignals(True)
        combo.clear()
        combo.addItems([item for item in items if item])
        if current:
            index = combo.findText(current)
            if index >= 0:
                combo.setCurrentIndex(index)
            elif keep_missing:
                combo.setEditText(current)
        combo.blockSignals(False)

    def _selected_topic_name(self) -> str:
        return self.topic.currentText().split(" [", 1)[0].strip()

    def _selected_image_topic_name(self) -> str:
        return self.image_topic.currentText().split(" [", 1)[0].strip()

    def update_topic_type(self, _text: str) -> None:
        topic = self._selected_topic_name()
        self.type_label.setText(f"type: {self._topic_types.get(topic, '-') or '-'}")

    def update_image_topic_type(self, _text: str) -> None:
        topic = self._selected_image_topic_name()
        self.image_type_label.setText(f"image type: {self._topic_types.get(topic, '-') or '-'}")

    def _append(self, output: InspectorTerminal, text: str) -> None:
        output.append_output(text)

    def _terminal(self, max_blocks: int = 1500) -> InspectorTerminal:
        return InspectorTerminal(max_blocks=max_blocks)

    def show_topic(self) -> None:
        self.tabs.setCurrentIndex(0)

    def show_image(self) -> None:
        self.tabs.setCurrentIndex(1)

    def set_project(self, project: ProjectSummary | None) -> None:
        self.project = project
        self._project_image_topics = []
        if project is not None:
            self._start_worker(self.api.get_project_config, self._finish_project_topics_config, project.key)

    def _finish_project_topics_config(self, result: object, error: object) -> None:
        if error is not None:
            return
        config = result if isinstance(result, dict) else {}
        self._project_image_topics = self._project_image_topics_from_config(config)
        self._fill_combo(self.image_topic, self._image_topic_names(list(self._topic_types)), keep_missing=False)
        if self._project_image_topics:
            self._append(self.preview_log, f"loaded {len(self._project_image_topics)} project image topic(s)")
        self.update_image_topic_type(self.image_topic.currentText())

    def stop_workers(self) -> None:
        self._closing = True
        for role in list(self._processes):
            self.stop_process(role)
        self.stop_image_preview()
        self._workers.clear()
