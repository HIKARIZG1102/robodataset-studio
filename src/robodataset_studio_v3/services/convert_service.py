from __future__ import annotations

from pathlib import Path
from threading import Thread
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

    def merge(self, sessions: list[str], output_dir: str, output_name: str = "") -> dict[str, Any]:
        task = task_service.create_task("convert_merge", "merge started")
        Thread(target=self._merge_worker, args=(task.task_id, sessions, output_dir, output_name), daemon=True).start()
        return {"task_id": task.task_id, "sessions": sessions, "output_dir": output_dir, "output_name": output_name}

    def hdf5(self, sessions: list[str], output_dir: str, output_name: str = "") -> dict[str, Any]:
        task = task_service.create_task("convert_hdf5", "HDF5 conversion started")
        Thread(target=self._hdf5_worker, args=(task.task_id, sessions, output_dir, output_name), daemon=True).start()
        return {"task_id": task.task_id, "sessions": sessions, "output_dir": output_dir, "output_name": output_name}

    def _merge_worker(self, task_id: str, sessions: list[str], output_dir: str, output_name: str = "") -> None:
        try:
            result = self._merge_sync(sessions, output_dir, output_name)
            task_service.complete_task(task_id, message="merged sessions", result=result)
        except Exception as exc:
            task_service.fail_task(task_id, message="merge failed", error=str(exc))

    def _hdf5_worker(self, task_id: str, sessions: list[str], output_dir: str, output_name: str = "") -> None:
        try:
            result = self._hdf5_sync(sessions, output_dir, output_name)
            task_service.complete_task(task_id, message="converted selected sessions to HDF5", result=result)
        except Exception as exc:
            task_service.fail_task(task_id, message="HDF5 conversion failed", error=str(exc))

    def _merge_sync(self, sessions: list[str], output_dir: str, output_name: str = "") -> dict[str, Any]:
        output = Path(output_dir).expanduser()
        raw_root = self._raw_root_from_sessions(sessions)
        target_root = self._unique_path(output / self._safe_name(output_name, "merged_calvin"))
        manifest = self.merger.merge(raw_root, target_root / "training", selected_sessions=sessions)
        return {"sessions": sessions, "output_dir": str(output), "merged_dir": str(target_root), "manifest": manifest}

    def _hdf5_sync(self, sessions: list[str], output_dir: str, output_name: str = "") -> dict[str, Any]:
        output = Path(output_dir).expanduser()
        output.mkdir(parents=True, exist_ok=True)
        episode_paths = []
        for session in sessions:
            session_path = Path(session).expanduser()
            episode_paths.extend(sorted((session_path / "training").glob("episode_*.npz")))
        if not episode_paths:
            raise RuntimeError("No episode_*.npz files found for selected sessions")
        output_path = self._unique_path(output / self._safe_hdf5_name(output_name))
        self.converter.convert_episode_paths(episode_paths, output_path)
        return {"sessions": sessions, "output_dir": str(output), "hdf5_path": str(output_path), "episode_count": len(episode_paths)}

    def _raw_root_from_sessions(self, sessions: list[str]) -> Path:
        if not sessions:
            raise RuntimeError("No sessions selected")
        first = Path(sessions[0]).expanduser()
        if first.name.startswith("session_"):
            return first.parent
        return first.parent

    def _safe_name(self, value: str, default: str) -> str:
        text = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in value.strip())
        return text.strip("._-") or default

    def _safe_hdf5_name(self, value: str) -> str:
        name = self._safe_name(value, "calvin")
        if not name.endswith((".hdf5", ".h5")):
            name = f"{name}.hdf5"
        return name

    def _unique_path(self, path: Path) -> Path:
        if not path.exists():
            return path
        suffix = 2
        while True:
            candidate = path.with_name(f"{path.stem}_{suffix}{path.suffix}")
            if not candidate.exists():
                return candidate
            suffix += 1


convert_service = ConvertService()
