from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from robodataset_studio_v3.services.task_service import task_service


class ReviewService:
    def scan_session(self, session_dir: str) -> dict[str, Any]:
        root = Path(session_dir).expanduser()
        training = root / "training"
        episodes = sorted(training.glob("episode_*.npz")) if training.exists() else []
        result = {
            "session_dir": str(root),
            "training_dir": str(training),
            "episode_count": len(episodes),
            "episodes": [str(path) for path in episodes],
            "has_dataset_config": (root / "dataset_config.yaml").exists() or (root / "collection_config.yaml").exists(),
        }
        task = task_service.run_instant("review_scan", f"scanned session {root}", result)
        return {"task_id": task.task_id, "result": result}

    def check_session(self, session_dir: str) -> dict[str, Any]:
        scan = self.scan_session(session_dir)["result"]
        issues = []
        valid = 0
        for episode in scan["episodes"]:
            episode_path = Path(episode)
            episode_issues = self._check_npz(episode_path)
            if episode_issues:
                issues.append({"episode": str(episode_path), "issues": episode_issues})
            else:
                valid += 1
        result = {
            "total": scan["episode_count"],
            "valid": valid,
            "invalid": len(issues),
            "issues": issues,
        }
        task = task_service.run_instant("review_check", f"checked session {session_dir}", result)
        return {"task_id": task.task_id, "result": result}

    def mark(self, session_dir: str, episode: str, status: str) -> dict[str, Any]:
        review_dir = Path(session_dir).expanduser() / "review"
        review_dir.mkdir(exist_ok=True)
        marks_path = review_dir / "review_marks.yaml"
        marks = yaml.safe_load(marks_path.read_text(encoding="utf-8")) if marks_path.exists() else {}
        if not isinstance(marks, dict):
            marks = {}
        marks[episode] = status
        marks_path.write_text(yaml.safe_dump(marks, sort_keys=False, allow_unicode=True), encoding="utf-8")
        return {"marks_file": str(marks_path), "episode": episode, "status": status}

    def check_hdf5(self, hdf5_path: str) -> dict[str, Any]:
        path = Path(hdf5_path).expanduser()
        if not path.exists():
            result = {"path": str(path), "ok": False, "error": "file not found"}
        else:
            try:
                import h5py

                with h5py.File(path, "r") as handle:
                    keys = list(handle.keys())
                result = {"path": str(path), "ok": True, "keys": keys, "total": len(keys), "valid": len(keys), "invalid": 0}
            except Exception as exc:
                result = {"path": str(path), "ok": False, "error": str(exc)}
        task = task_service.run_instant("hdf5_check", f"checked HDF5 {path}", result)
        return {"task_id": task.task_id, "result": result}

    def check_layout(self, folder: str) -> dict[str, Any]:
        root = Path(folder).expanduser()
        result = {
            "folder": str(root),
            "exists": root.exists(),
            "has_training": (root / "training").exists(),
            "has_dataset_config": (root / "dataset_config.yaml").exists() or (root / "collection_config.yaml").exists(),
            "episode_count": len(list((root / "training").glob("episode_*.npz"))) if (root / "training").exists() else 0,
        }
        result["ok"] = result["exists"] and result["has_training"] and result["episode_count"] > 0
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


review_service = ReviewService()
