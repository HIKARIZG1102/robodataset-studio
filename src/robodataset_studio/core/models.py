from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def now_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


@dataclass
class ProjectState:
    task_name: str = ""
    version: str = ""
    dataset_root: Path = Path("")
    operator: str = ""
    environment: str = ""
    current_session: str = field(default_factory=lambda: now_id("session"))
    selected_nodes: list[str] = field(default_factory=list)
    selected_streams: list[dict[str, Any]] = field(default_factory=list)
    collection_config: dict[str, Any] = field(default_factory=dict)
    conversion_outputs: list[Path] = field(default_factory=list)
    upload_targets: list[str] = field(default_factory=list)
    language: str = "zh"
    ai_enabled: bool = False
    ai_base_url: str = ""
    ai_model: str = ""
    ai_api_key: str = ""
    ui_state: dict[str, Any] = field(default_factory=dict)

    @property
    def effective_task_name(self) -> str:
        return self.task_name or "untitled_project"

    @property
    def effective_version(self) -> str:
        return self.version or "v1"

    @property
    def effective_dataset_root(self) -> Path:
        if str(self.dataset_root) in {"", "."}:
            return project_root() / "robodataset"
        if self.dataset_root.is_absolute():
            return self.dataset_root
        return project_root() / self.dataset_root

    @property
    def raw_session_dir(self) -> Path:
        return (
            self.effective_dataset_root
            / "raw_sessions"
            / self.effective_task_name
            / self.effective_version
            / self.current_session
        )

    @property
    def episodes_dir(self) -> Path:
        return self.raw_session_dir / "training"

    @property
    def merged_dir(self) -> Path:
        return self.effective_dataset_root / "merged_calvin" / self.effective_task_name / self.effective_version / "training"


@dataclass
class ProcessRecord:
    process_id: str
    type: str
    command: list[str]
    owner_page: str
    process_group_id: str
    pid: int | None = None
    status: str = "starting"
    started_at: datetime = field(default_factory=datetime.now)
    ended_at: datetime | None = None
    stdout_tail: list[str] = field(default_factory=list)
    stderr_tail: list[str] = field(default_factory=list)

    def command_text(self) -> str:
        return " ".join(self.command)
