from __future__ import annotations

from pathlib import Path

import time

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
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
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from robodataset_studio.core.config_manager import ConfigManager
from robodataset_studio.core.environment import EnvironmentService
from robodataset_studio.core.models import ProjectState
from robodataset_studio.core.process_manager import ProcessManager
from robodataset_studio.dataset.converter import Hdf5Converter
from robodataset_studio.dataset.layout import CalvinLayoutScanner
from robodataset_studio.dataset.merge_plan import CalvinMergePlanner
from robodataset_studio.dataset.recorder import MockRecorder
from robodataset_studio.dataset.validator import DatasetValidator
from robodataset_studio.ros.graph_discovery import RosGraphDiscovery
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
        self.topics = QTableWidget(0, 2)
        self.topics.setHorizontalHeaderLabels(["Topic", "Type"])
        self.topics.setSelectionBehavior(QAbstractItemView.SelectRows)
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

    def generate_config(self) -> None:
        self.ctx.state.collection_config = self.ctx.config_manager.build_default_config(
            self.ctx.state, self.ctx.last_graph.get("topics", [])
        )
        QMessageBox.information(self, "Config", "collection_config.yaml generated in memory. Open Config page to edit/save.")


class InspectorPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.topic = QLineEdit("/wx250s/joint_states")
        echo = QPushButton("Start topic echo")
        hz = QPushButton("Start topic hz")
        echo.clicked.connect(lambda: self.start_probe("echo"))
        hz.clicked.connect(lambda: self.start_probe("hz"))
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.preview = ImagePreviewLabel()
        self.preview.sampled.connect(self.update_sample)
        self.sample = QLabel("sample: x=- y=- rgb=(-, -, -)")
        self.fps = QLabel("preview fps: 0.0")
        self._frames = 0
        self._last_fps_at = time.time()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Topic"))
        layout.addWidget(self.topic)
        row = QHBoxLayout()
        row.addWidget(echo)
        row.addWidget(hz)
        layout.addLayout(row)
        layout.addWidget(QLabel("Probe output is tracked in Process page."))
        preview_row = QHBoxLayout()
        preview_row.addWidget(self.preview, 3)
        info_col = QVBoxLayout()
        info_col.addWidget(QLabel("Image Topic Preview"))
        info_col.addWidget(self.fps)
        info_col.addWidget(self.sample)
        info_col.addStretch(1)
        preview_row.addLayout(info_col, 1)
        layout.addLayout(preview_row)
        layout.addWidget(self.output)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_output)
        self.timer.start(1000)
        self.preview_timer = QTimer(self)
        self.preview_timer.timeout.connect(self.mock_preview_frame)
        self.preview_timer.start(150)

    def start_probe(self, mode: str) -> None:
        topic = self.topic.text().strip()
        if not topic:
            return
        command = ["ros2", "topic", mode, topic]
        if mode == "echo":
            command = ["ros2", "topic", "echo", topic]
        self.ctx.process_manager.start(command, f"topic_{mode}", "InspectorPage")

    def refresh_output(self) -> None:
        lines: list[str] = []
        for record in self.ctx.process_manager.records():
            if record.owner_page == "InspectorPage":
                lines.append(f"{record.process_id} [{record.status}] {record.command_text()}")
                lines.extend(record.stdout_tail[-8:])
                lines.extend(record.stderr_tail[-4:])
        self.output.setPlainText("\n".join(lines))

    def mock_preview_frame(self) -> None:
        h, w = 224, 224
        x = np.linspace(0, 255, w, dtype=np.uint8)
        y = np.linspace(0, 255, h, dtype=np.uint8)[:, None]
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:, :, 0] = x
        frame[:, :, 1] = y[:, 0:1]
        frame[:, :, 2] = (int(time.time() * 40) % 255)
        self.preview.set_frame(frame)
        self._frames += 1
        now = time.time()
        if now - self._last_fps_at >= 1.0:
            self.fps.setText(f"preview fps: {self._frames / (now - self._last_fps_at):.1f}")
            self._frames = 0
            self._last_fps_at = now

    def update_sample(self, x: int, y: int, r: int, g: int, b: int) -> None:
        self.sample.setText(f"sample: x={x} y={y} rgb=({r}, {g}, {b})")


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
        upload = QPushButton("Start rsync upload")
        upload.clicked.connect(self.upload)
        layout = QFormLayout(self)
        layout.addRow("Local path", self.local)
        layout.addRow("SSH target", self.target)
        layout.addRow(upload)

    def upload(self) -> None:
        local_path = Path(self.local.text()).expanduser()
        if not local_path.exists():
            QMessageBox.warning(self, "Missing local path", f"Local path does not exist:\n{local_path}")
            return
        if not self.ctx.has_converted_dataset() and local_path == self.ctx.state.merged_dir:
            QMessageBox.warning(self, "No converted dataset", "Convert NPZ to HDF5 before uploading the merged directory.")
            return
        if "user@host" in self.target.text():
            QMessageBox.warning(self, "Upload target", "Replace the placeholder SSH target before uploading.")
            return
        uploader = SshUploader(self.ctx.process_manager)
        uploader.upload_with_rsync(local_path, self.target.text().strip())


class ProcessPage(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["ID", "Type", "PID", "Status", "Owner", "Command", "Tail"])
        stop = QPushButton("Stop Selected")
        stop_all = QPushButton("Stop All")
        refresh = QPushButton("Refresh")
        stop.clicked.connect(self.stop_selected)
        stop_all.clicked.connect(self.ctx.process_manager.stop_all)
        refresh.clicked.connect(self.refresh)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(refresh)
        row.addWidget(stop)
        row.addWidget(stop_all)
        layout.addLayout(row)
        layout.addWidget(self.table)
        self.ctx.process_manager.add_listener(self.refresh)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1500)

    def refresh(self) -> None:
        records = self.ctx.process_manager.records()
        self.table.setRowCount(len(records))
        for row, record in enumerate(records):
            tail = "\n".join((record.stdout_tail + record.stderr_tail)[-3:])
            values = [record.process_id, record.type, record.pid or "", record.status, record.owner_page, record.command_text(), tail]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(str(value)))

    def stop_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        if item:
            self.ctx.process_manager.stop(item.text())


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
