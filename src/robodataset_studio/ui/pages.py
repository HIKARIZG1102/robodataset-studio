from __future__ import annotations

from pathlib import Path

import threading
import time
from uuid import uuid4

import numpy as np
from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from robodataset_studio.core.config_manager import ConfigManager
from robodataset_studio.core.environment import EnvironmentService
from robodataset_studio.core.models import ProcessRecord, ProjectState
from robodataset_studio.core.process_manager import ProcessManager
from robodataset_studio.dataset.converter import Hdf5Converter
from robodataset_studio.dataset.layout import CalvinLayoutScanner
from robodataset_studio.dataset.merge_plan import CalvinMergePlanner
from robodataset_studio.dataset.recorder import MockRecorder
from robodataset_studio.dataset.validator import DatasetValidator
from robodataset_studio.ros.graph_discovery import RosGraphDiscovery
from robodataset_studio.upload.manifest import MANIFEST_NAME, UploadManifest
from robodataset_studio.upload.ssh_uploader import SshUploader


class AppContext:
    def __init__(self) -> None:
        self.state = ProjectState()
        self.config_manager = ConfigManager()
        self.process_manager = ProcessManager()
        self.environment = EnvironmentService()
        self.discovery = RosGraphDiscovery()
        self.recorder = MockRecorder()
        self.validator = DatasetValidator()
        self.converter = Hdf5Converter()
        self.layout_scanner = CalvinLayoutScanner()
        self.merge_planner = CalvinMergePlanner()
        self.last_graph: dict[str, list[dict[str, str]]] = {"nodes": [], "topics": [], "services": []}

    def has_config(self) -> bool:
        return bool(self.state.collection_config)

    def has_raw_episodes(self) -> bool:
        return self.state.episodes_dir.exists() and any(self.state.episodes_dir.glob("episode_*.npz"))

    def has_converted_dataset(self) -> bool:
        return any(path.exists() for path in self.state.conversion_outputs) or (self.state.merged_dir / "calvin.hdf5").exists()


