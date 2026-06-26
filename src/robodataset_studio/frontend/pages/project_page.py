from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QTimer, Signal
from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QPlainTextEdit, QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from robodataset_studio.frontend.api_client import ApiClient, ProjectSummary
from robodataset_studio.frontend.i18n import text
from robodataset_studio.frontend.pages.base import BasePage


class ProjectPage(BasePage):
    projectConfigChanged = Signal(object)

    def __init__(self, api: ApiClient, project: ProjectSummary | None = None) -> None:
        super().__init__("Properties", api, project)
        self.config_select = QComboBox()
        self.configs: list[dict] = []
        self.info = QPlainTextEdit()
        self.info.setReadOnly(True)
        self.info.setMaximumHeight(170)
        self.output.setReadOnly(True)
        self.output.setMinimumHeight(220)
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(lambda _path: self.schedule_refresh())
        self.watcher.fileChanged.connect(lambda _path: self.schedule_refresh())
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.setInterval(250)
        self.refresh_timer.timeout.connect(self.refresh)
        self.signature_timer = QTimer(self)
        self.signature_timer.setInterval(2000)
        self.signature_timer.timeout.connect(self.refresh_if_changed)
        self._last_signature: tuple[int, int, int] | None = None
        self._build()
        self.refresh()
        self.signature_timer.start()

    def _build(self) -> None:
        buttons = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        refresh_library = QPushButton("Refresh Library")
        refresh_library.clicked.connect(self.refresh_library)
        load_config = QPushButton("Load Config Into Project")
        load_config.clicked.connect(self.load_config_into_project)
        structure = QPushButton("Open Structure Window")
        structure.clicked.connect(self.open_structure_window)
        buttons.addWidget(QLabel("Library config"))
        buttons.addWidget(self.config_select, 2)
        buttons.addWidget(refresh_library)
        buttons.addWidget(load_config)
        buttons.addWidget(refresh)
        buttons.addWidget(structure)
        buttons.addStretch(1)

        self.layout.addLayout(buttons)
        self.layout.addWidget(QLabel("Project Summary"))
        self.layout.addWidget(self.info)
        self.layout.addWidget(QLabel("Project Structure Tree"))
        self.finish_layout()

    def on_project_config_changed(self, project: ProjectSummary | None) -> None:
        self.project = project
        self._last_signature = None
        self.refresh()

    def schedule_refresh(self) -> None:
        self.refresh_timer.start()

    def refresh_if_changed(self) -> None:
        if self.project is None:
            return
        signature = self._project_signature(Path(self.project.path))
        if signature != self._last_signature:
            self.refresh()

    def refresh(self) -> None:
        if self.project is None:
            self.info.setPlainText("No project is open.")
            self.output.setPlainText("")
            self._reset_watches([])
            self._last_signature = None
            return
        root = Path(self.project.path)
        signature = self._project_signature(root)
        self._last_signature = signature
        size = self._dir_size(root)
        modified = datetime.fromtimestamp(root.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S") if root.exists() else "-"
        lines = [
            f"name: {self.project.name}",
            f"version: {self.project.version}",
            f"key: {self.project.key}",
            f"config: {self.project.config_id or '-'}",
            f"recorded data: {self.project.has_recorded_data}",
            f"path: {self.project.path}",
            f"size: {self._format_bytes(size)}",
            f"modified: {modified}",
        ]
        self.info.setPlainText("\n".join(lines))
        self.output.setPlainText("\n".join(self._ascii_tree(root)))
        self.status.setText("Project properties refreshed")
        self._reset_watches(self._watch_paths(root))
        self.refresh_library()

    def refresh_library(self) -> None:
        current = self.project.config_id if self.project is not None else ""
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
            index = self.config_select.findData(current)
            if index >= 0:
                self.config_select.setCurrentIndex(index)
        self.config_select.blockSignals(False)

    def load_config_into_project(self) -> None:
        if self.project is None:
            QMessageBox.information(self, "Load Config", "Open or create a project first.")
            return
        config_id = str(self.config_select.currentData() or "")
        if not config_id:
            QMessageBox.information(self, "Load Config", "Select a library config first.")
            return
        if self.project.has_recorded_data and config_id != self.project.config_id:
            QMessageBox.warning(
                self,
                "Load Config",
                "This project already has recorded data. You can reload the current library config, but create a new project version before switching to another config.",
            )
            return
        try:
            self.project = self.api.bind_project_config(self.project.key, config_id)
        except Exception as exc:
            self.status.setText(f"Cannot load config into project: {exc}")
            return
        self.status.setText(f"Loaded config into project: {config_id}")
        self.projectConfigChanged.emit(self.project)
        self.refresh()

    def open_structure_window(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(self._tr("Project Structure"))
        dialog.resize(760, 640)
        layout = QVBoxLayout(dialog)
        splitter = QSplitter()
        tree = QTreeWidget()
        tree.setHeaderLabels([self._tr("Name"), self._tr("Type"), self._tr("Size")])
        detail = QPlainTextEdit()
        detail.setReadOnly(True)
        tree.currentItemChanged.connect(lambda item, _prev: self.show_item_detail(item, detail))
        splitter.addWidget(tree)
        splitter.addWidget(detail)
        splitter.setSizes([420, 340])
        layout.addWidget(splitter)
        if self.project is not None:
            root = Path(self.project.path)
            if root.exists():
                root_item = QTreeWidgetItem([root.name, "dir", self._format_bytes(self._dir_size(root, max_files=2000))])
                root_item.setData(0, 0x0100, str(root))
                tree.addTopLevelItem(root_item)
                self._add_children_to_tree(root_item, root, depth=0)
                root_item.setExpanded(True)
                tree.resizeColumnToContents(0)
                tree.setCurrentItem(root_item)
        close = QPushButton(self._tr("Close"))
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    def _add_children_to_tree(self, parent: QTreeWidgetItem, path: Path, *, depth: int) -> None:
        if depth >= 3:
            return
        try:
            children = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        except Exception:
            return
        for child in children[:300]:
            kind = "dir" if child.is_dir() else child.suffix.lstrip(".") or "file"
            size = self._format_bytes(self._dir_size(child, max_files=800) if child.is_dir() else child.stat().st_size)
            label = self._summarized_name(child)
            item = QTreeWidgetItem([label, kind, size])
            item.setData(0, 0x0100, str(child))
            parent.addChild(item)
            if child.is_dir() and not self._should_summarize_dir(child):
                self._add_children_to_tree(item, child, depth=depth + 1)

    def show_item_detail(self, item: QTreeWidgetItem | None, detail: QPlainTextEdit) -> None:
        if item is None:
            detail.clear()
            return
        path = Path(str(item.data(0, 0x0100) or ""))
        if not path.exists():
            detail.clear()
            return
        if self.project is not None and not self._is_within_project(path):
            detail.setPlainText(f"path: {path}\n\noutside current project")
            return
        lines = [f"path: {path}", f"type: {'dir' if path.is_dir() else 'file'}"]
        if path.is_file():
            lines.append(f"size: {self._format_bytes(path.stat().st_size)}")
            if path.suffix.lower() in {".yaml", ".yml", ".json", ".txt", ".md"}:
                try:
                    lines.extend(["", path.read_text(encoding="utf-8", errors="replace")[:20000]])
                except Exception as exc:
                    lines.append(f"cannot read file: {exc}")
        else:
            lines.append(f"size: {self._format_bytes(self._dir_size(path, max_files=2000))}")
        detail.setPlainText("\n".join(lines))

    def _tr(self, value: str) -> str:
        language = "zh" if self.title.text() == "属性" else "en"
        return text(value, language)

    def _dir_size(self, path: Path, *, max_files: int = 10000) -> int:
        if not path.exists():
            return 0
        if path.is_file():
            return path.stat().st_size
        total = 0
        count = 0
        for item in path.rglob("*"):
            if count >= max_files:
                break
            try:
                if item.is_file():
                    total += item.stat().st_size
                    count += 1
            except Exception:
                continue
        return total

    def _ascii_tree(self, root: Path, *, max_depth: int = 4, max_items: int = 160) -> list[str]:
        if not root.exists():
            return ["<missing>"]
        lines = [f"{root.name}/"]
        count = 0

        def walk(path: Path, prefix: str, depth: int) -> None:
            nonlocal count
            if depth >= max_depth or count >= max_items:
                return
            try:
                children = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
            except Exception:
                return
            visible = children[: max(0, max_items - count)]
            for index, child in enumerate(visible):
                if count >= max_items:
                    break
                count += 1
                is_last = index == len(visible) - 1
                branch = "`-- " if is_last else "|-- "
                name = self._summarized_name(child)
                lines.append(f"{prefix}{branch}{name}")
                if child.is_dir() and not self._should_summarize_dir(child):
                    extension = "    " if is_last else "|   "
                    walk(child, prefix + extension, depth + 1)
            if len(children) > len(visible):
                lines.append(f"{prefix}`-- ... {len(children) - len(visible)} more")

        walk(root, "", 0)
        if count >= max_items:
            lines.append(f"... truncated at {max_items} items")
        return lines

    def _should_summarize_dir(self, path: Path) -> bool:
        parts = path.parts
        if "raw_sessions" in parts and path.name.startswith("session_"):
            return True
        if path.parent.name in {"exports", "merged", "merge", "merged_sessions"} and path.is_dir():
            return True
        if path.name.startswith(("merged", "merge_")) and path.is_dir():
            return True
        return False

    def _summarized_name(self, path: Path) -> str:
        if not path.is_dir() or not self._should_summarize_dir(path):
            return f"{path.name}/" if path.is_dir() else path.name
        files, dirs = self._child_counts(path)
        parts = []
        if dirs:
            parts.append(f"{dirs} dirs")
        if files:
            parts.append(f"{files} files")
        suffix = f" ({', '.join(parts)})" if parts else " (empty)"
        return f"{path.name}/{suffix}"

    def _child_counts(self, path: Path, *, max_items: int = 10000) -> tuple[int, int]:
        files = 0
        dirs = 0
        try:
            for index, item in enumerate(path.rglob("*")):
                if index >= max_items:
                    break
                if item.is_dir():
                    dirs += 1
                elif item.is_file():
                    files += 1
        except Exception:
            pass
        return files, dirs

    def _project_signature(self, root: Path, *, max_items: int = 2000) -> tuple[int, int, int]:
        if not root.exists():
            return (0, 0, 0)
        total_size = 0
        latest_mtime = int(root.stat().st_mtime_ns)
        count = 1
        try:
            iterator = root.rglob("*")
            for item in iterator:
                if count >= max_items:
                    break
                try:
                    stat = item.stat()
                except Exception:
                    continue
                count += 1
                latest_mtime = max(latest_mtime, int(stat.st_mtime_ns))
                if item.is_file():
                    total_size += int(stat.st_size)
        except Exception:
            pass
        return (count, total_size, latest_mtime)

    def _watch_paths(self, root: Path, *, max_dirs: int = 80) -> list[str]:
        if not root.exists():
            return []
        paths = [str(root)]
        try:
            for item in root.rglob("*"):
                if len(paths) >= max_dirs:
                    break
                if item.is_dir():
                    paths.append(str(item))
        except Exception:
            pass
        return paths

    def _reset_watches(self, paths: list[str]) -> None:
        current = [*self.watcher.directories(), *self.watcher.files()]
        if current:
            self.watcher.removePaths(current)
        existing = [path for path in paths if Path(path).exists()]
        if existing:
            self.watcher.addPaths(existing)

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
            if size < 1024.0:
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
            size /= 1024.0
        return f"{size:.1f} PB"
