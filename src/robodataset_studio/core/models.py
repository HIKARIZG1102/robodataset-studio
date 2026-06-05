from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


def now_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


@dataclass
class ProjectState:
    task_name: str = "catch_the_satellite"
    version: str = "v1"
    dataset_root: Path = Path.home() / "robot_datasets" / "robodataset_studio"
    operator: str = ""
    environment: str = "physical"
    current_session: str = field(default_factory=lambda: now_id("session"))
    selected_nodes: list[str] = field(default_factory=list)
    selected_streams: list[dict[str, Any]] = field(default_factory=list)
    collection_config: dict[str, Any] = field(default_factory=dict)
    conversion_outputs: list[Path] = field(default_factory=list)
    upload_targets: list[str] = field(default_factory=list)

    @property
    def raw_session_dir(self) -> Path:
        return (
            self.dataset_root
            / "raw_sessions"
            / self.task_name
            / self.version
            / self.current_session
        )

    @property
    def episodes_dir(self) -> Path:
        return self.raw_session_dir / "training"

    @property
    def merged_dir(self) -> Path:
        return self.dataset_root / "merged_calvin" / self.task_name / self.version / "training"


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
