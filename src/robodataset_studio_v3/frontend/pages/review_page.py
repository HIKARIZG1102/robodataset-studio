from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from robodataset_studio_v3.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio_v3.frontend.pages.base import BasePage
from robodataset_studio_v3.frontend.ui_helpers import make_path_field, make_path_label


class ReviewPage(BasePage):
    def __init__(self, api: ApiClient, project: ProjectSummary | None = None) -> None:
        super().__init__("Review", api, project)
        self._review_rows: list[dict[str, Any]] = []
        self._visible_rows: list[dict[str, Any]] = []
        self._last_report: dict[str, Any] = {}
        self.overview_tree = QTreeWidget()
        self.overview_tree.setHeaderLabels(["Name", "Type", "Size"])
        self.overview_detail = QPlainTextEdit()
        self.overview_detail.setReadOnly(True)
        self.overview_tree.currentItemChanged.connect(lambda item, _prev: self.show_overview_item(item))

        self.session_dir = QLineEdit()
        self.session_dir.setReadOnly(True)
        self.session_summary = QLabel("")
        make_path_field(self.session_dir)
        make_path_label(self.session_summary)
        self.status_filter = QComboBox()
        self.status_filter.addItems(["all", "uncheck", "ok", "warning", "error"])
        self.status_filter.currentTextChanged.connect(self.apply_review_filter)
        self.mark_select = QComboBox()
        self.mark_select.addItems(["good", "bad", "uncertain", "unmarked"])

        self.episodes = QTableWidget(0, 8)
        self.episodes.setHorizontalHeaderLabels(["Episode", "Status", "Mark", "Steps", "Size MB", "Missing", "Quality", "Fields"])
        self.episodes.setSelectionBehavior(QTableWidget.SelectRows)
        self.episodes.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.episodes.horizontalHeader().setStretchLastSection(True)
        self.episodes.currentCellChanged.connect(lambda row, _col, _prev_row, _prev_col: self.load_episode_detail(row))

        self.summary = QPlainTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setMaximumHeight(112)
        self.ai_session_report = QPlainTextEdit()
        self.ai_session_report.setPlaceholderText("AI session report will be loaded from ai_session_report.md in the selected session.")
        self.ai_session_report.setMaximumHeight(112)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.ai_review_prompt = QPlainTextEdit()
        self.ai_review_prompt.setMaximumHeight(170)
        self.ai_review_result = QPlainTextEdit()
        self.ai_review_result.setReadOnly(True)

        self.hdf5_path = QLineEdit()
        self.hdf5_path.setReadOnly(True)
        make_path_field(self.hdf5_path)
        self.hdf5_summary = QPlainTextEdit()
        self.hdf5_summary.setReadOnly(True)
        self.hdf5_check_summary = QPlainTextEdit()
        self.hdf5_check_summary.setReadOnly(True)
        self.hdf5_check_summary.setMaximumHeight(140)
        self.hdf5_table = QTableWidget(0, 4)
        self.hdf5_table.setHorizontalHeaderLabels(["Scope", "Status", "Issue", "Detail"])
        self.hdf5_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.hdf5_table.horizontalHeader().setStretchLastSection(True)

        if project is not None:
            self.session_dir.setText(f"{project.path}/raw_sessions")
            self.hdf5_path.setText(f"{project.path}/exports/calvin.hdf5")

        tabs = QTabWidget()
        tabs.addTab(self._overview_tab(), "Overview")
        tabs.addTab(self._episode_tab(), "Episode Review")
        tabs.addTab(self._hdf5_tab(), "HDF5 Inspect")
        self.layout.addWidget(tabs, 1)
        self.finish_layout()

    def on_project_config_changed(self, project: ProjectSummary | None) -> None:
        self.project = project
        self._review_rows = []
        self._visible_rows = []
        self.episodes.setRowCount(0)
        self.detail.clear()
        self.summary.clear()
        self.ai_session_report.clear()
        self.hdf5_summary.clear()
        self.hdf5_check_summary.clear()
        self.hdf5_table.setRowCount(0)
        if project is not None:
            self.session_dir.setText(f"{project.path}/raw_sessions")
            self.hdf5_path.setText(f"{project.path}/exports/calvin.hdf5")
        self.refresh_overview()

    def _overview_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        buttons = QHBoxLayout()
        refresh = QPushButton("Refresh Overview")
        refresh.clicked.connect(self.refresh_overview)
        buttons.addWidget(refresh)
        buttons.addStretch(1)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.overview_tree)
        splitter.addWidget(self.overview_detail)
        splitter.setSizes([520, 620])
        layout.addLayout(buttons)
        layout.addWidget(splitter, 1)
        self.refresh_overview()
        return widget

    def _episode_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        form = QFormLayout()
        form.addRow("Review session root", self._path_row(self.session_dir, self.browse_session))
        layout.addLayout(form)

        target_buttons = QHBoxLayout()
        for label, handler in [
            ("Use Current Session", self.use_current_session),
            ("Scan Session", self.scan_session),
            ("Run Local Checks", self.check_session),
            ("Export Quality Report", self.export_quality_report),
        ]:
            button = QPushButton(label)
            button.clicked.connect(handler)
            target_buttons.addWidget(button)
        target_buttons.addStretch(1)
        layout.addLayout(target_buttons)
        layout.addWidget(self.session_summary)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Status filter"))
        controls.addWidget(self.status_filter)
        controls.addWidget(QLabel("Manual mark"))
        controls.addWidget(self.mark_select)
        mark_button = QPushButton("Mark Selected")
        mark_button.clicked.connect(self.mark_selected)
        controls.addWidget(mark_button)
        delete_button = QPushButton("Delete Selected")
        delete_button.clicked.connect(self.trash_selected)
        controls.addWidget(delete_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        summary_splitter = QSplitter(Qt.Horizontal)
        quality_panel = QWidget()
        quality_layout = QVBoxLayout(quality_panel)
        quality_layout.setContentsMargins(0, 0, 0, 0)
        quality_layout.addWidget(QLabel("Quality Summary"))
        quality_layout.addWidget(self.summary)
        ai_report_panel = QWidget()
        ai_report_layout = QVBoxLayout(ai_report_panel)
        ai_report_layout.setContentsMargins(0, 0, 0, 0)
        ai_report_header = QHBoxLayout()
        ai_report_header.addWidget(QLabel("AI Session Report"))
        save_ai_report = QPushButton("Save AI Report")
        save_ai_report.clicked.connect(self.save_ai_session_report)
        ai_report_header.addWidget(save_ai_report)
        ai_report_header.addStretch(1)
        ai_report_layout.addLayout(ai_report_header)
        ai_report_layout.addWidget(self.ai_session_report)
        summary_splitter.addWidget(quality_panel)
        summary_splitter.addWidget(ai_report_panel)
        summary_splitter.setSizes([520, 620])
        layout.addWidget(summary_splitter)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.episodes)
        detail_panel = QWidget()
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.addWidget(QLabel("Selected NPZ Details"))
        detail_layout.addWidget(self.detail)
        splitter.addWidget(detail_panel)
        splitter.setSizes([700, 480])
        layout.addWidget(splitter, 1)

        ai_buttons = QHBoxLayout()
        ai_buttons.addWidget(QLabel("AI Review"))
        build_prompt = QPushButton("Default AI Review Prompt")
        build_prompt.clicked.connect(self.build_ai_review_prompt)
        send_review = QPushButton("Send AI Review")
        send_review.clicked.connect(self.send_ai_review)
        ai_buttons.addWidget(build_prompt)
        ai_buttons.addWidget(send_review)
        ai_buttons.addStretch(1)
        layout.addLayout(ai_buttons)
        ai_splitter = QSplitter(Qt.Horizontal)
        ai_splitter.addWidget(self.ai_review_prompt)
        ai_splitter.addWidget(self.ai_review_result)
        ai_splitter.setSizes([600, 600])
        layout.addWidget(ai_splitter)
        return widget

    def _hdf5_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        form = QFormLayout()
        form.addRow("HDF5 file", self._path_row(self.hdf5_path, self.browse_hdf5))
        layout.addLayout(form)
        buttons = QHBoxLayout()
        inspect = QPushButton("Inspect HDF5")
        inspect.clicked.connect(self.inspect_hdf5)
        check = QPushButton("Run HDF5 Checks")
        check.clicked.connect(self.check_hdf5)
        buttons.addWidget(inspect)
        buttons.addWidget(check)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addWidget(QLabel("HDF5 Overview"))
        layout.addWidget(self.hdf5_summary)
        layout.addWidget(QLabel("HDF5 Check Summary"))
        layout.addWidget(self.hdf5_check_summary)
        layout.addWidget(QLabel("HDF5 Check Results"))
        layout.addWidget(self.hdf5_table, 1)
        return widget

    def use_current_session(self) -> None:
        if self.project is not None:
            self.session_dir.setText(f"{self.project.path}/raw_sessions")
        self.scan_session()

    def scan_session(self) -> None:
        self._post("/api/review/session/scan", {"session_dir": self.session_dir.text().strip()}, "Session scanned", self._finish_scan)

    def check_session(self) -> None:
        self._post("/api/review/session/check", {"session_dir": self.session_dir.text().strip()}, "Session checked", self._finish_check)

    def export_quality_report(self) -> None:
        self._post("/api/review/session/report", {"session_dir": self.session_dir.text().strip()}, "Quality report exported", self._finish_report)

    def load_ai_session_report(self) -> None:
        session_dir = self.session_dir.text().strip()
        if not session_dir:
            self.ai_session_report.clear()
            return
        self.run_async(
            self.api.post,
            self._finish_load_ai_session_report,
            "/api/review/session/ai-report/load",
            {"session_dir": session_dir},
            timeout=20.0,
        )

    def save_ai_session_report(self) -> None:
        session_dir = self.session_dir.text().strip()
        if not session_dir:
            self.status.setText("Select a session before saving AI report.")
            return
        payload = {"session_dir": session_dir, "content": self.ai_session_report.toPlainText()}
        self.run_async(self.api.post, self._finish_save_ai_session_report, "/api/review/session/ai-report/save", payload, timeout=20.0)

    def inspect_hdf5(self) -> None:
        self._post("/api/review/hdf5/inspect", {"hdf5_path": self.hdf5_path.text().strip()}, "HDF5 inspected", self._finish_hdf5_inspect)

    def check_hdf5(self) -> None:
        self._post("/api/review/hdf5/check", {"hdf5_path": self.hdf5_path.text().strip()}, "HDF5 checked", self._finish_hdf5_check)

    def refresh_overview(self) -> None:
        self.overview_tree.clear()
        if self.project is None:
            return
        root = Path(self.project.path)
        if not root.exists():
            return
        root_item = QTreeWidgetItem([root.name, "dir", self._format_bytes(self._path_size(root, max_files=2000))])
        root_item.setData(0, Qt.UserRole, str(root))
        self.overview_tree.addTopLevelItem(root_item)
        self._add_overview_children(root_item, root, depth=0)
        root_item.setExpanded(True)

    def _add_overview_children(self, parent: QTreeWidgetItem, path: Path, *, depth: int) -> None:
        if depth >= 4:
            return
        try:
            children = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        except Exception:
            return
        for child in children[:400]:
            kind = "dir" if child.is_dir() else child.suffix.lstrip(".") or "file"
            size = self._format_bytes(self._path_size(child, max_files=1000))
            item = QTreeWidgetItem([child.name, kind, size])
            item.setData(0, Qt.UserRole, str(child))
            parent.addChild(item)
            if child.is_dir():
                self._add_overview_children(item, child, depth=depth + 1)

    def show_overview_item(self, item: QTreeWidgetItem | None) -> None:
        if item is None:
            self.overview_detail.clear()
            return
        path = Path(str(item.data(0, Qt.UserRole) or ""))
        if not path.exists():
            self.overview_detail.clear()
            return
        if self.project is not None and not self._is_within_project(path):
            self.overview_detail.setPlainText(f"path: {path}\n\noutside current project")
            return
        lines = [f"path: {path}", f"type: {'dir' if path.is_dir() else 'file'}", f"size: {self._format_bytes(self._path_size(path, max_files=2000))}"]
        if path.is_file() and path.suffix.lower() in {".yaml", ".yml", ".json", ".txt"}:
            try:
                lines.extend(["", path.read_text(encoding="utf-8", errors="replace")[:20000]])
            except Exception as exc:
                lines.append(f"cannot read file: {exc}")
        self.overview_detail.setPlainText("\n".join(lines))

    def _path_size(self, path: Path, *, max_files: int = 10000) -> int:
        try:
            if path.is_file():
                return path.stat().st_size
            total = 0
            count = 0
            for item in path.rglob("*"):
                if count >= max_files:
                    break
                if item.is_file():
                    total += item.stat().st_size
                    count += 1
            return total
        except Exception:
            return 0

    def _is_within_project(self, path: Path) -> bool:
        if self.project is None:
            return False
        try:
            path.resolve().relative_to(Path(self.project.path).resolve())
            return True
        except ValueError:
            return False

    @staticmethod
    def _format_bytes(value: int) -> str:
        size = float(value)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    def build_ai_review_prompt(self) -> None:
        report = self._last_report if self._last_report else {"episodes": self._review_rows, "total": len(self._review_rows)}
        self._post("/api/ai/review-prompt", {"review_summary": report}, "AI review prompt generated", self._finish_ai_prompt)

    def send_ai_review(self) -> None:
        prompt = self.ai_review_prompt.toPlainText().strip()
        if not prompt:
            self.build_ai_review_prompt()
            return
        self.status.setText("AI review running...")
        self.run_async(self.api.get, self._finish_ai_settings, "/api/settings", timeout=10.0)

    def _post(self, path: str, payload: dict[str, Any], status: str, callback) -> None:
        self.status.setText(f"{status}...")
        self.run_async(self.api.post, callback, path, payload, timeout=60.0)

    def _finish_scan(self, result: object, error: object) -> None:
        payload = self._payload_or_error(result, error)
        if not payload:
            return
        rows = payload.get("episodes", [])
        self._review_rows = rows if isinstance(rows, list) else []
        self._last_report = payload.get("quality_report", {}) if isinstance(payload.get("quality_report"), dict) else {}
        self._sync_session(payload)
        self.apply_review_filter()
        self.update_quality_summary()
        self.session_summary.setText(
            f"session: {payload.get('session_dir', '')} | training: {payload.get('training_dir', '')} | "
            f"episodes: {payload.get('episode_count', len(self._review_rows))} | checks: not run"
        )
        self.load_ai_session_report()
        self.show_result(result, "Session scanned")

    def _finish_check(self, result: object, error: object) -> None:
        payload = self._payload_or_error(result, error)
        if not payload:
            return
        rows = payload.get("episodes", [])
        self._review_rows = rows if isinstance(rows, list) else []
        self._last_report = payload.get("quality_report", {}) if isinstance(payload.get("quality_report"), dict) else {}
        self._sync_session(payload)
        self.apply_review_filter()
        self.update_quality_summary()
        self.session_summary.setText(
            f"session: {payload.get('session_dir', '')} | training: {payload.get('training_dir', '')} | "
            f"episodes: {len(self._review_rows)} | checks: local script"
        )
        self.load_ai_session_report()
        self.show_result(result, "Session checked")

    def _finish_report(self, result: object, error: object) -> None:
        payload = self._payload_or_error(result, error)
        if not payload:
            return
        self.status.setText(f"Quality report exported: {payload.get('path', '')}")
        report = payload.get("report", {})
        if isinstance(report, dict):
            self._last_report = report
            self.update_quality_summary()
        self.show_result(result, "Quality report exported")

    def _finish_hdf5_inspect(self, result: object, error: object) -> None:
        payload = self._payload_or_error(result, error)
        if not payload:
            self.hdf5_summary.setPlainText(f"Cannot inspect HDF5:\n{error}")
            return
        self.hdf5_summary.setPlainText(str(payload.get("summary_text", "")))
        self.show_result(result, "HDF5 inspected")

    def _finish_hdf5_check(self, result: object, error: object) -> None:
        payload = self._payload_or_error(result, error)
        if not payload:
            self.hdf5_check_summary.setPlainText(f"Cannot check HDF5:\n{error}")
            return
        self.hdf5_check_summary.setPlainText(str(payload.get("summary_text", "")))
        rows = payload.get("rows", [])
        self._populate_issue_table(self.hdf5_table, rows if isinstance(rows, list) else [], ["scope", "status", "issue", "detail"])
        self.show_result(result, "HDF5 checked")

    def _finish_ai_prompt(self, result: object, error: object) -> None:
        payload = self._payload_or_error(result, error)
        if not payload:
            return
        self.ai_review_prompt.setPlainText(str(payload.get("prompt", "")))
        self.ai_review_result.setPlainText("AI review prompt generated.")
        self.show_result(result, "AI review prompt generated")

    def _finish_ai_settings(self, result: object, error: object) -> None:
        if error is not None:
            self.ai_review_result.setPlainText(f"Cannot load AI settings:\n{error}")
            self.show_error(error if isinstance(error, Exception) else Exception(str(error)))
            return
        settings = result if isinstance(result, dict) else {}
        ai = settings.get("ai", {}) if isinstance(settings.get("ai"), dict) else {}
        if not ai.get("enabled"):
            self.ai_review_result.setPlainText("Enable AI in Settings before using AI review.")
            self.status.setText("AI disabled")
            return
        payload = {
            "prompt": self.ai_review_prompt.toPlainText().strip(),
            "kind": "ai_review",
            "base_url": str(ai.get("base_url", "")),
            "model": str(ai.get("model", "")),
            "api_key": str(ai.get("api_key", "")),
        }
        self.run_async(self.api.post, self._finish_ai_review, "/api/ai/send", payload, timeout=float(ai.get("timeout_sec", 90) or 90) + 10)

    def _finish_ai_review(self, result: object, error: object) -> None:
        payload = self._payload_or_error(result, error)
        if not payload:
            self.ai_review_result.setPlainText(f"AI review failed:\n{error}")
            return
        if payload.get("error"):
            self.ai_review_result.setPlainText(f"AI review failed:\n{payload.get('error')}")
            self.status.setText("AI review failed")
            return
        self.ai_review_result.setPlainText(str(payload.get("response", "")))
        self.ai_session_report.setPlainText(str(payload.get("response", "")))
        self.show_result(result, "AI review finished")

    def _finish_load_ai_session_report(self, result: object, error: object) -> None:
        if error is not None:
            self.ai_session_report.setPlainText(f"Cannot load AI session report:\n{error}")
            return
        payload = self._payload_or_error(result, error)
        self.ai_session_report.setPlainText(str(payload.get("content", "")))
        path = str(payload.get("path", ""))
        self.ai_session_report.setToolTip(path)
        if path:
            self.status.setText(f"AI session report loaded: {path}")

    def _finish_save_ai_session_report(self, result: object, error: object) -> None:
        payload = self._payload_or_error(result, error)
        if not payload:
            return
        self.status.setText(f"AI session report saved: {payload.get('path', '')}")
        self.show_result(result, "AI session report saved")

    def apply_review_filter(self) -> None:
        status = self.status_filter.currentText()
        self._visible_rows = [row for row in self._review_rows if status == "all" or str(row.get("status", "")) == status]
        self.episodes.setRowCount(len(self._visible_rows))
        for row_idx, row in enumerate(self._visible_rows):
            values = [
                row.get("name", ""),
                row.get("status", ""),
                row.get("mark", "unmarked"),
                row.get("steps", ""),
                row.get("size_mb", ""),
                row.get("missing", ""),
                row.get("quality", ""),
                row.get("fields", ""),
            ]
            for col, value in enumerate(values):
                self.episodes.setItem(row_idx, col, QTableWidgetItem(str(value)))
        self._fit_episode_table()
        if self._visible_rows:
            self.episodes.selectRow(0)
            self.load_episode_detail(0)
        else:
            self.detail.clear()

    def update_quality_summary(self) -> None:
        report = self._last_report if isinstance(self._last_report, dict) else {}
        by_status = report.get("by_status", {}) if isinstance(report.get("by_status"), dict) else {}
        marks = report.get("mark_counts", {}) if isinstance(report.get("mark_counts"), dict) else {}
        issues = report.get("issue_counts", {}) if isinstance(report.get("issue_counts"), dict) else {}
        lines = [
            f"total: {report.get('total', len(self._review_rows))}",
            "status: "
            f"ok={by_status.get('ok', 0)} warning={by_status.get('warning', 0)} error={by_status.get('error', 0)} "
            f"uncheck={sum(1 for row in self._review_rows if str(row.get('status', '')) == 'uncheck')}",
            "marks: " + (", ".join(f"{key}={value}" for key, value in sorted(marks.items())) if marks else "-"),
            "issues: " + (", ".join(f"{key}={value}" for key, value in sorted(issues.items())) if issues else "-"),
        ]
        self.summary.setPlainText("\n".join(lines))

    def load_episode_detail(self, row: int) -> None:
        if row < 0 or row >= len(self._visible_rows):
            self.detail.clear()
            return
        episode = str(self._visible_rows[row].get("name", ""))
        if not episode:
            self.detail.clear()
            return
        payload = {"session_dir": self.session_dir.text().strip(), "episode": episode, "status": ""}
        self.detail.setPlainText(f"Loading {episode}...")
        self.run_async(self.api.post, self._finish_episode_detail, "/api/review/session/episode", payload, timeout=20.0)

    def _finish_episode_detail(self, result: object, error: object) -> None:
        if error is not None:
            self.detail.setPlainText(f"Cannot load episode detail:\n{error}")
            return
        payload = result if isinstance(result, dict) else {}
        if "description" in payload:
            self.detail.setPlainText(str(payload.get("description", "")))
        else:
            self.detail.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2, default=str))

    def mark_selected(self) -> None:
        row = self.episodes.currentRow()
        if row < 0 or row >= len(self._visible_rows):
            self.status.setText("Select an episode row first.")
            return
        episode = str(self._visible_rows[row].get("name", ""))
        mark = self.mark_select.currentText()
        payload = {"session_dir": self.session_dir.text().strip(), "episode": episode, "status": mark}
        self.run_async(self.api.post, lambda result, error: self._finish_mark(result, error, episode, mark), "/api/review/session/mark", payload, timeout=20.0)

    def _finish_mark(self, result: object, error: object, episode: str, mark: str) -> None:
        if error is not None:
            self.show_error(error if isinstance(error, Exception) else Exception(str(error)))
            return
        for row in self._review_rows:
            if str(row.get("name", "")) == episode:
                row["mark"] = mark
        self.apply_review_filter()
        self.status.setText("Episode mark saved")
        self.show_result(result, "Episode mark saved")

    def trash_selected(self) -> None:
        selected_rows = sorted({index.row() for index in self.episodes.selectedIndexes()}, reverse=True)
        if not selected_rows:
            self.status.setText("Select episode rows first.")
            return
        self._trash_queue = [str(self._visible_rows[row].get("name", "")) for row in selected_rows if 0 <= row < len(self._visible_rows)]
        self._trash_next()

    def _trash_next(self) -> None:
        if not getattr(self, "_trash_queue", []):
            self.scan_session()
            return
        episode = self._trash_queue.pop(0)
        payload = {"session_dir": self.session_dir.text().strip(), "episode": episode, "status": "bad"}
        self.run_async(self.api.post, self._finish_trash, "/api/review/session/trash", payload, timeout=20.0)

    def _finish_trash(self, result: object, error: object) -> None:
        if error is not None:
            self.show_error(error if isinstance(error, Exception) else Exception(str(error)))
            return
        self.show_result(result, "Episode moved to review_deleted")
        self._trash_next()

    def _payload_or_error(self, result: object, error: object) -> dict[str, Any]:
        if error is not None:
            self.show_error(error if isinstance(error, Exception) else Exception(str(error)))
            return {}
        if not isinstance(result, dict):
            return {}
        payload = result.get("result", result)
        return payload if isinstance(payload, dict) else {}

    def _sync_session(self, payload: dict[str, Any]) -> None:
        if payload.get("session_dir"):
            self.session_dir.setText(str(payload.get("session_dir")))

    def _populate_issue_table(self, table: QTableWidget, rows: list[Any], keys: list[str]) -> None:
        table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            data = row if isinstance(row, dict) else {}
            for col, key in enumerate(keys):
                table.setItem(row_idx, col, QTableWidgetItem(str(data.get(key, ""))))
        self._fit_issue_table(table)

    def _fit_episode_table(self) -> None:
        widths = [180, 82, 86, 64, 82, 180, 180]
        for col, width in enumerate(widths):
            self.episodes.setColumnWidth(col, width)

    def _fit_issue_table(self, table: QTableWidget) -> None:
        widths = [180, 82, 180]
        for col, width in enumerate(widths):
            table.setColumnWidth(col, width)

    def browse_session(self) -> None:
        if self._browse_dir(self.session_dir, "Select CALVIN session"):
            self.load_ai_session_report()

    def browse_hdf5(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select HDF5 file", self.hdf5_path.text().strip(), "HDF5 (*.hdf5 *.h5);;All files (*)")
        if path:
            self.hdf5_path.setText(path)

    def _browse_dir(self, target: QLineEdit, title: str) -> bool:
        path = QFileDialog.getExistingDirectory(self, title, target.text().strip())
        if path:
            target.setText(path)
            return True
        return False

    def _path_row(self, field: QLineEdit, handler) -> QWidget:
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        browse = QPushButton("Browse")
        browse.clicked.connect(handler)
        row.addWidget(field)
        row.addWidget(browse)
        return widget
