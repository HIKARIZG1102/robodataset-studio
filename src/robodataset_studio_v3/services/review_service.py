from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from robodataset_studio_v3.dataset.validator import DatasetValidator
from robodataset_studio_v3.services.task_service import task_service


class ReviewService:
    def __init__(self) -> None:
        self.validator = DatasetValidator()

    def scan_session(self, session_dir: str) -> dict[str, Any]:
        root = self._resolve_session_dir(Path(session_dir).expanduser())
        training = root / "training"
        episodes = sorted(training.glob("episode_*.npz")) if training.exists() else []
        marks = self._load_marks(root)
        result = {
            "session_dir": str(root),
            "training_dir": str(training),
            "episode_count": len(episodes),
            "episodes": [
                {
                    "name": path.name,
                    "path": str(path),
                    "size_bytes": path.stat().st_size,
                    "mark": marks.get(path.name, ""),
                }
                for path in episodes
            ],
            "has_dataset_config": (root / "dataset_config.yaml").exists() or (root / "collection_config.yaml").exists(),
            "marks": marks,
        }
        task = task_service.run_instant("review_scan", f"scanned session {root}", result)
        return {"task_id": task.task_id, "result": result}

    def check_session(self, session_dir: str) -> dict[str, Any]:
        root = self._resolve_session_dir(Path(session_dir).expanduser())
        config = self._load_session_config(root)
        rows = self.validator.scan_npz(root / "training", config)
        report = self.validator.quality_report(rows, self._load_marks(root))
        issues = [row for row in rows if row.get("status") != "ok"]
        result = {
            "session_dir": str(root),
            "total": report["total"],
            "valid": report["by_status"]["ok"],
            "invalid": report["by_status"]["warning"] + report["by_status"]["error"],
            "summary": report,
            "issues": issues,
        }
        task = task_service.run_instant("review_check", f"checked session {session_dir}", result)
        return {"task_id": task.task_id, "result": result}

    def mark(self, session_dir: str, episode: str, status: str) -> dict[str, Any]:
        root = self._resolve_session_dir(Path(session_dir).expanduser())
        review_dir = root / "review"
        review_dir.mkdir(exist_ok=True)
        marks_path = review_dir / "review_marks.yaml"
        marks = yaml.safe_load(marks_path.read_text(encoding="utf-8")) if marks_path.exists() else {}
        if not isinstance(marks, dict):
            marks = {}
        marks[episode] = status
        marks_path.write_text(yaml.safe_dump(marks, sort_keys=False, allow_unicode=True), encoding="utf-8")
        return {"marks_file": str(marks_path), "session_dir": str(root), "episode": episode, "status": status}

    def check_hdf5(self, hdf5_path: str) -> dict[str, Any]:
        path = Path(hdf5_path).expanduser()
        rows = self.validator.check_hdf5(path)
        result = {"path": str(path), "rows": rows, "summary_text": self.validator.hdf5_check_summary(path, rows)}
        task = task_service.run_instant("hdf5_check", f"checked HDF5 {path}", result)
        return {"task_id": task.task_id, "result": result}

    def check_layout(self, folder: str) -> dict[str, Any]:
        root = Path(folder).expanduser()
        rows = self.validator.check_calvin_layout(root)
        result = {"folder": str(root), "rows": rows, "ok": all(str(row.get("status")) != "error" for row in rows)}
        task = task_service.run_instant("layout_check", f"checked layout {root}", result)
        return {"task_id": task.task_id, "result": result}

    def _check_npz(self, path: Path) -> list[str]:
        issues = []
        try:
            import numpy as np

            with np.load(path, allow_pickle=False) as data:
                if not data.files:
                    return ["empty npz"]
                for key in data.files:
                    value = data[key]
                    if value.size == 0:
                        issues.append(f"{key}: empty array")
                    if np.issubdtype(value.dtype, np.number) and not np.isfinite(value).all():
                        issues.append(f"{key}: contains NaN or Inf")
        except Exception as exc:
            issues.append(f"cannot read npz: {exc}")
        return issues

    def _load_session_config(self, root: Path) -> dict[str, Any]:
        for name in ("dataset_config.yaml", "collection_config.yaml"):
            path = root / name
            if path.exists():
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
        return {}

    def _resolve_session_dir(self, path: Path) -> Path:
        if path.name.startswith("session_"):
            return path
        candidates = sorted([item for item in path.glob("session_*") if item.is_dir()])
        if candidates:
            return candidates[-1]
        return path

    def _load_marks(self, root: Path) -> dict[str, str]:
        path = root / "review" / "review_marks.yaml"
        if not path.exists():
            return {}
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return {str(key): str(value) for key, value in data.items()} if isinstance(data, dict) else {}


review_service = ReviewService()
