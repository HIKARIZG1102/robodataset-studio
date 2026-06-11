from __future__ import annotations

import json
import os
import re
from pathlib import Path, PurePosixPath

import threading
import time
from dataclasses import dataclass
from uuid import uuid4

import numpy as np
from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QPlainTextEdit,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from robodataset_studio.core.config_manager import ConfigManager
from robodataset_studio.core.config_library import ConfigLibrary
from robodataset_studio.core.environment import EnvironmentService
from robodataset_studio.core.models import ProcessRecord, ProjectState
from robodataset_studio.core.process_manager import ProcessManager
from robodataset_studio.dataset.converter import Hdf5Converter
from robodataset_studio.dataset.layout import CalvinLayoutScanner
from robodataset_studio.dataset.merge_plan import CalvinMergePlanner, CalvinSessionMerger
from robodataset_studio.dataset.recorder import MockRecorder
from robodataset_studio.dataset.validator import DatasetValidator
from robodataset_studio.ros.episode_recorder import RosEpisodeRecorder, RosEpisodeResult
from robodataset_studio.ros.graph_discovery import RosGraphDiscovery
from robodataset_studio.ros.image_conversion import image_bytes_to_rgb
from robodataset_studio.ui.i18n import apply_i18n
from robodataset_studio.upload.manifest import MANIFEST_NAME, UploadManifest
from robodataset_studio.upload.ssh_uploader import SshConnection, SshUploader
from robodataset_studio.upload.ssh_profiles import SshProfile, SshProfileStore


class AppContext(QObject):
    language_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.state = ProjectState()
        self.config_manager = ConfigManager()
        self.config_library = ConfigLibrary()
        self.process_manager = ProcessManager()
        self.environment = EnvironmentService()
        self.discovery = RosGraphDiscovery()
        self.recorder = MockRecorder()
        self.ros_recorder = RosEpisodeRecorder()
        self.validator = DatasetValidator()
        self.converter = Hdf5Converter()
        self.layout_scanner = CalvinLayoutScanner()
        self.merge_planner = CalvinMergePlanner()
        self.session_merger = CalvinSessionMerger()
        self.ssh_profiles = SshProfileStore()
        self.last_graph: dict[str, list[dict[str, str]]] = {"nodes": [], "topics": [], "services": []}

    def has_config(self) -> bool:
        return bool(self.state.collection_config)

    def has_raw_episodes(self) -> bool:
        return self.state.episodes_dir.exists() and any(self.state.episodes_dir.glob("episode_*.npz"))

    def has_converted_dataset(self) -> bool:
        return any(path.exists() for path in self.state.conversion_outputs) or (self.state.merged_dir / "calvin.hdf5").exists()

    def set_language(self, language: str) -> None:
        language = "en" if language == "en" else "zh"
        if self.state.language == language:
            return
        self.state.language = language
        self.language_changed.emit(language)


class ImagePreviewWidget(QWidget):
    sampled = Signal(int, int, int, int, int)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(640, 360)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self._frame: np.ndarray | None = None
        self._image: QImage | None = None
        self._target_rect = None

    def set_frame(self, frame: np.ndarray) -> None:
        self._frame = frame
        h, w, _ = frame.shape
        image = QImage(frame.data, w, h, 3 * w, QImage.Format_RGB888)
        self._image = image.copy()
        self.update()

    def clear_frame(self) -> None:
        self._frame = None
        self._image = None
        self._target_rect = None
        self.update()

    def has_frame(self) -> bool:
        return self._image is not None and not self._image.isNull()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.black)
        if self._image is None or self._image.isNull():
            painter.end()
            return
        scaled = self._image.scaled(self.size(), Qt.KeepAspectRatio, Qt.FastTransformation)
        x = int((self.width() - scaled.width()) / 2)
        y = int((self.height() - scaled.height()) / 2)
        self._target_rect = (x, y, scaled.width(), scaled.height())
        painter.drawImage(x, y, scaled)
        painter.end()

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt API
        return max(360, int(width * 9 / 16))

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt API
        return True

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


class RosImagePreviewWorker(QObject):
    status_changed = Signal(str)
    finished = Signal()

    def __init__(self, topic: str) -> None:
        super().__init__()
        self.topic = topic
        self._running = True
        self._lock = threading.Lock()
        self._received = 0
        self._last_status_at = 0.0
        self.latest_data: bytes | None = None
        self.latest_meta: dict[str, object] = {}

    @Slot()
    def run(self) -> None:
        context = None
        executor = None
        node = None
        try:
            if os.environ.get("ROBODATASET_DISABLE_FASTDDS_SHM", "1") == "1":
                profile = Path(__file__).resolve().parents[3] / "config" / "fastdds_no_shm.xml"
                if profile.exists():
                    os.environ.setdefault("RMW_IMPLEMENTATION", os.environ.get("ROBODATASET_RMW_IMPLEMENTATION", "rmw_cyclonedds_cpp"))
                    os.environ.setdefault("FASTDDS_DEFAULT_PROFILES_FILE", str(profile))
                    os.environ.setdefault("FASTRTPS_DEFAULT_PROFILES_FILE", str(profile))
            import rclpy
            from rclpy.executors import SingleThreadedExecutor
            from rclpy.qos import qos_profile_sensor_data
            from sensor_msgs.msg import Image

            context = rclpy.Context()
            rclpy.init(context=context)
            node = rclpy.create_node(f"robodataset_image_preview_{uuid4().hex[:8]}", context=context)
            executor = SingleThreadedExecutor(context=context)
            executor.add_node(node)

            def on_image(msg: Image) -> None:
                with self._lock:
                    self._received += 1
                    self.latest_data = bytes(msg.data)
                    self.latest_meta = {
                        "encoding": msg.encoding,
                        "width": int(msg.width),
                        "height": int(msg.height),
                        "step": int(msg.step),
                        "received": self._received,
                    }
                now = time.time()
                if now - self._last_status_at >= 1.0:
                    self._last_status_at = now
                    self.status_changed.emit(
                        f"receiving frames={self.frames_received()} encoding={msg.encoding} size={msg.width}x{msg.height}"
                    )

            node.create_subscription(Image, self.topic, on_image, qos_profile_sensor_data)
            self.status_changed.emit(f"subscribed: {self.topic}")
            while self._running and context.ok():
                executor.spin_once(timeout_sec=0.1)
        except Exception as exc:
            self.status_changed.emit(f"preview error: {exc}")
        finally:
            if executor is not None and node is not None:
                try:
                    executor.remove_node(node)
                except Exception:
                    pass
            if node is not None:
                try:
                    node.destroy_node()
                except Exception:
                    pass
            if context is not None:
                try:
                    context.try_shutdown()
                except Exception:
                    pass
            self.finished.emit()

    def stop(self) -> None:
        self._running = False
        self.clear_buffer()

    def snapshot(self) -> tuple[bytes | None, dict[str, object]]:
        with self._lock:
            return self.latest_data, dict(self.latest_meta)

    def frames_received(self) -> int:
        with self._lock:
            return self._received

    def clear_buffer(self) -> None:
        with self._lock:
            self.latest_data = None
            self.latest_meta = {}


class RosRecordingWorker(QObject):
    finished = Signal(object, object)

    def __init__(
        self,
        recorder: RosEpisodeRecorder,
        config: dict,
        episodes_dir: Path,
        episode_index: int,
        duration_sec: float,
    ) -> None:
        super().__init__()
        self.recorder = recorder
        self.config = config
        self.episodes_dir = episodes_dir
        self.episode_index = episode_index
        self.duration_sec = duration_sec

    @Slot()
    def run(self) -> None:
        try:
            result = self.recorder.record_episode(
                self.config,
                self.episodes_dir,
                self.episode_index,
                duration_sec=self.duration_sec,
            )
        except Exception as exc:
            self.finished.emit(None, exc)
            return
        self.finished.emit(result, None)


@dataclass
class CaptureMonitorSlot:
    stream_name: str
    topic: str
    widget: QWidget
    preview: ImagePreviewWidget
    status: QLabel
    meta: QLabel
    fps: QLabel
    start_button: QPushButton
    stop_button: QPushButton
    timer: QTimer
    thread: QThread | None = None
    worker: RosImagePreviewWorker | None = None
    latest_sequence: int = 0
    displayed_sequence: int = -1
    frames: int = 0
    last_fps_at: float = 0.0


class ProjectPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.task = QLineEdit(ctx.state.task_name)
        self.version = QLineEdit(ctx.state.version)
        self.operator = QLineEdit(ctx.state.operator)
        self.root = QLineEdit(str(ctx.state.dataset_root))
        browse = QPushButton("Browse")
        browse.clicked.connect(self.browse_root)
        preset = QPushButton("Use gello_widowx preset")
        preset.clicked.connect(self.use_gello_preset)
        save = QPushButton("Save Project")
        save.clicked.connect(self.save)

        root_row = QHBoxLayout()
        root_row.addWidget(self.root)
        root_row.addWidget(browse)
        root_row.addWidget(preset)

        form = QFormLayout()
        form.addRow("Task name", self.task)
        form.addRow("Version", self.version)
        form.addRow("Operator", self.operator)
        form.addRow("Dataset root", root_row)

        self.summary = QPlainTextEdit()
        self.summary.setReadOnly(True)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(save)
        layout.addWidget(QLabel("Project paths"))
        layout.addWidget(self.summary)
        self.save()

    def browse_root(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Dataset root", self.root.text())
        if path:
            self.root.setText(path)

    def use_gello_preset(self) -> None:
        self.root.setText("/data/dataset/calvin/robot_datasets/gello_widowx")
        self.task.setText("catch_the_satellite_2fig")
        self.version.setText("v1")

    def save(self) -> None:
        self.ctx.state.task_name = self.task.text().strip() or "task"
        self.ctx.state.version = self.version.text().strip() or "v1"
        self.ctx.state.operator = self.operator.text().strip()
        self.ctx.state.dataset_root = Path(self.root.text()).expanduser()
        self.summary.setPlainText(
            f"session: {self.ctx.state.current_session}\n"
            f"raw session: {self.ctx.state.raw_session_dir}\n"
            f"episodes: {self.ctx.state.episodes_dir}\n"
            f"merged: {self.ctx.state.merged_dir}"
        )


class EnvironmentPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        layout = QVBoxLayout(self)
        layout.addWidget(refresh)
        layout.addWidget(self.report)
        self.refresh()

    def refresh(self) -> None:
        self.report.setPlainText(self.ctx.environment.report_text())


class DiscoveryPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.nodes = QListWidget()
        self.nodes.currentRowChanged.connect(self.select_node)
        self.topics = QTableWidget(0, 3)
        self.topics.setHorizontalHeaderLabels(["Use", "Topic", "Type"])
        self.topics.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.topics.setSelectionMode(QAbstractItemView.NoSelection)
        self.topics.setWordWrap(False)
        self.topics.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.topics.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.topics.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        refresh = QPushButton("Discover ROS2 Graph")
        refresh.clicked.connect(self.refresh)
        generate = QPushButton("Generate Listener Config From Selected Topics")
        generate.clicked.connect(self.generate_config)
        layout = QVBoxLayout(self)
        layout.addWidget(refresh)
        layout.addWidget(QLabel("Nodes"))
        layout.addWidget(self.nodes)
        layout.addWidget(QLabel("Topics"))
        layout.addWidget(self.topics)
        layout.addWidget(generate)

    def refresh(self) -> None:
        graph = self.ctx.discovery.discover()
        self.ctx.last_graph = graph
        self.populate_graph(graph)

    def populate_graph(self, graph: dict[str, list[dict[str, str]]]) -> None:
        self.nodes.clear()
        for node in graph.get("nodes", []):
            self.nodes.addItem(node["name"])
        topics = graph.get("topics", [])
        self.topics.setRowCount(len(topics))
        for row, topic in enumerate(topics):
            self.topics.setItem(row, 0, self._make_check_item(Qt.Unchecked))
            self.topics.setItem(row, 1, self._text_item(topic.get("name", "")))
            self.topics.setItem(row, 2, self._text_item(topic.get("type", "")))
        self.topics.resizeRowsToContents()
        if graph.get("nodes"):
            self.nodes.setCurrentRow(0)

    def generate_config(self) -> None:
        selected_topics = self._selected_topics()
        topics = selected_topics or self.ctx.last_graph.get("topics", [])
        self.ctx.state.collection_config = self.ctx.config_manager.build_default_config(
            self.ctx.state, topics
        )
        self.ctx.state.selected_streams = topics
        QMessageBox.information(
            self,
            "Config",
            f"listener-only collection_config.yaml generated from {len(topics)} topic(s). Open Config page to edit/save.",
        )

    def select_node(self, row: int) -> None:
        nodes = self.ctx.last_graph.get("nodes", [])
        if 0 <= row < len(nodes):
            self.ctx.state.selected_nodes = [nodes[row].get("name", "")]

    def _make_check_item(self, state: Qt.CheckState) -> QTableWidgetItem:
        item = QTableWidgetItem("")
        item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        item.setCheckState(state)
        return item

    def _text_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setToolTip(text)
        item.setFlags(Qt.ItemIsEnabled)
        return item

    def _selected_topics(self) -> list[dict[str, str]]:
        topics = self.ctx.last_graph.get("topics", [])
        rows = []
        for row in range(self.topics.rowCount()):
            item = self.topics.item(row, 0)
            if item is not None and item.checkState() == Qt.Checked:
                rows.append(row)
        return [topics[row] for row in rows if 0 <= row < len(topics)]


class InspectorPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.topic = QComboBox()
        self.topic.setEditable(True)
        self.image_topic = QComboBox()
        self.image_topic.setEditable(True)
        self.node = QComboBox()
        self.node.setEditable(True)
        self.type_label = QLabel("type: -")
        self.image_type_label = QLabel("image type: -")
        self.decoupled_hint = QLabel("Node, generic topic, and image topic are independent selections.")
        self.preview_status = QLabel("preview: stopped")
        self.image_meta = QLabel("image: -")
        self._topic_types: dict[str, str] = {}
        self._inspector_processes: dict[str, str] = {}
        self._preview_thread: QThread | None = None
        self._preview_worker: RosImagePreviewWorker | None = None
        refresh_choices = QPushButton("Refresh from Discovery")
        start_node_info = QPushButton("Start node info")
        stop_node_info = QPushButton("Stop node info")
        start_echo = QPushButton("Start topic echo")
        stop_echo = QPushButton("Stop topic echo")
        start_hz = QPushButton("Start topic hz")
        stop_hz = QPushButton("Stop topic hz")
        start_preview = QPushButton("Start image monitor")
        stop_preview = QPushButton("Stop image monitor")
        self.pause_preview_button = QPushButton("Pause preview")
        self.pause_preview_button.clicked.connect(self.toggle_preview_pause)
        refresh_choices.clicked.connect(self.refresh_choices)
        start_node_info.clicked.connect(self.start_node_info)
        stop_node_info.clicked.connect(lambda: self.stop_inspector_process("node_info"))
        start_echo.clicked.connect(lambda: self.start_probe("echo"))
        stop_echo.clicked.connect(lambda: self.stop_inspector_process("echo"))
        start_hz.clicked.connect(lambda: self.start_probe("hz"))
        stop_hz.clicked.connect(lambda: self.stop_inspector_process("hz"))
        start_preview.clicked.connect(self.start_image_preview)
        stop_preview.clicked.connect(self.stop_image_preview)
        self.topic.currentTextChanged.connect(self.update_topic_type)
        self.image_topic.currentTextChanged.connect(self.update_image_topic_type)
        self.node.currentTextChanged.connect(self.update_selected_node)
        self.node_log = self._terminal()
        self.echo_log = self._terminal()
        self.hz_log = self._terminal()
        self.preview_log = self._terminal()
        self.frame_stats = self._terminal()
        self.preview = ImagePreviewWidget()
        self.preview.sampled.connect(self.update_sample)
        self.sample = QLabel("sample: x=- y=- rgb=(-, -, -)")
        self.fps = QLabel("preview fps: 0.0")
        self.camera_fps = QLabel("camera fps: 0.0")
        for label in [self.preview_status, self.image_meta, self.fps, self.camera_fps, self.sample]:
            label.setMinimumWidth(260)
            label.setMaximumWidth(320)
            label.setWordWrap(False)
            label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.playback_fps = QSpinBox()
        self.playback_fps.setRange(1, 480)
        self.playback_fps.setValue(10)
        self.playback_fps.setSuffix(" fps")
        self.playback_fps.setFixedWidth(96)
        self.playback_fps.setToolTip("Display target FPS. Source image stream still runs at its original rate.")
        self._frames = 0
        self._last_display_fps_at = time.time()
        self._last_camera_fps_at = time.time()
        self._max_camera_fps = 0.0
        self._last_source_received = 0
        self.playback_fps.setMinimum(1)
        self._manual_playback_override = False
        self._auto_playback_deadline = 0.0
        self._effective_playback_fps = self.playback_fps.value()
        self._preview_generation = 0
        self.playback_fps.valueChanged.connect(self.set_manual_playback_fps)
        self._latest_frame: np.ndarray | None = None
        self._latest_meta: dict[str, object] = {}
        self._latest_sequence = 0
        self._displayed_sequence = -1
        self._paused_frame: np.ndarray | None = None
        self._preview_paused = False
        layout = QVBoxLayout(self)
        layout.addWidget(refresh_choices)
        node_row = QHBoxLayout()
        node_row.addWidget(QLabel("Node"))
        node_row.addWidget(self.node, 1)
        node_row.addWidget(start_node_info)
        node_row.addWidget(stop_node_info)
        topic_row = QHBoxLayout()
        topic_row.addWidget(QLabel("Generic topic"))
        topic_row.addWidget(self.topic, 1)
        topic_row.addWidget(self.type_label)
        echo_row = QHBoxLayout()
        echo_row.addWidget(start_echo)
        echo_row.addWidget(stop_echo)
        hz_row = QHBoxLayout()
        hz_row.addWidget(start_hz)
        hz_row.addWidget(stop_hz)
        image_topic_row = QHBoxLayout()
        image_topic_row.addWidget(QLabel("Image monitor topic"))
        image_topic_row.addWidget(self.image_topic, 1)
        image_topic_row.addWidget(self.image_type_label)
        preview_buttons = QHBoxLayout()
        preview_buttons.addWidget(start_preview)
        preview_buttons.addWidget(stop_preview)
        preview_buttons.addWidget(self.pause_preview_button)
        preview_buttons.addWidget(self.playback_fps)
        layout.addWidget(self.decoupled_hint)
        layout.addLayout(node_row)
        layout.addLayout(topic_row)
        layout.addLayout(echo_row)
        layout.addLayout(hz_row)
        layout.addLayout(image_topic_row)
        layout.addLayout(preview_buttons)
        preview_row = QHBoxLayout()
        preview_row.setContentsMargins(0, 0, 0, 0)
        preview_row.addWidget(self.preview, 3)
        info_col = QVBoxLayout()
        info_col.setContentsMargins(0, 0, 0, 0)
        info_col.addWidget(QLabel("Image Topic Preview"))
        info_col.addWidget(self.preview_status)
        info_col.addWidget(self.image_meta)
        info_col.addWidget(self.fps)
        info_col.addWidget(self.camera_fps)
        info_col.addWidget(self.sample)
        info_col.addStretch(1)
        preview_row.addLayout(info_col, 1)
        layout.addLayout(preview_row)
        terminals = QTabWidget()
        terminals.addTab(self.node_log, "Node Info")
        terminals.addTab(self.echo_log, "Topic Echo")
        terminals.addTab(self.hz_log, "Topic Hz")
        terminals.addTab(self.preview_log, "Preview Log")
        terminals.addTab(self.frame_stats, "Frame Stats")
        terminals.setMinimumHeight(220)
        layout.addWidget(terminals)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_output)
        self.timer.start(1000)
        self.playback_timer = QTimer(self)
        self.playback_timer.setTimerType(Qt.PreciseTimer)
        self.playback_timer.timeout.connect(self.display_latest_frame)
        self.update_playback_timer()
        self.refresh_choices()

    def _terminal(self) -> QPlainTextEdit:
        terminal = QPlainTextEdit()
        terminal.setReadOnly(True)
        terminal.setMaximumBlockCount(2000)
        return terminal

    def start_probe(self, mode: str) -> None:
        topic = self._selected_topic_name()
        if not topic:
            return
        self.stop_inspector_process(mode)
        command = ["ros2", "topic", mode, topic]
        record = self.ctx.process_manager.start(command, f"topic_{mode}", "InspectorPage")
        self._inspector_processes[mode] = record.process_id
        self._append_log(mode, f"$ {record.command_text()}")

    def start_node_info(self) -> None:
        node = self.node.currentText().strip()
        if not node:
            return
        self.stop_inspector_process("node_info")
        record = self.ctx.process_manager.start(["ros2", "node", "info", node], "node_info", "InspectorPage")
        self._inspector_processes["node_info"] = record.process_id
        self._append_log("node_info", f"$ {record.command_text()}")

    def stop_inspector_process(self, role: str) -> None:
        process_id = self._inspector_processes.pop(role, None)
        if process_id:
            self.ctx.process_manager.stop(process_id)
            self._append_log(role, f"[stopped] {process_id}")

    def refresh_output(self) -> None:
        records = {record.process_id: record for record in self.ctx.process_manager.records()}
        for role, process_id in list(self._inspector_processes.items()):
            record = records.get(process_id)
            if not record:
                continue
            self._set_log(role, self._format_record(record))
            if record.status in {"exited", "failed"}:
                self._inspector_processes.pop(role, None)

    def refresh_choices(self) -> None:
        if not self.ctx.last_graph.get("topics") and not self.ctx.last_graph.get("nodes"):
            self.ctx.last_graph = self.ctx.discovery.discover()
        selected_topic = self._selected_topic_name()
        selected_image_topic = self._selected_image_topic_name()
        selected_node = self.ctx.state.selected_nodes[0] if self.ctx.state.selected_nodes else ""
        self._topic_types = {topic.get("name", ""): topic.get("type", "") for topic in self.ctx.last_graph.get("topics", [])}
        self.node.blockSignals(True)
        self.topic.blockSignals(True)
        self.node.clear()
        self.topic.clear()
        self.image_topic.clear()
        self.node.addItems([node.get("name", "") for node in self.ctx.last_graph.get("nodes", [])])
        image_topics: list[dict[str, str]] = []
        for topic in self.ctx.last_graph.get("topics", []):
            name = topic.get("name", "")
            typ = topic.get("type", "")
            self.topic.addItem(f"{name} [{typ}]" if typ else name, name)
            if typ == "sensor_msgs/msg/Image":
                image_topics.append(topic)
                self.image_topic.addItem(f"{name} [{typ}]", name)
        if selected_node:
            index = self.node.findText(selected_node)
            if index >= 0:
                self.node.setCurrentIndex(index)
            else:
                self.node.setEditText(selected_node)
        if selected_topic:
            index = self.topic.findData(selected_topic)
            if index >= 0:
                self.topic.setCurrentIndex(index)
            else:
                self.topic.setEditText(selected_topic)
        if selected_image_topic:
            image_index = self.image_topic.findData(selected_image_topic)
            if image_index >= 0:
                self.image_topic.setCurrentIndex(image_index)
            else:
                self.image_topic.setEditText(selected_image_topic)
        elif image_topics:
            self.image_topic.setCurrentIndex(0)
        self.node.blockSignals(False)
        self.topic.blockSignals(False)
        self.update_topic_type(self.topic.currentText())
        self.update_image_topic_type(self.image_topic.currentText())

    def _selected_topic_name(self) -> str:
        data = self.topic.currentData()
        current_text = self.topic.currentText().strip()
        if data and self.topic.currentIndex() >= 0 and current_text == self.topic.itemText(self.topic.currentIndex()):
            return str(data)
        return current_text.split(" [", 1)[0].strip()

    def update_topic_type(self, _text: str) -> None:
        topic = self._selected_topic_name()
        typ = self._topic_types.get(topic, "")
        self.type_label.setText(f"type: {typ or '-'}")

    def _selected_image_topic_name(self) -> str:
        data = self.image_topic.currentData()
        current_text = self.image_topic.currentText().strip()
        if data and self.image_topic.currentIndex() >= 0 and current_text == self.image_topic.itemText(self.image_topic.currentIndex()):
            return str(data)
        return current_text.split(" [", 1)[0].strip()

    def update_image_topic_type(self, _text: str) -> None:
        topic = self._selected_image_topic_name()
        typ = self._topic_types.get(topic, "")
        self.image_type_label.setText(f"image type: {typ or '-'}")

    def update_selected_node(self, text: str) -> None:
        node = text.strip()
        if node:
            self.ctx.state.selected_nodes = [node]

    def start_image_preview(self) -> None:
        topic = self._selected_image_topic_name()
        topic_type = self._topic_types.get(topic, "")
        if not topic:
            return
        if topic_type and topic_type != "sensor_msgs/msg/Image":
            QMessageBox.warning(self, "Topic type", f"Image preview expects sensor_msgs/msg/Image.\nSelected type: {topic_type}")
            return
        self.stop_image_preview(clear_display=False)
        self._preview_generation += 1
        preview_generation = self._preview_generation
        self._frames = 0
        self._last_display_fps_at = time.time()
        self._last_camera_fps_at = time.time()
        self._max_camera_fps = 0.0
        self._last_source_received = 0
        self.prepare_preview_playback_start()
        self._preview_thread = QThread(self)
        self._preview_worker = RosImagePreviewWorker(topic)
        self._preview_worker.moveToThread(self._preview_thread)
        self._preview_thread.started.connect(self._preview_worker.run)
        self._preview_worker.status_changed.connect(self.handle_preview_status, Qt.QueuedConnection)
        self._preview_worker.finished.connect(self._preview_thread.quit)
        self._preview_worker.finished.connect(self._preview_worker.deleteLater)
        self._preview_thread.finished.connect(self._preview_thread.deleteLater)
        self._preview_thread.finished.connect(lambda generation=preview_generation: self._preview_finished(generation))
        self._latest_frame = None
        self._latest_meta = {}
        self._latest_sequence = 0
        self._displayed_sequence = -1
        self._paused_frame = None
        self._preview_paused = False
        self.pause_preview_button.setText("Pause preview")
        mode = "manual" if self._manual_playback_override else "calibrating"
        self.camera_fps.setText(f"source: - max: - target: {self._effective_playback_fps} {mode}")
        self.update_playback_timer()
        self.playback_timer.start()
        self._preview_thread.start()
        self._append_log("preview", f"$ image-monitor subscribe {topic}")

    def prepare_preview_playback_start(self) -> None:
        self._effective_playback_fps = self.playback_fps.value()
        if self._manual_playback_override:
            self._auto_playback_deadline = 0.0
            return
        self._auto_playback_deadline = time.time() + 2.0

    def stop_image_preview(self, clear_display: bool = True) -> None:
        self._preview_generation += 1
        if self._preview_worker is not None:
            self._preview_worker.stop()
            try:
                self._preview_worker.status_changed.disconnect()
            except Exception:
                pass
        if self._preview_thread is not None:
            self._preview_thread.quit()
            if not self._preview_thread.wait(3000):
                self._append_log("preview", "[warning] image preview thread did not stop within 3 seconds")
        self._preview_worker = None
        self._preview_thread = None
        self.playback_timer.stop()
        if clear_display:
            self.clear_preview_buffer()
        self.preview_status.setText("preview: stopped")
        self._append_log("preview", "[stopped] image preview")

    def _preview_finished(self, generation: int) -> None:
        if generation != self._preview_generation:
            return
        self._preview_worker = None
        self._preview_thread = None
        if self.preview_status.text().startswith("subscribed"):
            self.preview_status.setText("preview: stopped")

    @Slot(str)
    def handle_preview_status(self, text: str) -> None:
        self.preview_status.setText(text)
        self._append_log("preview", text)

    def store_preview_frame(self) -> None:
        if self._preview_worker is None:
            return
        data, meta = self._preview_worker.snapshot()
        if data is None:
            return
        received = int(meta.get("received", 0) or 0)
        if received <= self._latest_sequence:
            return
        frame = image_bytes_to_rgb(data, meta)
        if frame is None:
            self._append_log("preview", f"unsupported image encoding: {meta.get('encoding')}")
            self._latest_sequence = received
            return
        self._latest_frame = frame
        self._latest_meta = meta
        self._latest_sequence = received
        self.update_source_fps()

    def update_source_fps(self) -> None:
        if self._preview_worker is None:
            return
        now = time.time()
        if now - self._last_camera_fps_at >= 1.0:
            received = self._preview_worker.frames_received()
            observed_fps = (received - self._last_source_received) / (now - self._last_camera_fps_at)
            self._max_camera_fps = max(self._max_camera_fps, observed_fps)
            self._update_auto_playback_fps(observed_fps, now)
            mode = "manual" if self._manual_playback_override else "auto"
            self.camera_fps.setText(
                f"source: {observed_fps:.1f} max: {self._max_camera_fps:.1f} target: {self._effective_playback_fps} {mode}"
            )
            if self._latest_meta:
                self.image_meta.setText(
                    "image: "
                    f"{self._latest_meta.get('width')}x{self._latest_meta.get('height')} "
                    f"{self._latest_meta.get('encoding')}"
                )
            self._last_source_received = received
            self._last_camera_fps_at = now

    def display_latest_frame(self) -> None:
        if self._preview_paused:
            return
        self.update_source_fps()
        self.store_preview_frame()
        if self._latest_frame is None:
            return
        if self._displayed_sequence == self._latest_sequence:
            return
        self.update_preview_frame(self._latest_frame)
        self._displayed_sequence = self._latest_sequence

    def clear_preview_buffer(self) -> None:
        self._latest_frame = None
        self._latest_meta = {}
        self._latest_sequence = 0
        self._displayed_sequence = -1
        self._paused_frame = None
        self._preview_paused = False
        self.preview.clear_frame()
        self.image_meta.setText("image: -")
        self.fps.setText("preview fps: 0.0")
        self.camera_fps.setText("source: 0.0 max: 0.0 target: -")
        self.sample.setText("sample: x=- y=- rgb=(-, -, -)")

    def update_preview_frame(self, frame: np.ndarray) -> None:
        self.preview.set_frame(frame)
        self._frames += 1
        now = time.time()
        if now - self._last_display_fps_at >= 1.0:
            self.fps.setText(f"preview fps: {self._frames / (now - self._last_display_fps_at):.1f}")
            self._frames = 0
            self._last_display_fps_at = now

    def set_manual_playback_fps(self, value: int) -> None:
        self._manual_playback_override = True
        self._auto_playback_deadline = 0.0
        self._effective_playback_fps = max(1, value)
        self.update_playback_timer()

    def _update_auto_playback_fps(self, observed_fps: float, now: float) -> None:
        if self._manual_playback_override:
            return
        if not self._auto_playback_deadline or observed_fps <= 0:
            return
        detected_fps = max(1, min(120, int(max(observed_fps, self._max_camera_fps) + 0.999)))
        if detected_fps != self._effective_playback_fps:
            self._effective_playback_fps = detected_fps
            self.update_playback_timer()
        if now >= self._auto_playback_deadline:
            self._auto_playback_deadline = 0.0

    def update_playback_timer(self) -> None:
        interval_ms = max(1, int(1000 / max(self._effective_playback_fps, 1)))
        self.playback_timer.setInterval(interval_ms)

    def toggle_preview_pause(self) -> None:
        if self._preview_paused:
            self._preview_paused = False
            self._paused_frame = None
            self.pause_preview_button.setText("Pause preview")
            self.preview_status.setText("preview: playing")
            return
        frame = self._latest_frame
        if frame is None:
            return
        self._preview_paused = True
        self._paused_frame = frame.copy()
        self.pause_preview_button.setText("Resume preview")
        self.preview_status.setText("preview: paused")
        self.update_preview_frame(self._paused_frame)
        self.update_frame_stats(self._paused_frame)

    def update_sample(self, x: int, y: int, r: int, g: int, b: int) -> None:
        self.sample.setText(f"sample: x={x} y={y} rgb=({r}, {g}, {b})")

    def update_frame_stats(self, frame: np.ndarray) -> None:
        stats = self._frame_stats_text(frame)
        self.frame_stats.setPlainText(stats)
        self._append_log("preview", "[paused] frame stats refreshed from current real image")

    def _frame_stats_text(self, frame: np.ndarray) -> str:
        rgb = frame.astype(np.float32)
        luminance = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
        under = float((luminance <= 5).mean() * 100.0)
        over = float((luminance >= 250).mean() * 100.0)
        means = rgb.mean(axis=(0, 1))
        stds = rgb.std(axis=(0, 1))
        mins = rgb.min(axis=(0, 1))
        maxs = rgb.max(axis=(0, 1))
        h, w, _ = frame.shape
        rows = []
        grid_h = max(h // 3, 1)
        grid_w = max(w // 3, 1)
        for gy in range(3):
            values = []
            for gx in range(3):
                tile = luminance[gy * grid_h : h if gy == 2 else (gy + 1) * grid_h, gx * grid_w : w if gx == 2 else (gx + 1) * grid_w]
                values.append(f"{tile.mean():6.1f}")
            rows.append(" ".join(values))
        return (
            "source: current paused real ROS image frame\n"
            "note: sensor_msgs/Image does not include camera exposure time or white-balance gains; values below are measured from pixels.\n"
            f"shape: {h}x{w} rgb8\n"
            f"luminance mean/std/min/max: {luminance.mean():.2f} / {luminance.std():.2f} / {luminance.min():.0f} / {luminance.max():.0f}\n"
            f"underexposed pixels <=5: {under:.2f}%\n"
            f"overexposed pixels >=250: {over:.2f}%\n"
            f"rgb mean: R={means[0]:.2f} G={means[1]:.2f} B={means[2]:.2f}\n"
            f"rgb std:  R={stds[0]:.2f} G={stds[1]:.2f} B={stds[2]:.2f}\n"
            f"rgb min:  R={mins[0]:.0f} G={mins[1]:.0f} B={mins[2]:.0f}\n"
            f"rgb max:  R={maxs[0]:.0f} G={maxs[1]:.0f} B={maxs[2]:.0f}\n"
            "\n3x3 luminance map:\n"
            + "\n".join(rows)
        )

    def _format_record(self, record: ProcessRecord) -> str:
        lines = [
            f"$ {record.command_text()}",
            f"[{record.status}] pid={record.pid or '-'} id={record.process_id}",
            "",
            *record.stdout_tail,
        ]
        if record.stderr_tail:
            lines.extend(["", "stderr:", *record.stderr_tail])
        return "\n".join(lines)

    def _log_widget(self, role: str) -> QPlainTextEdit:
        return {
            "node_info": self.node_log,
            "echo": self.echo_log,
            "hz": self.hz_log,
            "preview": self.preview_log,
        }[role]

    def _set_log(self, role: str, text: str) -> None:
        widget = self._log_widget(role)
        widget.setPlainText(text)
        widget.verticalScrollBar().setValue(widget.verticalScrollBar().maximum())

    def _append_log(self, role: str, text: str) -> None:
        widget = self._log_widget(role)
        widget.appendPlainText(text)
        widget.verticalScrollBar().setValue(widget.verticalScrollBar().maximum())

    def stop_all_inspector_tasks(self) -> None:
        for role in list(self._inspector_processes):
            self.stop_inspector_process(role)
        self.stop_image_preview()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.stop_all_inspector_tasks()
        super().closeEvent(event)


class ConfigPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self._updating_form = False
        self.editor = QPlainTextEdit()
        self.status = QLabel("")
        self.library = QComboBox()
        self.library.setEditable(False)
        self.config_name = QLineEdit("default_listener")
        self.instruction = QLineEdit()
        self.scene_description = QPlainTextEdit()
        self.scene_description.setMaximumHeight(76)
        self.sample_rate = QSpinBox()
        self.sample_rate.setRange(1, 240)
        self.sample_rate.setSuffix(" Hz")
        self.episode_duration = QSpinBox()
        self.episode_duration.setRange(1, 3600)
        self.episode_duration.setSuffix(" sec")
        self.crop_enabled = QCheckBox("Enable crop")
        self.crop_x = QSpinBox()
        self.crop_y = QSpinBox()
        self.crop_width = QSpinBox()
        self.crop_height = QSpinBox()
        self.resize_enabled = QCheckBox("Enable resize")
        self.resize_width = QSpinBox()
        self.resize_height = QSpinBox()
        for spin in [self.crop_x, self.crop_y, self.crop_width, self.crop_height, self.resize_width, self.resize_height]:
            spin.setRange(0, 8192)
        self.ai_validation_enabled = QCheckBox("Enable AI validation")
        self.ai_base_url = QLineEdit()
        self.ai_model = QLineEdit()
        self.ai_api_key_env = QLineEdit()
        self.ai_prompt = QPlainTextEdit()
        self.ai_prompt.setMaximumHeight(90)
        new_config = QPushButton("New Config")
        load_library = QPushButton("Load From Library")
        save_library = QPushButton("Save To Library")
        delete_library = QPushButton("Delete Library Config")
        generate = QPushButton("Generate Default")
        apply_form = QPushButton("Apply Form To YAML")
        reload_form = QPushButton("Reload Form From YAML")
        validate = QPushButton("Validate")
        save = QPushButton("Save collection_config.yaml")
        new_config.clicked.connect(self.new_config)
        load_library.clicked.connect(self.load_library_config)
        save_library.clicked.connect(self.save_library_config)
        delete_library.clicked.connect(self.delete_library_config)
        generate.clicked.connect(self.generate)
        apply_form.clicked.connect(self.apply_form_to_yaml)
        reload_form.clicked.connect(self.reload_form_from_yaml)
        validate.clicked.connect(self.validate)
        save.clicked.connect(self.save)
        layout = QVBoxLayout(self)
        library_row = QHBoxLayout()
        library_row.addWidget(QLabel("Config library"))
        library_row.addWidget(self.library, 2)
        library_row.addWidget(QLabel("Name"))
        library_row.addWidget(self.config_name, 1)
        library_row.addWidget(new_config)
        library_row.addWidget(load_library)
        library_row.addWidget(save_library)
        library_row.addWidget(delete_library)
        layout.addLayout(library_row)
        row = QHBoxLayout()
        row.addWidget(generate)
        row.addWidget(reload_form)
        row.addWidget(apply_form)
        row.addWidget(validate)
        row.addWidget(save)
        layout.addLayout(row)
        quick_form = QFormLayout()
        quick_form.addRow("Instruction / prompt", self.instruction)
        quick_form.addRow("Scene description", self.scene_description)
        quick_form.addRow("Sample rate", self.sample_rate)
        quick_form.addRow("Episode duration", self.episode_duration)
        crop_row = QHBoxLayout()
        crop_row.addWidget(self.crop_enabled)
        crop_row.addWidget(QLabel("x"))
        crop_row.addWidget(self.crop_x)
        crop_row.addWidget(QLabel("y"))
        crop_row.addWidget(self.crop_y)
        crop_row.addWidget(QLabel("w"))
        crop_row.addWidget(self.crop_width)
        crop_row.addWidget(QLabel("h"))
        crop_row.addWidget(self.crop_height)
        quick_form.addRow("Image crop", crop_row)
        resize_row = QHBoxLayout()
        resize_row.addWidget(self.resize_enabled)
        resize_row.addWidget(QLabel("w"))
        resize_row.addWidget(self.resize_width)
        resize_row.addWidget(QLabel("h"))
        resize_row.addWidget(self.resize_height)
        quick_form.addRow("Image resize", resize_row)
        quick_form.addRow("AI validation", self.ai_validation_enabled)
        quick_form.addRow("AI base URL", self.ai_base_url)
        quick_form.addRow("AI model", self.ai_model)
        quick_form.addRow("AI key env", self.ai_api_key_env)
        quick_form.addRow("Config review prompt", self.ai_prompt)
        layout.addLayout(quick_form)
        layout.addWidget(self.status)
        layout.addWidget(self.editor)
        self.refresh_library()
        self.generate()

    def refresh_library(self) -> None:
        selected = self.library.currentText()
        self.library.clear()
        for path in self.ctx.config_library.list_configs():
            self.library.addItem(path.stem)
        if selected:
            index = self.library.findText(selected)
            if index >= 0:
                self.library.setCurrentIndex(index)

    def generate(self) -> None:
        if not self.ctx.state.collection_config:
            self.ctx.state.collection_config = self.ctx.config_manager.build_default_config(
                self.ctx.state, self.ctx.last_graph.get("topics", [])
            )
        self.editor.setPlainText(self.ctx.config_manager.dumps(self.ctx.state.collection_config))
        self.reload_form_from_yaml()

    def new_config(self) -> None:
        self.ctx.state.collection_config = self.ctx.config_manager.build_default_config(
            self.ctx.state, self.ctx.state.selected_streams or self.ctx.last_graph.get("topics", [])
        )
        self.editor.setPlainText(self.ctx.config_manager.dumps(self.ctx.state.collection_config))
        self.reload_form_from_yaml()
        self.status.setText("New config generated from current selected topics.")

    def load_library_config(self) -> None:
        name = self.library.currentText().strip()
        if not name:
            QMessageBox.warning(self, "Config library", "No saved config selected.")
            return
        text = self.ctx.config_library.load_text(name)
        self.editor.setPlainText(text)
        self.ctx.state.collection_config = self.ctx.config_manager.loads(text)
        self.reload_form_from_yaml()
        self.config_name.setText(name)
        self.status.setText(f"Loaded config_library/{name}.yaml")

    def save_library_config(self) -> None:
        name = self.config_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Config library", "Enter a config name before saving.")
            return
        config = self._current_config()
        text = self.ctx.config_manager.dumps(config)
        path = self.ctx.config_library.save_text(name, text)
        self.refresh_library()
        index = self.library.findText(path.stem)
        if index >= 0:
            self.library.setCurrentIndex(index)
        self.status.setText(f"Saved library config: {path.relative_to(Path(__file__).resolve().parents[3])}")

    def delete_library_config(self) -> None:
        name = self.library.currentText().strip()
        if not name:
            QMessageBox.warning(self, "Config library", "No saved config selected.")
            return
        if QMessageBox.question(self, "Delete config", f"Delete config_library/{name}.yaml?") != QMessageBox.Yes:
            return
        path = self.ctx.config_library.delete(name)
        self.refresh_library()
        self.status.setText(f"Deleted library config: {path.name}")

    def _current_config(self) -> dict:
        config = self.ctx.config_manager.loads(self.editor.toPlainText())
        self.ctx.state.collection_config = config
        return config

    def reload_form_from_yaml(self) -> None:
        try:
            config = self.ctx.config_manager.loads(self.editor.toPlainText())
        except Exception as exc:
            self.status.setText(f"Cannot load form from YAML: {exc}")
            return
        self.ctx.state.collection_config = config
        recording = config.get("recording", {})
        instruction = config.get("instruction", {})
        environment = config.get("environment", {})
        ai_validation = config.get("ai_validation", {})
        first_camera = self._first_camera(config)
        crop = first_camera.get("crop", {}) if first_camera else {}
        resize = first_camera.get("resize", {}) if first_camera else {}

        self._updating_form = True
        self.instruction.setText(str(instruction.get("text", "")))
        self.scene_description.setPlainText(str(environment.get("description", "")))
        self.sample_rate.setValue(int(recording.get("sample_rate_hz") or 10))
        self.episode_duration.setValue(int(recording.get("episode_duration_sec") or 2))
        self.crop_enabled.setChecked(bool(crop.get("enabled", False)))
        self.crop_x.setValue(int(crop.get("x", 0) or 0))
        self.crop_y.setValue(int(crop.get("y", 0) or 0))
        self.crop_width.setValue(int(crop.get("width", 0) or 0))
        self.crop_height.setValue(int(crop.get("height", 0) or 0))
        self.resize_enabled.setChecked(bool(resize.get("enabled", False)))
        self.resize_width.setValue(int(resize.get("width", 224) or 0))
        self.resize_height.setValue(int(resize.get("height", 224) or 0))
        self.ai_validation_enabled.setChecked(bool(ai_validation.get("enabled", False)))
        self.ai_base_url.setText(str(ai_validation.get("base_url", "")))
        self.ai_model.setText(str(ai_validation.get("model", "")))
        self.ai_api_key_env.setText(str(ai_validation.get("api_key_env", "ROBOT_DATA_AI_API_KEY")))
        self.ai_prompt.setPlainText(str(ai_validation.get("config_review_prompt", self._default_ai_prompt())))
        self._updating_form = False

    def apply_form_to_yaml(self) -> None:
        if self._updating_form:
            return
        try:
            config = self.ctx.config_manager.loads(self.editor.toPlainText())
        except Exception as exc:
            QMessageBox.warning(self, "Config YAML", f"Cannot apply form because YAML is invalid:\n{exc}")
            return
        config.setdefault("instruction", {})["text"] = self.instruction.text().strip()
        config.setdefault("environment", {})["description"] = self.scene_description.toPlainText().strip()
        recording = config.setdefault("recording", {})
        recording["sample_rate_hz"] = int(self.sample_rate.value())
        recording["episode_duration_sec"] = int(self.episode_duration.value())
        ai_validation = config.setdefault("ai_validation", {})
        ai_validation["enabled"] = self.ai_validation_enabled.isChecked()
        ai_validation["provider"] = ai_validation.get("provider") or "openai_compatible"
        ai_validation["base_url"] = self.ai_base_url.text().strip()
        ai_validation["api_key_env"] = self.ai_api_key_env.text().strip() or "ROBOT_DATA_AI_API_KEY"
        ai_validation["model"] = self.ai_model.text().strip()
        ai_validation["config_review_prompt"] = self.ai_prompt.toPlainText().strip()

        crop = {
            "enabled": self.crop_enabled.isChecked(),
            "x": int(self.crop_x.value()),
            "y": int(self.crop_y.value()),
            "width": int(self.crop_width.value()),
            "height": int(self.crop_height.value()),
        }
        resize = {
            "enabled": self.resize_enabled.isChecked(),
            "width": int(self.resize_width.value()),
            "height": int(self.resize_height.value()),
        }
        for camera in config.get("cameras", []):
            camera["crop"] = dict(crop)
            camera["resize"] = dict(resize)
        for stream in config.get("streams", []):
            preview = stream.setdefault("preview", {})
            preview["crop"] = dict(crop)
            preview["resize"] = dict(resize)

        self.ctx.state.collection_config = config
        self.editor.setPlainText(self.ctx.config_manager.dumps(config))
        self.status.setText("Applied quick form settings to YAML.")

    def _first_camera(self, config: dict) -> dict:
        cameras = config.get("cameras", [])
        return cameras[0] if cameras and isinstance(cameras[0], dict) else {}

    def _default_ai_prompt(self) -> str:
        return (
            "Check whether this collection_config.yaml is sufficient for robot dataset collection. "
            "Focus on missing robot, camera, stream, instruction, scene, recording, and dataset fields. "
            "Return structured JSON with severity, missing_fields, suspicious_fields, and recommended_changes."
        )

    def validate(self) -> None:
        errors = self.ctx.config_manager.validate(self._current_config())
        self.status.setText("OK" if not errors else "Warnings: " + "; ".join(errors))

    def save(self) -> None:
        config = self._current_config()
        errors = self.ctx.config_manager.validate(config)
        path = self.ctx.state.raw_session_dir / "collection_config.yaml"
        self.ctx.config_manager.save(path, config)
        self.status.setText(f"Saved: {path}" + (f" | warnings: {len(errors)}" if errors else ""))


class RecordingPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.episode_index = 0
        self._recording_thread: QThread | None = None
        self._recording_worker: RosRecordingWorker | None = None
        self._monitor_slots: list[CaptureMonitorSlot] = []
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.streams = QTableWidget(0, 6)
        self.streams.setHorizontalHeaderLabels(["Name", "Modality", "Source", "Topic/Endpoint", "Role", "Runtime"])
        self.monitor_grid = QHBoxLayout()
        self.duration = QSpinBox()
        self.duration.setRange(1, 600)
        self.duration.setValue(2)
        self.duration.setSuffix(" sec")
        refresh = QPushButton("Refresh Listener Plan")
        refresh.clicked.connect(self.refresh_plan)
        record_mock = QPushButton("Simulate Listener Episode")
        record_ros = QPushButton("Record ROS2 Episode")
        record_mock.clicked.connect(self.record_mock)
        record_ros.clicked.connect(self.record_ros)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Listener Recording Console"))
        layout.addWidget(QLabel("This page listens to configured streams and writes dataset episodes. It does not send robot control commands."))
        layout.addWidget(refresh)
        layout.addWidget(self.streams)
        layout.addWidget(QLabel("Capture monitors"))
        layout.addLayout(self.monitor_grid)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Duration"))
        controls.addWidget(self.duration)
        controls.addWidget(record_ros)
        controls.addWidget(record_mock)
        layout.addLayout(controls)
        layout.addWidget(self.log)
        self.refresh_plan()

    def refresh_plan(self) -> None:
        streams = self.ctx.state.collection_config.get("streams", []) if self.ctx.has_config() else []
        runtime = self.ctx.state.collection_config.get("runtime", {}) if self.ctx.has_config() else {}
        mode = runtime.get("mode", "listener_only")
        self.streams.setRowCount(len(streams))
        for row, stream in enumerate(streams):
            values = [
                stream.get("name", ""),
                stream.get("modality", ""),
                stream.get("source", ""),
                stream.get("topic") or stream.get("endpoint", ""),
                stream.get("training_role", ""),
                mode,
            ]
            for col, value in enumerate(values):
                self.streams.setItem(row, col, QTableWidgetItem(str(value)))
        image_streams = [
            stream
            for stream in streams
            if stream.get("message_type") == "sensor_msgs/msg/Image" and stream.get("topic")
        ][:4]
        self.rebuild_capture_monitors(image_streams)

    def record_mock(self) -> None:
        if not self.ctx.has_config():
            QMessageBox.warning(self, "Missing config", "Generate and save collection_config.yaml before recording.")
            return
        path = self.ctx.recorder.record_episode(self.ctx.state.episodes_dir, self.episode_index)
        self.episode_index += 1
        self.log.appendPlainText(f"recorded: {path}")

    def record_ros(self) -> None:
        if not self.ctx.has_config():
            QMessageBox.warning(self, "Missing config", "Generate and save collection_config.yaml before recording.")
            return
        errors = self.preflight_recording()
        if errors:
            message = "Recording preflight failed:\n" + "\n".join(f"- {error}" for error in errors)
            QMessageBox.warning(self, "Recording preflight failed", message)
            self.log.appendPlainText(message)
            return
        if self._recording_thread is not None:
            QMessageBox.warning(self, "Recording active", "A ROS2 recording is already running.")
            return
        self._recording_thread = QThread(self)
        self._recording_worker = RosRecordingWorker(
            self.ctx.ros_recorder,
            self.ctx.state.collection_config,
            self.ctx.state.episodes_dir,
            self.episode_index,
            float(self.duration.value()),
        )
        self._recording_worker.moveToThread(self._recording_thread)
        self._recording_thread.started.connect(self._recording_worker.run)
        self._recording_worker.finished.connect(self.finish_ros_recording)
        self._recording_worker.finished.connect(self._recording_thread.quit)
        self._recording_worker.finished.connect(self._recording_worker.deleteLater)
        self._recording_thread.finished.connect(self._recording_thread.deleteLater)
        self._recording_thread.start()
        self.log.appendPlainText("started ROS2 recording in background")

    def preflight_recording(self) -> list[str]:
        config = self.ctx.state.collection_config
        graph = self.ctx.discovery.discover()
        self.ctx.last_graph = graph
        topic_types = {topic.get("name", ""): topic.get("type", "") for topic in graph.get("topics", [])}
        errors: list[str] = []
        image_streams = [
            stream
            for stream in config.get("streams", [])
            if stream.get("source") == "ros2_topic" and stream.get("message_type") == "sensor_msgs/msg/Image"
        ]
        if not image_streams:
            errors.append("configuration has no sensor_msgs/msg/Image streams")
        for stream in image_streams:
            topic = str(stream.get("topic") or "")
            name = str(stream.get("name") or stream.get("calvin_key") or "image")
            if not topic:
                errors.append(f"{name}: image stream has no topic")
                continue
            error = self._topic_preflight_error(name, topic, "sensor_msgs/msg/Image", topic_types)
            if error:
                errors.append(error)
        state_keys = [
            state_key
            for state_key in config.get("state", {}).get("keys", [])
            if state_key.get("type") == "sensor_msgs/msg/JointState" and state_key.get("source_topic")
        ]
        if not state_keys:
            errors.append("configuration has no JointState state key for robot_obs")
        for state_key in state_keys:
            topic = str(state_key.get("source_topic") or "")
            error = self._topic_preflight_error(
                str(state_key.get("name", "robot_obs")),
                topic,
                "sensor_msgs/msg/JointState",
                topic_types,
            )
            if error:
                errors.append(error)
        return errors

    def _topic_preflight_error(
        self,
        label: str,
        topic: str,
        expected_type: str,
        topic_types: dict[str, str],
    ) -> str | None:
        actual_type = topic_types.get(topic)
        publisher_count: int | None = None
        if actual_type is None:
            info = self.ctx.discovery.topic_info(topic)
            if info is not None:
                actual_type = str(info.get("type") or "")
                publisher_count = int(info.get("publisher_count") or 0)
        if actual_type != expected_type:
            hint = f" current type is {actual_type}" if actual_type else " topic is not currently published"
            return f"{label}: {topic} is not an active {expected_type} topic;{hint}"
        if publisher_count == 0:
            return f"{label}: {topic} has type {expected_type} but no active publishers"
        return None

    @Slot(object, object)
    def finish_ros_recording(self, result: object, error: object) -> None:
        self._recording_thread = None
        self._recording_worker = None
        if error is not None:
            QMessageBox.warning(self, "ROS2 recording failed", str(error))
            self.log.appendPlainText(f"recording failed: {error}")
            return
        if not isinstance(result, RosEpisodeResult):
            self.log.appendPlainText("recording failed: unexpected recorder result")
            return
        self.episode_index += max(result.steps, 1)
        warning_text = f" warnings={len(result.warnings)}" if result.warnings else ""
        self.log.appendPlainText(
            f"recorded real ROS2 CALVIN transitions: {result.path.parent} count={result.steps} streams={', '.join(result.streams)}{warning_text}"
        )

    def rebuild_capture_monitors(self, image_streams: list[dict]) -> None:
        self.stop_all_capture_monitors()
        while self.monitor_grid.count():
            item = self.monitor_grid.takeAt(0)
            widget = item.widget()
            layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif layout is not None:
                self._clear_layout(layout)
        self._monitor_slots = []
        for stream in image_streams:
            slot = self._make_monitor_slot(str(stream.get("name", "image")), str(stream.get("topic", "")))
            self._monitor_slots.append(slot)
            self.monitor_grid.addWidget(slot.widget)
        self.monitor_grid.addStretch(1)

    def _make_monitor_slot(self, stream_name: str, topic: str) -> CaptureMonitorSlot:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        title = QLabel(f"{stream_name}\n{topic}")
        preview = ImagePreviewWidget()
        status = QLabel("monitor: stopped")
        meta = QLabel("image: -")
        fps = QLabel("preview fps: 0.0")
        start = QPushButton("Start capture monitor")
        stop = QPushButton("Stop capture monitor")
        timer = QTimer(self)
        timer.setTimerType(Qt.PreciseTimer)
        timer.setInterval(66)
        slot = CaptureMonitorSlot(
            stream_name=stream_name,
            topic=topic,
            widget=wrapper,
            preview=preview,
            status=status,
            meta=meta,
            fps=fps,
            start_button=start,
            stop_button=stop,
            timer=timer,
            last_fps_at=time.time(),
        )
        start.clicked.connect(lambda _checked=False, item=slot: self.start_capture_monitor(item))
        stop.clicked.connect(lambda _checked=False, item=slot: self.stop_capture_monitor(item))
        timer.timeout.connect(lambda item=slot: self.display_monitor_frame(item))
        layout.addWidget(title)
        layout.addWidget(preview)
        button_row = QHBoxLayout()
        button_row.addWidget(start)
        button_row.addWidget(stop)
        layout.addLayout(button_row)
        layout.addWidget(status)
        layout.addWidget(meta)
        layout.addWidget(fps)
        return slot

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                self._clear_layout(child_layout)

    def start_capture_monitor(self, slot: CaptureMonitorSlot) -> None:
        if not slot.topic:
            QMessageBox.warning(self, "Capture monitor", "Choose an image topic from the listener plan first.")
            return
        self.stop_capture_monitor(slot, clear_display=False)
        slot.thread = QThread(self)
        slot.worker = RosImagePreviewWorker(slot.topic)
        slot.worker.moveToThread(slot.thread)
        slot.thread.started.connect(slot.worker.run)
        slot.worker.status_changed.connect(lambda text, item=slot: self.handle_monitor_status(item, text), Qt.QueuedConnection)
        slot.worker.finished.connect(slot.thread.quit)
        slot.worker.finished.connect(slot.worker.deleteLater)
        slot.thread.finished.connect(slot.thread.deleteLater)
        slot.thread.finished.connect(lambda item=slot: self._monitor_finished(item))
        slot.latest_sequence = 0
        slot.displayed_sequence = -1
        slot.frames = 0
        slot.last_fps_at = time.time()
        slot.timer.start()
        slot.thread.start()
        self.log.appendPlainText(f"capture monitor subscribed: {slot.stream_name} {slot.topic}")

    def stop_capture_monitor(self, slot: CaptureMonitorSlot, clear_display: bool = True) -> None:
        if slot.worker is not None:
            slot.worker.stop()
            try:
                slot.worker.status_changed.disconnect()
            except Exception:
                pass
        if slot.thread is not None:
            slot.thread.quit()
            slot.thread.wait(3000)
        slot.worker = None
        slot.thread = None
        slot.timer.stop()
        slot.status.setText("monitor: stopped")
        if clear_display:
            slot.preview.clear_frame()
            slot.meta.setText("image: -")
            slot.fps.setText("preview fps: 0.0")

    def stop_all_capture_monitors(self) -> None:
        for slot in list(self._monitor_slots):
            self.stop_capture_monitor(slot)

    def _monitor_finished(self, slot: CaptureMonitorSlot) -> None:
        slot.worker = None
        slot.thread = None

    def handle_monitor_status(self, slot: CaptureMonitorSlot, text: str) -> None:
        slot.status.setText(text)

    def display_monitor_frame(self, slot: CaptureMonitorSlot) -> None:
        if slot.worker is None:
            return
        data, meta = slot.worker.snapshot()
        if data is None:
            return
        received = int(meta.get("received", 0) or 0)
        if received <= slot.latest_sequence or received == slot.displayed_sequence:
            return
        frame = image_bytes_to_rgb(data, meta)
        slot.latest_sequence = received
        if frame is None:
            slot.status.setText(f"unsupported image encoding: {meta.get('encoding')}")
            return
        slot.preview.set_frame(frame)
        slot.displayed_sequence = received
        slot.frames += 1
        slot.meta.setText(f"image: {meta.get('width')}x{meta.get('height')} {meta.get('encoding')} frame={received}")
        now = time.time()
        if now - slot.last_fps_at >= 1.0:
            fps = slot.frames / (now - slot.last_fps_at)
            slot.fps.setText(f"preview fps: {fps:.1f}")
            slot.frames = 0
            slot.last_fps_at = now

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.stop_all_capture_monitors()
        super().closeEvent(event)


class ReviewPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self._episode_paths: list[Path] = []
        self._review_rows: list[dict[str, object]] = []
        self._visible_rows: list[dict[str, object]] = []
        self._review_marks: dict[str, str] = {}
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["Episode", "Status", "Mark", "Steps", "Size MB", "Missing", "Quality", "Fields"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.currentCellChanged.connect(self.show_episode_detail)
        self.status_filter = QComboBox()
        self.status_filter.addItems(["all", "ok", "warning", "error"])
        self.status_filter.currentTextChanged.connect(self.apply_review_filter)
        self.mark_select = QComboBox()
        self.mark_select.addItems(["good", "bad", "uncertain", "unmarked"])
        self.summary = QPlainTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setMaximumHeight(110)
        self.layout_table = QTableWidget(0, 6)
        self.layout_table.setHorizontalHeaderLabels(["Area", "Task", "Version", "NPZ", "HDF5", "Manifest"])
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.hdf5_summary = QPlainTextEdit()
        self.hdf5_summary.setReadOnly(True)
        scan = QPushButton("Scan Episodes")
        scan.clicked.connect(self.scan)
        mark_selected = QPushButton("Mark Selected")
        mark_selected.clicked.connect(self.mark_selected)
        export_report = QPushButton("Export quality report")
        export_report.clicked.connect(self.export_quality_report)
        inspect_hdf5 = QPushButton("Inspect Current HDF5")
        inspect_hdf5.clicked.connect(self.inspect_hdf5)
        scan_layout = QPushButton("Scan CALVIN Layout")
        scan_layout.clicked.connect(self.scan_layout)
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        controls.addWidget(scan)
        controls.addWidget(QLabel("Status filter"))
        controls.addWidget(self.status_filter)
        controls.addWidget(QLabel("Manual mark"))
        controls.addWidget(self.mark_select)
        controls.addWidget(mark_selected)
        controls.addWidget(export_report)
        layout.addLayout(controls)
        layout.addWidget(QLabel("Quality Summary"))
        layout.addWidget(self.summary)
        episode_row = QHBoxLayout()
        episode_row.addWidget(self.table, 3)
        detail_col = QVBoxLayout()
        detail_col.addWidget(QLabel("Selected NPZ Details"))
        detail_col.addWidget(self.detail)
        episode_row.addLayout(detail_col, 2)
        layout.addLayout(episode_row)
        layout.addWidget(QLabel("Current HDF5 Overview"))
        layout.addWidget(inspect_hdf5)
        layout.addWidget(self.hdf5_summary)
        layout.addWidget(QLabel("CALVIN Dataset Layout"))
        layout.addWidget(scan_layout)
        layout.addWidget(self.layout_table)

    def scan(self) -> None:
        if not self.ctx.has_raw_episodes():
            QMessageBox.warning(self, "No episodes", "Record at least one episode before review.")
            return
        rows = self.ctx.validator.scan_npz(self.ctx.state.episodes_dir, self.ctx.state.collection_config)
        self._review_rows = rows
        self.apply_review_filter()
        self.update_quality_summary()

    def apply_review_filter(self) -> None:
        status = self.status_filter.currentText()
        rows = self._review_rows
        self._visible_rows = [row for row in rows if status == "all" or row.get("status") == status]
        self._episode_paths = [Path(str(row["path"])) for row in self._visible_rows]
        self.table.setRowCount(len(self._visible_rows))
        for row_idx, row in enumerate(self._visible_rows):
            name = str(row["name"])
            mark = self._review_marks.get(name, "unmarked")
            values = [name, row["status"], mark, row["steps"], row["size_mb"], row["missing"], row["quality"], row["fields"]]
            for col, value in enumerate(values):
                self.table.setItem(row_idx, col, QTableWidgetItem(str(value)))
        if self._visible_rows:
            self.table.selectRow(0)
            self.show_episode_detail(0, 0, -1, -1)
        else:
            self.detail.clear()

    def mark_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._visible_rows):
            return
        name = str(self._visible_rows[row].get("name", ""))
        self._review_marks[name] = self.mark_select.currentText()
        self.apply_review_filter()
        self.update_quality_summary()

    def update_quality_summary(self) -> None:
        report = self.ctx.validator.quality_report(self._review_rows, self._review_marks)
        issues = report["issue_counts"] or {"-": 0}
        marks = report["mark_counts"] or {"-": 0}
        lines = [
            f"total: {report['total']}",
            "status: "
            f"ok={report['by_status']['ok']} warning={report['by_status']['warning']} error={report['by_status']['error']}",
            "marks: " + ", ".join(f"{key}={value}" for key, value in marks.items()),
            "issues: " + ", ".join(f"{key}={value}" for key, value in issues.items()),
        ]
        self.summary.setPlainText("\n".join(lines))

    def export_quality_report(self) -> None:
        if not self._review_rows:
            QMessageBox.warning(self, "Quality report", "Scan episodes before exporting a quality report.")
            return
        report = self.ctx.validator.quality_report(self._review_rows, self._review_marks)
        output = self.ctx.state.raw_session_dir / "quality_report.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.summary.appendPlainText(f"exported: {output}")

    def scan_layout(self) -> None:
        layout = self.ctx.layout_scanner.scan(self.ctx.state.dataset_root)
        rows: list[tuple[str, dict[str, object]]] = []
        rows.extend(("raw_sessions", row) for row in layout.get("raw_sessions", []))
        rows.extend(("merged_calvin", row) for row in layout.get("merged", []))
        if not layout.get("exists"):
            QMessageBox.warning(self, "Dataset root missing", f"Dataset root does not exist locally:\n{self.ctx.state.dataset_root}")
        self.layout_table.setRowCount(len(rows))
        for row_idx, (area, row) in enumerate(rows):
            values = [
                area,
                row.get("task", ""),
                row.get("version", ""),
                row.get("npz_count", ""),
                row.get("has_hdf5", ""),
                row.get("has_manifest", ""),
            ]
            for col, value in enumerate(values):
                self.layout_table.setItem(row_idx, col, QTableWidgetItem(str(value)))

    def show_episode_detail(self, current_row: int, _current_col: int, _previous_row: int, _previous_col: int) -> None:
        if current_row < 0 or current_row >= len(self._episode_paths):
            return
        self.detail.setPlainText(self.ctx.validator.describe_npz(self._episode_paths[current_row], self.ctx.state.collection_config))

    def inspect_hdf5(self) -> None:
        candidates = [path for path in self.ctx.state.conversion_outputs if path.exists()]
        default_path = self.ctx.state.merged_dir / "calvin.hdf5"
        path = candidates[-1] if candidates else default_path
        self.hdf5_summary.setPlainText(self.ctx.validator.describe_hdf5(path))


class ConvertPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.plan_table = QTableWidget(0, 7)
        self.plan_table.setHorizontalHeaderLabels(["Session", "Status", "Episodes", "Annotations", "First", "Last", "Path"])
        dry_run = QPushButton("Build Merge Dry Run")
        dry_run.clicked.connect(self.build_dry_run)
        merge = QPushButton("Merge NPZ Sessions")
        merge.clicked.connect(self.merge_sessions)
        convert = QPushButton("Convert NPZ to HDF5")
        convert.clicked.connect(self.convert)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Merge Dry Run"))
        layout.addWidget(dry_run)
        layout.addWidget(self.plan_table)
        layout.addWidget(merge)
        layout.addWidget(convert)
        layout.addWidget(self.log)

    def build_dry_run(self) -> None:
        raw_root = self.ctx.state.dataset_root / "raw_sessions" / self.ctx.state.task_name / self.ctx.state.version
        rows = self.ctx.merge_planner.build_plan(raw_root)
        if not rows:
            QMessageBox.information(self, "Dry run", f"No raw sessions found under:\n{raw_root}")
        self.plan_table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            values = [
                row["session"],
                row["status"],
                row["episodes"],
                row["has_annotations"],
                row["first_episode"],
                row["last_episode"],
                row["path"],
            ]
            for col, value in enumerate(values):
                self.plan_table.setItem(row_idx, col, QTableWidgetItem(str(value)))

    def merge_sessions(self) -> None:
        raw_root = self.ctx.state.dataset_root / "raw_sessions" / self.ctx.state.task_name / self.ctx.state.version
        try:
            manifest = self.ctx.session_merger.merge(raw_root, self.ctx.state.merged_dir)
        except Exception as exc:
            QMessageBox.warning(self, "Merge failed", str(exc))
            self.log.appendPlainText(f"merge failed: {exc}")
            return
        self.log.appendPlainText(
            "merged sessions: "
            f"{manifest['session_count']} session(s), {manifest['episode_count']} episode(s) -> {manifest['merged_training_dir']}"
        )

    def convert(self) -> None:
        if not self.ctx.has_raw_episodes():
            QMessageBox.warning(self, "No episodes", "Record or import raw NPZ episodes before conversion.")
            return
        config_yaml = self.ctx.config_manager.dumps(self.ctx.state.collection_config or {})
        output = self.ctx.state.merged_dir / "calvin.hdf5"
        path = self.ctx.converter.convert(self.ctx.state.episodes_dir, output, config_yaml)
        self.ctx.state.conversion_outputs.append(path)
        self.log.appendPlainText(f"converted: {path}")


class UploadPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.local = QLineEdit(str(ctx.state.merged_dir))
        self.profile_name = QLineEdit("lab_server")
        self.profile_select = QComboBox()
        self.lan_host = QLineEdit("")
        self.wan_host = QLineEdit("")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(22)
        self.username = QLineEdit("")
        self.password = QLineEdit("")
        self.password.setEchoMode(QLineEdit.Password)
        self.key_path = QLineEdit("")
        self.auth_hint = QLabel("auth: agent_or_default_key")
        self.remote_path = QLineEdit("/data/dataset")
        self.path_breadcrumbs = QHBoxLayout()
        self.new_folder = QLineEdit("")
        self.remote_files = QTableWidget(0, 3)
        self.remote_files.setHorizontalHeaderLabels(["Name", "Type", "Size"])
        self.remote_files.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.remote_files.setSelectionMode(QAbstractItemView.SingleSelection)
        self.remote_files.currentCellChanged.connect(self.select_remote_row)
        self.remote_files.cellDoubleClicked.connect(self.open_remote_row)
        self.upload_progress = QLabel("upload progress: -")
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        build_manifest = QPushButton("Build upload manifest")
        verify_manifest = QPushButton("Verify upload manifest")
        save_profile = QPushButton("Save server profile")
        load_profile = QPushButton("Load server profile")
        delete_profile = QPushButton("Delete server profile")
        test_ssh = QPushButton("Connect and list")
        parent_dir = QPushButton("Up")
        select_dir = QPushButton("Use current directory")
        mkdir = QPushButton("Create folder")
        check_space = QPushButton("Check remote space")
        upload = QPushButton("Start rsync upload")
        refresh_upload_progress = QPushButton("Refresh upload progress")
        remote_verify = QPushButton("Verify remote manifest")
        self.password.textChanged.connect(self.update_auth_hint)
        self.key_path.textChanged.connect(self.update_auth_hint)
        build_manifest.clicked.connect(self.build_manifest)
        verify_manifest.clicked.connect(self.verify_manifest)
        save_profile.clicked.connect(self.save_server_profile)
        load_profile.clicked.connect(self.load_server_profile)
        delete_profile.clicked.connect(self.delete_server_profile)
        test_ssh.clicked.connect(self.test_ssh)
        parent_dir.clicked.connect(self.go_parent_dir)
        select_dir.clicked.connect(self.select_current_remote_dir)
        mkdir.clicked.connect(self.create_remote_folder)
        check_space.clicked.connect(self.check_remote_space)
        upload.clicked.connect(self.upload)
        refresh_upload_progress.clicked.connect(self.refresh_upload_progress)
        remote_verify.clicked.connect(self.verify_remote)
        layout = QFormLayout(self)
        layout.addRow("Local path", self.local)
        profile_row = QHBoxLayout()
        profile_row.addWidget(self.profile_select, 2)
        profile_row.addWidget(QLabel("Name"))
        profile_row.addWidget(self.profile_name, 1)
        profile_row.addWidget(load_profile)
        profile_row.addWidget(save_profile)
        profile_row.addWidget(delete_profile)
        layout.addRow("Server profile", profile_row)
        layout.addRow("Internal IP / Host", self.lan_host)
        layout.addRow("Public IP / Host", self.wan_host)
        layout.addRow("Port", self.port)
        layout.addRow("Username", self.username)
        layout.addRow("Password", self.password)
        layout.addRow("Private key path", self.key_path)
        layout.addRow("Authentication", self.auth_hint)
        self.remote_path.textChanged.connect(self.update_remote_breadcrumbs)
        layout.addRow("Remote directory", self.remote_path)
        layout.addRow("Path", self.path_breadcrumbs)
        remote_buttons = QHBoxLayout()
        remote_buttons.addWidget(test_ssh)
        remote_buttons.addWidget(parent_dir)
        remote_buttons.addWidget(select_dir)
        layout.addRow(remote_buttons)
        mkdir_row = QHBoxLayout()
        mkdir_row.addWidget(self.new_folder)
        mkdir_row.addWidget(mkdir)
        layout.addRow("New folder", mkdir_row)
        layout.addRow(self.remote_files)
        layout.addRow(build_manifest)
        layout.addRow(verify_manifest)
        layout.addRow(check_space)
        layout.addRow(upload)
        layout.addRow(refresh_upload_progress)
        layout.addRow("Upload progress", self.upload_progress)
        layout.addRow(remote_verify)
        layout.addRow(self.report)
        self.upload_progress_timer = QTimer(self)
        self.upload_progress_timer.timeout.connect(self.refresh_upload_progress)
        self.upload_progress_timer.start(1500)
        self.refresh_server_profiles()
        self.update_remote_breadcrumbs()

    def _local_path(self) -> Path:
        return Path(self.local.text()).expanduser()

    def _validate_local_path(self) -> Path | None:
        local_path = self._local_path()
        if not local_path.exists():
            QMessageBox.warning(self, "Missing local path", f"Local path does not exist:\n{local_path}")
            return None
        if not local_path.is_dir():
            QMessageBox.warning(self, "Local path", f"Local path must be a directory:\n{local_path}")
            return None
        return local_path

    def build_manifest(self) -> Path | None:
        local_path = self._validate_local_path()
        if not local_path:
            return None
        manifest = UploadManifest()
        summary = manifest.build(local_path)
        manifest_path = manifest.write(local_path, summary)
        self.report.setPlainText(
            f"manifest: {manifest_path}\n"
            f"files: {summary['file_count']}\n"
            f"total_size_mb: {summary['total_size_bytes'] / 1024 / 1024:.3f}"
        )
        return manifest_path

    def verify_manifest(self) -> None:
        local_path = self._validate_local_path()
        if not local_path:
            return
        manifest_path = local_path / MANIFEST_NAME
        if not manifest_path.exists():
            QMessageBox.warning(self, "Manifest missing", f"Build {MANIFEST_NAME} before verification.")
            return
        result = UploadManifest().verify(manifest_path)
        self.report.setPlainText(
            f"manifest: {manifest_path}\n"
            f"ok: {result['ok']}\n"
            f"checked: {result['checked']}\n"
            f"missing: {len(result['missing'])}\n"
            f"mismatched: {len(result['mismatched'])}"
        )

    def _local_size_bytes(self, local_path: Path) -> int:
        return sum(path.stat().st_size for path in local_path.rglob("*") if path.is_file())

    def _connection(self) -> SshConnection | None:
        host = self.lan_host.text().strip() or self.wan_host.text().strip()
        if not host:
            QMessageBox.warning(self, "SSH server", "Enter internal IP/host or public IP/host.")
            return None
        username = self.username.text().strip()
        if not username:
            QMessageBox.warning(self, "SSH username", "Enter the SSH login username.")
            return None
        remote_path = self.remote_path.text().strip() or "/"
        return SshConnection(
            host=host,
            port=int(self.port.value()),
            username=username,
            remote_path=remote_path,
            password=self.password.text(),
            key_path=self.key_path.text().strip(),
        )

    def refresh_server_profiles(self) -> None:
        current = self.profile_select.currentText()
        self.profile_select.clear()
        for profile in self.ctx.ssh_profiles.list_profiles():
            self.profile_select.addItem(profile.name)
        if current:
            index = self.profile_select.findText(current)
            if index >= 0:
                self.profile_select.setCurrentIndex(index)

    def _current_profile(self) -> SshProfile:
        return SshProfile(
            name=self.profile_name.text().strip() or self.profile_select.currentText().strip(),
            lan_host=self.lan_host.text().strip(),
            wan_host=self.wan_host.text().strip(),
            port=int(self.port.value()),
            username=self.username.text().strip(),
            key_path=self.key_path.text().strip(),
            remote_path=self.remote_path.text().strip() or "/data/dataset",
        )

    def save_server_profile(self) -> None:
        try:
            profile = self._current_profile()
            self.ctx.ssh_profiles.save_profile(profile)
        except Exception as exc:
            QMessageBox.warning(self, "Server profile", str(exc))
            return
        self.refresh_server_profiles()
        index = self.profile_select.findText(profile.name)
        if index >= 0:
            self.profile_select.setCurrentIndex(index)
        self.report.setPlainText(f"saved server profile: {profile.name}\npassword was not saved")

    def load_server_profile(self) -> None:
        name = self.profile_select.currentText().strip() or self.profile_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Server profile", "No server profile selected.")
            return
        try:
            profile = self.ctx.ssh_profiles.load_profile(name)
        except Exception as exc:
            QMessageBox.warning(self, "Server profile", str(exc))
            return
        self.profile_name.setText(profile.name)
        self.lan_host.setText(profile.lan_host)
        self.wan_host.setText(profile.wan_host)
        self.port.setValue(profile.port)
        self.username.setText(profile.username)
        self.key_path.setText(profile.key_path)
        self.remote_path.setText(profile.remote_path)
        self.password.clear()
        self.update_auth_hint()
        self.report.setPlainText(f"loaded server profile: {profile.name}\npassword was not loaded")

    def delete_server_profile(self) -> None:
        name = self.profile_select.currentText().strip()
        if not name:
            QMessageBox.warning(self, "Server profile", "No server profile selected.")
            return
        if QMessageBox.question(self, "Delete server profile", f"Delete SSH server profile '{name}'?") != QMessageBox.Yes:
            return
        self.ctx.ssh_profiles.delete_profile(name)
        self.refresh_server_profiles()
        self.report.setPlainText(f"deleted server profile: {name}")

    def update_auth_hint(self) -> None:
        if self.key_path.text().strip():
            mode = "key"
        elif self.password.text():
            mode = "password"
        else:
            mode = "agent_or_default_key"
        self.auth_hint.setText(f"auth: {mode}")

    def _selected_remote_name(self) -> str | None:
        row = self.remote_files.currentRow()
        if row < 0:
            return None
        item = self.remote_files.item(row, 0)
        return item.text() if item else None

    def _remote_path_parts(self) -> list[tuple[str, str]]:
        raw = self.remote_path.text().strip() or "/"
        absolute = raw.startswith("/")
        parts = [part for part in raw.split("/") if part]
        crumbs: list[tuple[str, str]] = [("/", "/")] if absolute else []
        current = "" if absolute else "."
        for part in parts:
            current = f"{current.rstrip('/')}/{part}" if current not in {"", "."} else (f"/{part}" if absolute else part)
            crumbs.append((part, current))
        if not crumbs:
            crumbs.append(("/", "/"))
        return crumbs

    def update_remote_breadcrumbs(self) -> None:
        while self.path_breadcrumbs.count():
            item = self.path_breadcrumbs.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for label, target in self._remote_path_parts():
            button = QPushButton(label)
            button.setToolTip(target)
            button.clicked.connect(lambda _checked=False, path=target: self.jump_remote_path(path))
            self.path_breadcrumbs.addWidget(button)
        self.path_breadcrumbs.addStretch(1)

    def jump_remote_path(self, path: str) -> None:
        self.remote_path.setText(path or "/")
        self.refresh_remote_listing()

    def _set_remote_listing(self, entries: list[dict[str, object]]) -> None:
        self.remote_files.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            values = [
                entry.get("name", ""),
                "dir" if entry.get("is_dir") else "file",
                entry.get("size", ""),
            ]
            for col, value in enumerate(values):
                self.remote_files.setItem(row, col, QTableWidgetItem(str(value)))

    def refresh_remote_listing(self) -> None:
        connection = self._connection()
        if connection is None:
            return
        try:
            entries = SshUploader(self.ctx.process_manager).list_remote_dir(connection)
        except Exception as exc:
            QMessageBox.warning(self, "SSH list failed", str(exc))
            self.report.setPlainText(f"SSH list failed: {exc}\nauth mode: {connection.auth_mode}")
            return
        self._set_remote_listing(entries)
        self.update_remote_breadcrumbs()
        self.report.setPlainText(
            f"connected: {connection.host_with_user}:{connection.port}\n"
            f"auth mode: {connection.auth_mode}\n"
            f"remote: {connection.remote_path}\n"
            f"entries: {len(entries)}"
        )

    def select_remote_row(self, current_row: int, _current_col: int, _previous_row: int, _previous_col: int) -> None:
        if current_row < 0:
            return
        name = self._selected_remote_name()
        typ = self.remote_files.item(current_row, 1).text() if self.remote_files.item(current_row, 1) else ""
        if name:
            self.report.setPlainText(f"selected remote {typ}: {name}")

    def open_remote_row(self, row: int, _col: int) -> None:
        item = self.remote_files.item(row, 0)
        typ = self.remote_files.item(row, 1)
        if not item or not typ or typ.text() != "dir":
            return
        base = self.remote_path.text().rstrip("/")
        self.remote_path.setText(f"{base}/{item.text()}" if base else f"/{item.text()}")
        self.refresh_remote_listing()

    def go_parent_dir(self) -> None:
        path = PurePosixPath(self.remote_path.text().strip() or "/")
        parent = str(path.parent)
        self.remote_path.setText(parent if parent else "/")
        self.refresh_remote_listing()

    def select_current_remote_dir(self) -> None:
        connection = self._connection()
        if connection is None:
            return
        self.report.setPlainText(f"upload target selected: {connection.target}")

    def create_remote_folder(self) -> None:
        connection = self._connection()
        if connection is None:
            return
        try:
            created = SshUploader(self.ctx.process_manager).mkdir_remote(connection, self.new_folder.text())
        except Exception as exc:
            QMessageBox.warning(self, "Create folder failed", str(exc))
            return
        self.remote_path.setText(created)
        self.new_folder.clear()
        self.refresh_remote_listing()

    def check_remote_space(self) -> None:
        local_path = self._validate_local_path()
        if not local_path:
            return
        connection = self._connection()
        if connection is None:
            return
        local_size = self._local_size_bytes(local_path)
        try:
            remote = SshUploader(self.ctx.process_manager).remote_space(connection)
        except Exception as exc:
            QMessageBox.warning(self, "Remote space", str(exc))
            return
        available = int(remote.get("available_bytes", 0))
        enough = available >= local_size
        self.report.setPlainText(
            f"local path: {local_path}\n"
            f"local size: {self._format_bytes(local_size)}\n"
            f"remote path: {connection.remote_path}\n"
            f"remote available: {self._format_bytes(available)}\n"
            f"remote free: {self._format_bytes(int(remote.get('free_bytes', 0)))}\n"
            f"remote total: {self._format_bytes(int(remote.get('total_bytes', 0)))}\n"
            f"enough space: {enough}"
        )

    def upload(self) -> None:
        local_path = self._validate_local_path()
        if not local_path:
            return
        if not self.ctx.has_converted_dataset() and local_path == self.ctx.state.merged_dir:
            QMessageBox.warning(self, "No converted dataset", "Convert NPZ to HDF5 before uploading the merged directory.")
            return
        connection = self._connection()
        if connection is None:
            return
        manifest_path = self.build_manifest()
        if manifest_path is None:
            return
        uploader = SshUploader(self.ctx.process_manager)
        record = uploader.upload_connection_with_rsync(local_path, connection)
        self.upload_progress.setText(f"upload progress: started {record.process_id}")
        self.report.setPlainText(f"started rsync upload: {record.process_id}\nOpen Process for full logs.")

    def refresh_upload_progress(self) -> None:
        upload_records = [record for record in self.ctx.process_manager.records() if record.type == "uploader"]
        if not upload_records:
            self.upload_progress.setText("upload progress: -")
            return
        record = sorted(upload_records, key=lambda item: item.started_at)[-1]
        summary = self._parse_rsync_progress(record.stdout_tail + record.stderr_tail)
        parts = [f"upload progress: {record.status}"]
        if summary.get("file"):
            parts.append(f"file={summary['file']}")
        if summary.get("percent") is not None:
            parts.append(f"{summary['percent']}%")
        if summary.get("speed"):
            parts.append(f"speed={summary['speed']}")
        if summary.get("eta"):
            parts.append(f"eta={summary['eta']}")
        parts.append(f"id={record.process_id}")
        self.upload_progress.setText(" | ".join(parts))

    def _parse_rsync_progress(self, lines: list[str]) -> dict[str, object]:
        summary: dict[str, object] = {"file": "", "percent": None, "speed": "", "eta": ""}
        progress_pattern = re.compile(r"(?P<percent>\d{1,3})%\s+(?P<speed>\S+/s)\s+(?P<eta>\S+)")
        for line in lines:
            text = line.strip()
            if not text:
                continue
            progress = progress_pattern.search(text)
            if progress:
                summary["percent"] = min(int(progress.group("percent")), 100)
                summary["speed"] = progress.group("speed")
                summary["eta"] = progress.group("eta")
                continue
            if not text.startswith(("sending ", "sent ", "total size", "receiving ", "created directory")):
                summary["file"] = text
        return summary

    def test_ssh(self) -> None:
        self.refresh_remote_listing()

    def verify_remote(self) -> None:
        local_path = self._validate_local_path()
        if not local_path:
            return
        manifest_path = local_path / MANIFEST_NAME
        if not manifest_path.exists():
            QMessageBox.warning(self, "Manifest missing", f"Build {MANIFEST_NAME} before remote verification.")
            return
        connection = self._connection()
        if connection is None:
            return
        try:
            record = SshUploader(self.ctx.process_manager).verify_remote_manifest(
                manifest_path,
                connection.target,
                connection.port,
                connection.key_path,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Remote verify", str(exc))
            return
        self.report.setPlainText(f"started remote manifest verification: {record.process_id}\nOpen Process to inspect details.")

    def _format_bytes(self, size: int) -> str:
        value = float(size)
        for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
            if value < 1024 or unit == "PB":
                return f"{value:.2f} {unit}"
            value /= 1024

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.upload_progress_timer.stop()
        super().closeEvent(event)


class ProcessPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self._records_by_id: dict[str, ProcessRecord] = {}
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["ID", "Type", "PID", "Status", "Owner", "Command", "Tail"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.currentCellChanged.connect(self.show_selected_log)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        stop = QPushButton("Stop Selected")
        stop_all = QPushButton("Stop All")
        refresh = QPushButton("Refresh")
        stop.clicked.connect(self.stop_selected)
        stop_all.clicked.connect(self.stop_all)
        refresh.clicked.connect(self.refresh)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(refresh)
        row.addWidget(stop)
        row.addWidget(stop_all)
        layout.addLayout(row)
        layout.addWidget(self.table)
        layout.addWidget(QLabel("Selected Process Log"))
        layout.addWidget(self.log)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1500)

    def refresh(self) -> None:
        records = self.ctx.process_manager.records()
        self._records_by_id = {record.process_id: record for record in records}
        selected_id = self._selected_process_id()
        self.table.setRowCount(len(records))
        for row, record in enumerate(records):
            tail = "\n".join((record.stdout_tail + record.stderr_tail)[-3:])
            values = [record.process_id, record.type, record.pid or "", record.status, record.owner_page, record.command_text(), tail]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(str(value)))
            if record.process_id == selected_id:
                self.table.selectRow(row)
        self.show_selected_log(self.table.currentRow(), 0, -1, -1)

    def _selected_process_id(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.text() if item else None

    def show_selected_log(self, current_row: int, _current_col: int, _previous_row: int, _previous_col: int) -> None:
        if current_row < 0:
            self.log.clear()
            return
        item = self.table.item(current_row, 0)
        if not item:
            self.log.clear()
            return
        record = self._records_by_id.get(item.text())
        if not record:
            self.log.clear()
            return
        lines = [
            f"id: {record.process_id}",
            f"type: {record.type}",
            f"pid: {record.pid or '-'}",
            f"status: {record.status}",
            f"owner: {record.owner_page}",
            f"command: {record.command_text()}",
            "",
            "stdout tail:",
            *(record.stdout_tail or ["-"]),
            "",
            "stderr tail:",
            *(record.stderr_tail or ["-"]),
        ]
        self.log.setPlainText("\n".join(lines))

    def stop_selected(self) -> None:
        process_id = self._selected_process_id()
        if not process_id:
            return
        if QMessageBox.question(self, "Stop process", f"Stop process {process_id}?") != QMessageBox.Yes:
            return
        self.ctx.process_manager.stop(process_id)

    def stop_all(self) -> None:
        records = [record for record in self.ctx.process_manager.records() if record.status in {"running", "stopping"}]
        if not records:
            return
        if QMessageBox.question(self, "Stop all processes", f"Stop {len(records)} running process(es)?") != QMessageBox.Yes:
            return
        self.ctx.process_manager.stop_all()


class SettingsPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.language = QComboBox()
        self.language.addItems(["中文", "English"])
        self.language.setCurrentText("中文" if ctx.state.language == "zh" else "English")
        self.language.currentTextChanged.connect(self.set_language)
        self.switch_language = QPushButton("Switch / 切换")
        self.switch_language.clicked.connect(self.toggle_language)
        self.ai_enabled = QComboBox()
        self.ai_enabled.addItems(["disabled", "enabled"])
        self.ai_base = QLineEdit("")
        self.ai_model = QLineEdit("")
        self.env_note = QLabel("Python env: project-local .venv or .conda-env")
        layout = QFormLayout(self)
        language_row = QHBoxLayout()
        language_row.addWidget(self.language)
        language_row.addWidget(self.switch_language)
        layout.addRow("Language / 语言", language_row)
        layout.addRow("Dependency env", self.env_note)
        layout.addRow("AI validation", self.ai_enabled)
        layout.addRow("OpenAI-compatible base URL", self.ai_base)
        layout.addRow("Model", self.ai_model)
        self.note = QTextEdit()
        self.note.setReadOnly(True)
        self.note.setPlainText("API keys should be provided through environment variables, not saved in project YAML.")
        layout.addRow(self.note)
        self.ctx.language_changed.connect(self.retranslate)
        self.retranslate(self.ctx.state.language)

    def set_language(self, text: str) -> None:
        self.ctx.set_language("en" if text == "English" else "zh")

    def toggle_language(self) -> None:
        self.language.setCurrentText("English" if self.ctx.state.language == "zh" else "中文")

    @Slot(str)
    def retranslate(self, language: str) -> None:
        apply_i18n(self, language)
        if language == "en":
            self.note.setPlainText("API keys should be provided through environment variables, not saved in project YAML.")
        else:
            self.note.setPlainText("API key 应通过环境变量提供，不保存到项目 YAML 中。")
