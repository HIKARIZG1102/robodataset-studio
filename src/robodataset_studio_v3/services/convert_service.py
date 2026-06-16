from __future__ import annotations

from pathlib import Path
from typing import Any

from robodataset_studio_v3.dataset.converter import Hdf5Converter
from robodataset_studio_v3.dataset.merge_plan import CalvinMergePlanner, CalvinSessionMerger
from robodataset_studio_v3.services.task_service import task_service


class ConvertService:
    def __init__(self) -> None:
        self.planner = CalvinMergePlanner()
        self.merger = CalvinSessionMerger()
        self.converter = Hdf5Converter()

    def scan(self, root: str) -> dict[str, Any]:
        base = Path(root).expanduser()
        plan = self.planner.build_plan(base, split="training")
        sessions = [
            {
                "name": str(row.get("session", "")),
                "path": str(row.get("path", "")),
                "episode_count": int(row.get("episodes", 0) or 0),
                "status": str(row.get("status", "")),
                "has_annotations": bool(row.get("has_annotations", False)),
            }
            for row in plan
        ]
        result = {"root": str(base), "exists": base.exists(), "sessions": sessions}
        task = task_service.run_instant("convert_scan", f"scanned sessions under {base}", result)
        return {"task_id": task.task_id, "result": result}

    def merge(self, sessions: list[str], output_dir: str) -> dict[str, Any]:
        output = Path(output_dir).expanduser()
        raw_root = self._raw_root_from_sessions(sessions)
        manifest = self.merger.merge(raw_root, output / "training", selected_sessions=sessions)
        result = {"sessions": sessions, "output_dir": str(output), "manifest": manifest}
        task = task_service.run_instant("convert_merge", "merged sessions", result)
        return {"task_id": task.task_id, "result": result}

    def hdf5(self, sessions: list[str], output_dir: str) -> dict[str, Any]:
        output = Path(output_dir).expanduser()
        output.mkdir(parents=True, exist_ok=True)
        episode_paths = []
        for session in sessions:
            session_path = Path(session).expanduser()
            episode_paths.extend(sorted((session_path / "training").glob("episode_*.npz")))
        if not episode_paths:
            raise RuntimeError("No episode_*.npz files found for selected sessions")
        output_path = output / "calvin.hdf5"
        self.converter.convert_episode_paths(episode_paths, output_path)
        result = {"sessions": sessions, "output_dir": str(output), "hdf5_path": str(output_path), "episode_count": len(episode_paths)}
        task = task_service.run_instant("convert_hdf5", "converted selected sessions to HDF5", result)
        return {"task_id": task.task_id, "result": result}

    def _raw_root_from_sessions(self, sessions: list[str]) -> Path:
        if not sessions:
            raise RuntimeError("No sessions selected")
        first = Path(sessions[0]).expanduser()
        if first.name.startswith("session_"):
            return first.parent
        return first.parent


convert_service = ConvertService()
