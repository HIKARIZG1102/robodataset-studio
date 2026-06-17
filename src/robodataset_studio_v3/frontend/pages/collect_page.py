from __future__ import annotations

from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
)

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio_v3.frontend.pages.base import BasePage


class CollectPage(BasePage):
    def __init__(self, api: ApiClient, project: ProjectSummary) -> None:
        super().__init__(f"Collect - {project.key}", api, project)
        self.mode = QComboBox()
        self.mode.addItem("Manual", "manual")
        self.mode.addItem("Duration", "duration_sec")
        self.mode.addItem("Sample count", "sample_count")
        self.duration = QDoubleSpinBox()
        self.duration.setRange(0.1, 3600.0)
        self.duration.setDecimals(1)
        self.duration.setSingleStep(0.1)
        self.duration.setSuffix(" sec")
        self.duration.setValue(2.0)
        self.samples = QSpinBox()
        self.samples.setRange(1, 10_000_000)
        self.samples.setSuffix(" samples")
        self.samples.setValue(20)
        self.plan = QLabel("Plan: -")
        self.session_label = QLabel("Session: -")
        self.task_label = QLabel("Task: -")
        self.streams = QTableWidget(0, 6)
        self.streams.setHorizontalHeaderLabels(["Name", "Modality", "Source", "Topic/Endpoint", "Type", "Role"])
        self.mode.currentIndexChanged.connect(lambda _index: self.update_mode_ui())
        self.duration.valueChanged.connect(lambda _value: self.update_plan_text())
        self.samples.valueChanged.connect(lambda _value: self.update_plan_text())
        self.current_dataset_config: dict[str, Any] = {}
        self.active_task_id = ""
        self.active_session_dir = ""
        self.task_timer = QTimer(self)
        self.task_timer.setInterval(1000)
        self.task_timer.timeout.connect(self.poll_active_task)
        self._build()
        self.refresh_plan()

    def _build(self) -> None:
        controls = QHBoxLayout()
        refresh = QPushButton("Refresh Listener Plan")
        preflight = QPushButton("Check Nodes")
        simulate = QPushButton("Simulate Listener Episode")
        start = QPushButton("Start Recording")
        stop = QPushButton("Stop Recording")
        refresh.clicked.connect(self.refresh_plan)
        preflight.clicked.connect(self.preflight)
        simulate.clicked.connect(self.simulate_episode)
        start.clicked.connect(self.start_recording)
        stop.clicked.connect(self.stop_recording)
        self.duration_label = QLabel("Duration")
        self.samples_label = QLabel("Samples")
        controls.addWidget(QLabel("Stop mode"))
        controls.addWidget(self.mode)
        controls.addWidget(self.duration_label)
        controls.addWidget(self.duration)
        controls.addWidget(self.samples_label)
        controls.addWidget(self.samples)
        controls.addStretch(1)
        controls.addWidget(refresh)
        controls.addWidget(preflight)
        controls.addWidget(simulate)
        controls.addWidget(start)
        controls.addWidget(stop)
        self.layout.addWidget(QLabel("Listener Recording Console"))
        self.layout.addWidget(QLabel("Uses the current dataset_config.yaml. Image monitors are available from the global Inspector panel."))
        self.layout.addLayout(controls)
        self.layout.addWidget(self.plan)
        self.layout.addWidget(self.session_label)
        self.layout.addWidget(self.task_label)
        self.layout.addWidget(self.streams)
        self.finish_layout()
        self.update_mode_ui()

    def refresh_plan(self) -> None:
        self.status.setText("Refreshing listener plan...")
        self.run_async(self.api.get_dataset_config, self._finish_refresh_plan, self.project_key())

    def _finish_refresh_plan(self, result: object, error: object) -> None:
        if error is not None:
            self.show_error(error if isinstance(error, Exception) else Exception(str(error)))
            return
        config = result if isinstance(result, dict) else {}
        self.current_dataset_config = config
        recording = config.get("recording", {}) if isinstance(config.get("recording"), dict) else {}
        mode = str(recording.get("stop_mode") or "manual")
        index = self.mode.findData(mode)
        if index >= 0:
            self.mode.setCurrentIndex(index)
        if recording.get("episode_duration_sec"):
            self.duration.setValue(float(recording.get("episode_duration_sec")))
        if recording.get("target_samples"):
            self.samples.setValue(int(recording.get("target_samples")))
        self._populate_streams(config)
        self.update_mode_ui()
        self.show_result(self._plan_payload(), "Plan refreshed")

    def _populate_streams(self, config: dict[str, Any]) -> None:
        streams = config.get("streams", [])
        rows = streams if isinstance(streams, list) else []
        self.streams.setRowCount(len(rows))
        for row, stream in enumerate(rows):
            item = stream if isinstance(stream, dict) else {}
            values = [
                item.get("name", ""),
                item.get("modality", ""),
                item.get("source", ""),
                item.get("topic") or item.get("endpoint", ""),
                item.get("message_type", ""),
                item.get("training_role", ""),
            ]
            for col, value in enumerate(values):
                self.streams.setItem(row, col, QTableWidgetItem(str(value)))
        self.streams.resizeColumnsToContents()

    def update_mode_ui(self) -> None:
        mode = str(self.mode.currentData() or "manual")
        duration_visible = mode == "duration_sec"
        samples_visible = mode == "sample_count"
        self.duration_label.setVisible(duration_visible)
        self.duration.setVisible(duration_visible)
        self.samples_label.setVisible(samples_visible)
        self.samples.setVisible(samples_visible)
        self.update_plan_text()

    def update_plan_text(self) -> None:
        payload = self._plan_payload()
        self.plan.setText(payload["summary"])

    def _plan_payload(self) -> dict[str, Any]:
        config = self.current_dataset_config or {}
        recording = config.get("recording", {}) if isinstance(config.get("recording"), dict) else {}
        sample_rate = float(recording.get("sample_rate_hz") or 10)
        mode = str(self.mode.currentData() or "manual")
        min_steps = int(recording.get("min_episode_steps") or 1)
        requires_actions = bool(config.get("dataset", {}).get("requires_actions", True)) if isinstance(config.get("dataset"), dict) else True
        minimum_samples = max(min_steps, 2 if requires_actions else 1)
        if mode == "manual":
            summary = f"Plan: manual start/stop; capture rate: {sample_rate:g}Hz; estimated episode_*.npz files: manual"
            samples = None
            transitions = None
        elif mode == "sample_count":
            samples = max(int(self.samples.value()), minimum_samples)
            transitions = max(samples - 1, 0) if requires_actions else samples
            summary = f"Plan: sample count {samples}; estimated episode_*.npz files: {transitions}"
        else:
            duration = float(self.duration.value())
            samples = max(int(round(sample_rate * duration)), minimum_samples)
            transitions = max(samples - 1, 0) if requires_actions else samples
            summary = f"Plan: {duration:g}s x {sample_rate:g}Hz ~= {samples} samples; estimated episode_*.npz files: {transitions}"
        return {"summary": summary, "mode": mode, "sample_rate_hz": sample_rate, "samples": samples, "estimated_transitions": transitions}

    def preflight(self) -> None:
        self.status.setText("Checking configured nodes/topics...")
        self.run_async(
            self.api.post,
            lambda result, error: self.finish_async_result(result, error, "Preflight complete"),
            "/api/recording/preflight",
            {"project_key": self.project_key()},
            timeout=60.0,
        )

    def start_recording(self) -> None:
        mode = str(self.mode.currentData() or "manual")
        payload: dict[str, Any] = {"project_key": self.project_key(), "mode": mode}
        if mode == "duration_sec":
            payload["duration_sec"] = float(self.duration.value())
        if mode == "sample_count":
            payload["target_samples"] = int(self.samples.value())
        self.status.setText("Starting recording...")
        self.run_async(
            self.api.post,
            self._finish_start_recording,
            "/api/recording/start",
            payload,
            timeout=20.0,
        )

    def simulate_episode(self) -> None:
        payload: dict[str, Any] = {"project_key": self.project_key(), "mode": "simulate", "target_samples": int(self.samples.value())}
        self.status.setText("Writing simulated listener episode...")
        self.run_async(
            self.api.post,
            self._finish_start_recording,
            "/api/recording/simulate",
            payload,
            timeout=20.0,
        )

    def stop_recording(self) -> None:
        self.status.setText("Stopping recording...")
        self.run_async(
            self.api.post,
            self._finish_stop_recording,
            "/api/recording/stop",
            {"project_key": self.project_key()},
            timeout=20.0,
        )

    def _finish_start_recording(self, result: object, error: object) -> None:
        if error is not None:
            self.show_error(error if isinstance(error, Exception) else Exception(str(error)))
            return
        payload = result if isinstance(result, dict) else {}
        self.active_task_id = str(payload.get("task_id") or "")
        self.active_session_dir = str(payload.get("session_dir") or "")
        self.session_label.setText(f"Session: {self.active_session_dir or '-'}")
        self.task_label.setText(f"Task: {self.active_task_id or '-'}")
        self.show_result(payload, "Recording task started")
        if self.active_task_id:
            self.task_timer.start()

    def _finish_stop_recording(self, result: object, error: object) -> None:
        if error is not None:
            self.show_error(error if isinstance(error, Exception) else Exception(str(error)))
            return
        payload = result if isinstance(result, dict) else {}
        self.show_result(payload, "Stop requested")
        task_id = str(payload.get("task_id") or self.active_task_id)
        if task_id:
            self.active_task_id = task_id
            self.task_label.setText(f"Task: {task_id}")
            self.task_timer.start()

    def poll_active_task(self) -> None:
        if not self.active_task_id:
            self.task_timer.stop()
            return
        self.run_async(self.api.get, self._finish_task_poll, f"/api/tasks/{self.active_task_id}", timeout=5.0)

    def _finish_task_poll(self, result: object, error: object) -> None:
        if error is not None:
            self.status.setText(f"Task poll failed: {error}")
            self.task_timer.stop()
            return
        task = result if isinstance(result, dict) else {}
        status = str(task.get("status") or "")
        message = str(task.get("message") or "")
        self.task_label.setText(f"Task: {self.active_task_id} [{status}] {message}")
        if status in {"done", "failed", "cancelled"}:
            self.task_timer.stop()
            self.show_result(task, f"Recording {status}")
            result_payload = task.get("result", {}) if isinstance(task.get("result"), dict) else {}
            session_dir = str(result_payload.get("session_dir") or self.active_session_dir)
            if session_dir:
                self.active_session_dir = session_dir
                self.session_label.setText(f"Session: {session_dir}")
            self.refresh_plan()