class ImagePreviewLabel(QLabel):
    sampled = Signal(int, int, int, int, int)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(448, 448)
        self.setAlignment(Qt.AlignCenter)
        self.setMouseTracking(True)
        self._frame: np.ndarray | None = None
        self._display_size = (448, 448)

    def set_frame(self, frame: np.ndarray) -> None:
        self._frame = frame
        h, w, _ = frame.shape
        image = QImage(frame.data, w, h, 3 * w, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(image).scaled(self.width(), self.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._display_size = (pixmap.width(), pixmap.height())
        self.setPixmap(pixmap)

    def clear_frame(self) -> None:
        self._frame = None
        self._display_size = (0, 0)
        self.setPixmap(QPixmap())

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._frame is None or self.pixmap() is None:
            return
        frame_h, frame_w, _ = self._frame.shape
        pix_w, pix_h = self._display_size
        x0 = (self.width() - pix_w) / 2
        y0 = (self.height() - pix_h) / 2
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
        self.latest_frame: np.ndarray | None = None
        self.latest_meta: dict[str, object] = {}

    @Slot()
    def run(self) -> None:
        context = None
        executor = None
        node = None
        try:
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
                frame = self._image_to_rgb(msg)
                if frame is not None:
                    with self._lock:
                        self._received += 1
                        self.latest_frame = frame
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
                            f"receiving: {self.topic} frames={self.frames_received()} encoding={msg.encoding} size={msg.width}x{msg.height}"
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

    def snapshot(self) -> tuple[np.ndarray | None, dict[str, object]]:
        with self._lock:
            return self.latest_frame, dict(self.latest_meta)

    def frames_received(self) -> int:
        with self._lock:
            return self._received

    def clear_buffer(self) -> None:
        with self._lock:
            self.latest_frame = None
            self.latest_meta = {}

    def _image_to_rgb(self, msg) -> np.ndarray | None:
        encoding = msg.encoding.lower()
        height = int(msg.height)
        width = int(msg.width)
        step = int(msg.step)
        raw = np.frombuffer(bytes(msg.data), dtype=np.uint8)
        if height <= 0 or width <= 0 or step <= 0:
            return None
        rows = raw.reshape((height, step))
        if encoding in {"rgb8", "bgr8"}:
            frame = rows[:, : width * 3].reshape((height, width, 3)).copy()
            if encoding == "bgr8":
                frame = frame[:, :, ::-1].copy()
            return frame
        if encoding in {"rgba8", "bgra8"}:
            frame = rows[:, : width * 4].reshape((height, width, 4))[:, :, :3].copy()
            if encoding == "bgra8":
                frame = frame[:, :, ::-1].copy()
            return frame
        if encoding in {"mono8", "8uc1"}:
            gray = rows[:, :width].reshape((height, width)).copy()
            return np.repeat(gray[:, :, None], 3, axis=2)
        if encoding in {"mono16", "16uc1", "16uc1; compresseddepth"}:
            depth = np.frombuffer(bytes(msg.data), dtype=np.uint16).reshape((height, step // 2))[:, :width]
            max_value = int(depth.max()) or 1
            gray = np.clip(depth.astype(np.float32) * 255.0 / max_value, 0, 255).astype(np.uint8)
            return np.repeat(gray[:, :, None], 3, axis=2)
        if encoding in {"32fc1"}:
            depth = np.frombuffer(bytes(msg.data), dtype=np.float32).reshape((height, step // 4))[:, :width]
            finite = depth[np.isfinite(depth)]
            if finite.size == 0:
                return np.zeros((height, width, 3), dtype=np.uint8)
            low = float(np.percentile(finite, 1))
            high = float(np.percentile(finite, 99))
            if high <= low:
                high = low + 1.0
            gray = np.clip((depth - low) * 255.0 / (high - low), 0, 255)
            gray = np.nan_to_num(gray, nan=0.0, posinf=255.0, neginf=0.0).astype(np.uint8)
            return np.repeat(gray[:, :, None], 3, axis=2)
        self.status_changed.emit(f"unsupported encoding: {msg.encoding}")
        return None


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
        self.topics = QTableWidget(0, 2)
        self.topics.setHorizontalHeaderLabels(["Topic", "Type"])
        self.topics.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.topics.currentCellChanged.connect(self.select_topic)
        refresh = QPushButton("Discover ROS2 Graph")
        refresh.clicked.connect(self.refresh)
        generate = QPushButton("Generate Config From Topics")
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
        self.nodes.clear()
        for node in graph.get("nodes", []):
            self.nodes.addItem(node["name"])
        topics = graph.get("topics", [])
        self.topics.setRowCount(len(topics))
        for row, topic in enumerate(topics):
            self.topics.setItem(row, 0, QTableWidgetItem(topic.get("name", "")))
            self.topics.setItem(row, 1, QTableWidgetItem(topic.get("type", "")))
        if graph.get("nodes"):
            self.nodes.setCurrentRow(0)
        if topics:
            self.topics.selectRow(0)

    def generate_config(self) -> None:
        self.ctx.state.collection_config = self.ctx.config_manager.build_default_config(
            self.ctx.state, self.ctx.last_graph.get("topics", [])
        )
        QMessageBox.information(self, "Config", "collection_config.yaml generated in memory. Open Config page to edit/save.")

    def select_node(self, row: int) -> None:
        nodes = self.ctx.last_graph.get("nodes", [])
        if 0 <= row < len(nodes):
            self.ctx.state.selected_nodes = [nodes[row].get("name", "")]

    def select_topic(self, row: int, _current_col: int, _previous_row: int, _previous_col: int) -> None:
        topics = self.ctx.last_graph.get("topics", [])
        if 0 <= row < len(topics):
            self.ctx.state.selected_streams = [topics[row]]


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
        start_preview = QPushButton("Start image preview")
        stop_preview = QPushButton("Stop image preview")
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
        self.preview = ImagePreviewLabel()
        self.preview.sampled.connect(self.update_sample)
        self.sample = QLabel("sample: x=- y=- rgb=(-, -, -)")
        self.fps = QLabel("preview fps: 0.0")
        self.camera_fps = QLabel("camera fps: 0.0")
        self.playback_fps = QSpinBox()
        self.playback_fps.setRange(1, 480)
        self.playback_fps.setValue(30)
        self.playback_fps.setSuffix(" fps")
        self.playback_fps.valueChanged.connect(self.update_playback_timer)
        self._frames = 0
        self._received_frames = 0
        self._last_display_fps_at = time.time()
        self._last_camera_fps_at = time.time()
        self._max_camera_fps = 0.0
        self.playback_fps.setMinimum(1)
        self._latest_frame: np.ndarray | None = None
        self._latest_meta: dict[str, object] = {}
        self._latest_sequence = 0
        self._displayed_sequence = -1
        self._paused_frame: np.ndarray | None = None
        self._preview_paused = False
        layout = QVBoxLayout(self)
        layout.addWidget(refresh_choices)
        layout.addWidget(QLabel("Node"))
        layout.addWidget(self.node)
        layout.addWidget(QLabel("Topic"))
        layout.addWidget(self.topic)
        layout.addWidget(self.type_label)
        layout.addWidget(QLabel("Image topic"))
        layout.addWidget(self.image_topic)
        layout.addWidget(self.image_type_label)
        node_row = QHBoxLayout()
        node_row.addWidget(start_node_info)
        node_row.addWidget(stop_node_info)
        echo_row = QHBoxLayout()
        echo_row.addWidget(start_echo)
        echo_row.addWidget(stop_echo)
        hz_row = QHBoxLayout()
        hz_row.addWidget(start_hz)
        hz_row.addWidget(stop_hz)
        preview_buttons = QHBoxLayout()
        preview_buttons.addWidget(start_preview)
        preview_buttons.addWidget(stop_preview)
        preview_buttons.addWidget(self.pause_preview_button)
        preview_buttons.addWidget(self.playback_fps)
        layout.addLayout(node_row)
        layout.addLayout(echo_row)
        layout.addLayout(hz_row)
        layout.addLayout(preview_buttons)
        preview_row = QHBoxLayout()
        preview_row.addWidget(self.preview, 3)
        info_col = QVBoxLayout()
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
        layout.addWidget(terminals)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_output)
        self.timer.start(1000)
        self.playback_timer = QTimer(self)
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
        selected_topic = self.ctx.state.selected_streams[0].get("name", "") if self.ctx.state.selected_streams else ""
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
            image_index = self.image_topic.findData(selected_topic)
            if image_index >= 0:
                self.image_topic.setCurrentIndex(image_index)
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
        if topic:
            self.ctx.state.selected_streams = [{"name": topic, "type": typ}]

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
        self.stop_image_preview()
        self._frames = 0
        self._received_frames = 0
        self._last_display_fps_at = time.time()
        self._last_camera_fps_at = time.time()
        self._max_camera_fps = 0.0
        self._preview_thread = QThread(self)
        self._preview_worker = RosImagePreviewWorker(topic)
        self._preview_worker.moveToThread(self._preview_thread)
        self._preview_thread.started.connect(self._preview_worker.run)
        self._preview_worker.status_changed.connect(self.preview_status.setText)
        self._preview_worker.status_changed.connect(lambda text: self._append_log("preview", text))
        self._preview_worker.finished.connect(self._preview_thread.quit)
        self._preview_worker.finished.connect(self._preview_worker.deleteLater)
        self._preview_thread.finished.connect(self._preview_thread.deleteLater)
        self._preview_thread.finished.connect(self._preview_finished)
        self._latest_frame = None
        self._latest_meta = {}
        self._latest_sequence = 0
        self._displayed_sequence = -1
        self._paused_frame = None
        self._preview_paused = False
        self.pause_preview_button.setText("Pause preview")
        self.playback_timer.start()
        self._preview_thread.start()
        self._append_log("preview", f"$ subscribe {topic}")

    def stop_image_preview(self) -> None:
        if self._preview_worker is not None:
            self._preview_worker.stop()
        if self._preview_thread is not None:
            self._preview_thread.quit()
            self._preview_thread.wait(1500)
        self._preview_worker = None
        self._preview_thread = None
        self.playback_timer.stop()
        self.clear_preview_buffer()
        self.preview_status.setText("preview: stopped")
        self._append_log("preview", "[stopped] image preview")

    def _preview_finished(self) -> None:
        self._preview_worker = None
        self._preview_thread = None
        if self.preview_status.text().startswith("subscribed"):
            self.preview_status.setText("preview: stopped")

    def store_preview_frame(self) -> None:
        if self._preview_worker is None:
            return
        frame, meta = self._preview_worker.snapshot()
        if frame is None:
            return
        self._latest_frame = frame
        self._latest_meta = meta
        received = int(meta.get("received", 0) or 0)
        if received <= self._latest_sequence:
            return
        delta = received - self._latest_sequence
        self._latest_sequence = received
        self._received_frames += delta
        now = time.time()
        if now - self._last_camera_fps_at >= 1.0:
            observed_fps = self._received_frames / (now - self._last_camera_fps_at)
            self._max_camera_fps = max(self._max_camera_fps, observed_fps)
            minimum_playback_fps = max(1, int(np.ceil(self._max_camera_fps)))
            if self.playback_fps.minimum() < minimum_playback_fps:
                self.playback_fps.setMinimum(minimum_playback_fps)
            if self.playback_fps.value() < minimum_playback_fps:
                self.playback_fps.setValue(minimum_playback_fps)
            self.camera_fps.setText(f"camera fps: {observed_fps:.1f} max: {self._max_camera_fps:.1f}")
            if self._latest_meta:
                self.image_meta.setText(
                    "image: "
                    f"{self._latest_meta.get('width')}x{self._latest_meta.get('height')} "
                    f"encoding={self._latest_meta.get('encoding')} step={self._latest_meta.get('step')}"
                )
            self._received_frames = 0
            self._last_camera_fps_at = now

    def display_latest_frame(self) -> None:
        if self._preview_paused:
            return
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
        self.camera_fps.setText("camera fps: 0.0")
        self.sample.setText("sample: x=- y=- rgb=(-, -, -)")

    def update_preview_frame(self, frame: np.ndarray) -> None:
        self.preview.set_frame(frame)
        self._frames += 1
        now = time.time()
        if now - self._last_display_fps_at >= 1.0:
            self.fps.setText(f"preview fps: {self._frames / (now - self._last_display_fps_at):.1f}")
            self._frames = 0
            self._last_display_fps_at = now

    def update_playback_timer(self) -> None:
        interval_ms = max(1, int(1000 / max(self.playback_fps.value(), 1)))
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
        self.editor = QPlainTextEdit()
        self.status = QLabel("")
        generate = QPushButton("Generate Default")
        validate = QPushButton("Validate")
        save = QPushButton("Save collection_config.yaml")
        generate.clicked.connect(self.generate)
        validate.clicked.connect(self.validate)
        save.clicked.connect(self.save)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(generate)
        row.addWidget(validate)
        row.addWidget(save)
        layout.addLayout(row)
        layout.addWidget(self.status)
        layout.addWidget(self.editor)
        self.generate()

    def generate(self) -> None:
        if not self.ctx.state.collection_config:
            self.ctx.state.collection_config = self.ctx.config_manager.build_default_config(
                self.ctx.state, self.ctx.last_graph.get("topics", [])
            )
        self.editor.setPlainText(self.ctx.config_manager.dumps(self.ctx.state.collection_config))

    def _current_config(self) -> dict:
        config = self.ctx.config_manager.loads(self.editor.toPlainText())
        self.ctx.state.collection_config = config
        return config

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
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.streams = QTableWidget(0, 5)
        self.streams.setHorizontalHeaderLabels(["Name", "Modality", "Source", "Topic/Endpoint", "Role"])
        refresh = QPushButton("Refresh Listener Plan")
        refresh.clicked.connect(self.refresh_plan)
        record = QPushButton("Simulate Listener Episode")
        record.clicked.connect(self.record)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Listener Recording Console"))
        layout.addWidget(QLabel("This page listens to configured streams and writes dataset episodes. It does not send robot control commands."))
        layout.addWidget(refresh)
        layout.addWidget(self.streams)
        layout.addWidget(record)
        layout.addWidget(self.log)
        self.refresh_plan()

    def refresh_plan(self) -> None:
        streams = self.ctx.state.collection_config.get("streams", []) if self.ctx.has_config() else []
        self.streams.setRowCount(len(streams))
        for row, stream in enumerate(streams):
            values = [
                stream.get("name", ""),
                stream.get("modality", ""),
                stream.get("source", ""),
                stream.get("topic") or stream.get("endpoint", ""),
                stream.get("training_role", ""),
            ]
            for col, value in enumerate(values):
                self.streams.setItem(row, col, QTableWidgetItem(str(value)))

    def record(self) -> None:
        if not self.ctx.has_config():
            QMessageBox.warning(self, "Missing config", "Generate and save collection_config.yaml before recording.")
            return
        path = self.ctx.recorder.record_episode(self.ctx.state.episodes_dir, self.episode_index)
        self.episode_index += 1
        self.log.appendPlainText(f"recorded: {path}")


class ReviewPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self._episode_paths: list[Path] = []
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Episode", "Status", "Steps", "Size MB", "Missing", "Fields"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.currentCellChanged.connect(self.show_episode_detail)
        self.layout_table = QTableWidget(0, 6)
        self.layout_table.setHorizontalHeaderLabels(["Area", "Task", "Version", "NPZ", "HDF5", "Manifest"])
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.hdf5_summary = QPlainTextEdit()
        self.hdf5_summary.setReadOnly(True)
        scan = QPushButton("Scan Episodes")
        scan.clicked.connect(self.scan)
        inspect_hdf5 = QPushButton("Inspect Current HDF5")
        inspect_hdf5.clicked.connect(self.inspect_hdf5)
        scan_layout = QPushButton("Scan CALVIN Layout")
        scan_layout.clicked.connect(self.scan_layout)
        layout = QVBoxLayout(self)
        layout.addWidget(scan)
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
        rows = self.ctx.validator.scan_npz(self.ctx.state.episodes_dir)
        self._episode_paths = [Path(str(row["path"])) for row in rows]
        self.table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            values = [row["name"], row["status"], row["steps"], row["size_mb"], row["missing"], row["fields"]]
            for col, value in enumerate(values):
                self.table.setItem(row_idx, col, QTableWidgetItem(str(value)))
        if rows:
            self.table.selectRow(0)
            self.show_episode_detail(0, 0, -1, -1)

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
        self.detail.setPlainText(self.ctx.validator.describe_npz(self._episode_paths[current_row]))

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
        convert = QPushButton("Convert NPZ to HDF5")
        convert.clicked.connect(self.convert)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Merge Dry Run"))
        layout.addWidget(dry_run)
        layout.addWidget(self.plan_table)
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
        self.target = QLineEdit("user@host:/remote/dataset/path/")
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        build_manifest = QPushButton("Build upload manifest")
        verify_manifest = QPushButton("Verify upload manifest")
        upload = QPushButton("Start rsync upload")
        build_manifest.clicked.connect(self.build_manifest)
        verify_manifest.clicked.connect(self.verify_manifest)
        upload.clicked.connect(self.upload)
        layout = QFormLayout(self)
        layout.addRow("Local path", self.local)
        layout.addRow("SSH target", self.target)
        layout.addRow(build_manifest)
        layout.addRow(verify_manifest)
        layout.addRow(upload)
        layout.addRow(self.report)

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

    def upload(self) -> None:
        local_path = self._validate_local_path()
        if not local_path:
            return
        if not self.ctx.has_converted_dataset() and local_path == self.ctx.state.merged_dir:
            QMessageBox.warning(self, "No converted dataset", "Convert NPZ to HDF5 before uploading the merged directory.")
            return
        if "user@host" in self.target.text():
            QMessageBox.warning(self, "Upload target", "Replace the placeholder SSH target before uploading.")
            return
        manifest_path = self.build_manifest()
        if manifest_path is None:
            return
        uploader = SshUploader(self.ctx.process_manager)
        uploader.upload_with_rsync(local_path, self.target.text().strip())


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
        self.ctx.process_manager.add_listener(self.refresh)
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
        self.ai_enabled = QComboBox()
        self.ai_enabled.addItems(["disabled", "enabled"])
        self.ai_base = QLineEdit("")
        self.ai_model = QLineEdit("")
        layout = QFormLayout(self)
        layout.addRow("AI validation", self.ai_enabled)
        layout.addRow("OpenAI-compatible base URL", self.ai_base)
        layout.addRow("Model", self.ai_model)
        note = QTextEdit()
        note.setReadOnly(True)
        note.setPlainText("API keys should be provided through environment variables, not saved in project YAML.")
        layout.addRow(note)
