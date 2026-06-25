from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import yaml
import h5py

from robodataset_studio_v3.dataset.validator import DatasetValidator
from robodataset_studio_v3.services.task_service import task_service


class ReviewService:
    def __init__(self) -> None:
        self.validator = DatasetValidator()

    def scan_session(self, session_dir: str) -> dict[str, Any]:
        root = self._resolve_session_dir(Path(session_dir).expanduser())
        training = root / "training"
        marks = self._load_marks(root)
        rows = self.validator.list_npz(training) if training.exists() else []
        for row in rows:
            row["mark"] = marks.get(str(row.get("name", "")), "unmarked")
        result = {
            "session_dir": str(root),
            "training_dir": str(training),
            "episode_count": len(rows),
            "episodes": rows,
            "has_dataset_config": (root / "dataset_config.yaml").exists() or (root / "collection_config.yaml").exists(),
            "marks": marks,
            "quality_report": self.validator.quality_report(rows, marks),
        }
        task = task_service.run_instant("review_scan", f"scanned session {root}", result)
        return {"task_id": task.task_id, "result": result}

    def check_session(self, session_dir: str) -> dict[str, Any]:
        root = self._resolve_session_dir(Path(session_dir).expanduser())
        config = self._load_session_config(root)
        marks = self._load_marks(root)
        rows = self.validator.scan_npz(root / "training", config)
        for row in rows:
            row["mark"] = marks.get(str(row.get("name", "")), "unmarked")
        report = self.validator.quality_report(rows, marks)
        result = {
            "session_dir": str(root),
            "training_dir": str(root / "training"),
            "total": report["total"],
            "valid": report["by_status"]["ok"],
            "invalid": report["by_status"]["warning"] + report["by_status"]["error"],
            "episodes": rows,
            "quality_report": report,
            "summary": report,
        }
        task = task_service.run_instant("review_check", f"checked session {session_dir}", result)
        return {"task_id": task.task_id, "result": result}

    def mark(self, session_dir: str, episode: str, status: str) -> dict[str, Any]:
        root = self._resolve_session_dir(Path(session_dir).expanduser())
        episode = Path(episode).name
        mark = status if status in {"good", "bad", "uncertain", "unmarked"} else "unmarked"
        marks = self._load_marks(root)
        marks[episode] = mark
        marks_path = self._save_marks(root, marks)
        return {"marks_file": str(marks_path), "session_dir": str(root), "episode": episode, "status": status}

    def episode_detail(self, session_dir: str, episode: str) -> dict[str, Any]:
        root = self._resolve_session_dir(Path(session_dir).expanduser())
        path = self._episode_path(root, episode)
        config = self._load_session_config(root)
        marks = self._load_marks(root)
        fields: list[dict[str, Any]] = []
        metadata: dict[str, Any] = {}
        quality_issues: list[str] = []
        with np.load(path, allow_pickle=True) as data:
            quality_issues = self.validator.quality_issues(
                data,
                self.validator.image_fields(config),
                self.validator.action_dim(config),
            )
            for key in data.files:
                value = data[key]
                field: dict[str, Any] = {
                    "name": key,
                    "shape": list(value.shape),
                    "dtype": str(value.dtype),
                    "size": int(value.size),
                }
                if np.issubdtype(value.dtype, np.number) and value.size:
                    finite = value[np.isfinite(value)]
                    if finite.size:
                        field.update(
                            {
                                "min": float(np.min(finite)),
                                "max": float(np.max(finite)),
                                "mean": float(np.mean(finite)),
                            }
                        )
                if key in {"episode_metadata", "collection_config", "task_info", "environment_info", "robot_info", "stream_schema"}:
                    metadata[key] = self._metadata_value(value)
                fields.append(field)
        missing = [field for field in self.validator.required_fields(config) if field not in {item["name"] for item in fields}]
        return {
            "session_dir": str(root),
            "episode": path.name,
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "size_mb": round(path.stat().st_size / 1024 / 1024, 3),
            "mark": marks.get(path.name, "unmarked"),
            "status": "error" if missing else "warning" if quality_issues else "ok",
            "missing": missing,
            "quality_issues": quality_issues,
            "fields": fields,
            "metadata": metadata,
            "description": self.validator.describe_npz(path, config),
        }

    def trash_episode(self, session_dir: str, episode: str) -> dict[str, Any]:
        root = self._resolve_session_dir(Path(session_dir).expanduser())
        path = self._episode_path(root, episode)
        trash_dir = root / "review_deleted"
        trash_dir.mkdir(parents=True, exist_ok=True)
        target = trash_dir / path.name
        suffix = 1
        while target.exists():
            target = trash_dir / f"{path.stem}_{suffix}{path.suffix}"
            suffix += 1
        shutil.move(str(path), str(target))
        marks = self._load_marks(root)
        marks.pop(path.name, None)
        self._save_marks(root, marks)
        return {"session_dir": str(root), "episode": path.name, "trashed_path": str(target)}

    def quality_report(self, session_dir: str) -> dict[str, Any]:
        root = self._resolve_session_dir(Path(session_dir).expanduser())
        config = self._load_session_config(root)
        rows = self.validator.scan_npz(root / "training", config)
        marks = self._load_marks(root)
        report = self.validator.quality_report(rows, marks)
        output = root / "quality_report.json"
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result = {"session_dir": str(root), "path": str(output), "report": report}
        task = task_service.run_instant("review_report", f"exported quality report {output}", result)
        return {"task_id": task.task_id, "result": result}

    def load_ai_report(self, session_dir: str) -> dict[str, Any]:
        root = self._resolve_session_dir(Path(session_dir).expanduser())
        path = self._ai_report_path(root)
        text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        return {"session_dir": str(root), "path": str(path), "exists": path.exists(), "content": text}

    def save_ai_report(self, session_dir: str, content: str) -> dict[str, Any]:
        root = self._resolve_session_dir(Path(session_dir).expanduser())
        path = self._ai_report_path(root)
        path.write_text(content.rstrip() + "\n", encoding="utf-8")
        result = {"session_dir": str(root), "path": str(path), "exists": True, "content": content}
        task = task_service.run_instant("review_ai_report", f"saved AI review report {path}", result)
        return {"task_id": task.task_id, "result": result}

    def inspect_hdf5(self, hdf5_path: str) -> dict[str, Any]:
        path = Path(hdf5_path).expanduser()
        result = {"path": str(path), "summary_text": self.validator.describe_hdf5(path)}
        task = task_service.run_instant("hdf5_inspect", f"inspected HDF5 {path}", result)
        return {"task_id": task.task_id, "result": result}

    def check_hdf5(self, hdf5_path: str) -> dict[str, Any]:
        path = Path(hdf5_path).expanduser()
        rows = self.validator.check_hdf5(path, self._load_hdf5_config(path))
        result = {"path": str(path), "rows": rows, "summary_text": self.validator.hdf5_check_summary(path, rows)}
        task = task_service.run_instant("hdf5_check", f"checked HDF5 {path}", result)
        return {"task_id": task.task_id, "result": result}

    def scan_layout(self, folder: str) -> dict[str, Any]:
        root = Path(folder).expanduser()
        rows: list[dict[str, object]] = []
        if not root.exists():
            rows.append({"path": str(root), "status": "error", "issue": "missing_root", "detail": "selected path does not exist"})
        elif root.is_file():
            rows.append({"path": str(root), "status": "error", "issue": "not_a_directory", "detail": "layout scan expects a folder"})
        else:
            session_dirs = self.validator._find_session_dirs(root)
            for session_dir in session_dirs:
                training = session_dir / "training"
                episodes = sorted(training.glob("episode_*.npz"))
                area = "merged_calvin" if "merged_calvin" in session_dir.parts else "raw_sessions"
                rows.append(
                    {
                        "path": str(session_dir),
                        "status": "ok" if episodes else "warning",
                        "issue": "-",
                        "detail": (
                            f"area={area} npz={len(episodes)} "
                            f"hdf5={any(session_dir.glob('*.hdf5')) or any(session_dir.glob('*.h5'))} "
                            f"manifest={(session_dir / 'merge_manifest.json').exists()}"
                        ),
                    }
                )
            for hdf5_path in sorted(root.glob("**/*.hdf5")) + sorted(root.glob("**/*.h5")):
                rows.append({"path": str(hdf5_path), "status": "ok", "issue": "-", "detail": "HDF5 file"})
            if not rows:
                rows.append({"path": str(root), "status": "warning", "issue": "empty_layout", "detail": "no CALVIN artifacts found"})
        result = {"folder": str(root), "rows": rows}
        task = task_service.run_instant("layout_scan", f"scanned layout {root}", result)
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

    def _load_hdf5_config(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            with h5py.File(path, "r") as h5:
                metadata = h5.get("metadata")
                raw = metadata.attrs.get("config_yaml", "") if metadata is not None else ""
            text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
            data = yaml.safe_load(text) if text.strip() else {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _resolve_session_dir(self, path: Path) -> Path:
        if path.name.startswith("session_"):
            return path
        candidates = sorted([item for item in path.glob("session_*") if item.is_dir()])
        if candidates:
            return candidates[-1]
        return path

    def _episode_path(self, root: Path, episode: str) -> Path:
        episode_name = Path(episode).name
        path = root / "training" / episode_name
        if not path.exists():
            raise FileNotFoundError(f"episode not found: {episode_name}")
        return path

    def _ai_report_path(self, root: Path) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        return root / "ai_session_report.md"

    def _metadata_value(self, value: np.ndarray) -> Any:
        try:
            if value.shape == ():
                raw = value.item()
            else:
                raw = value.tolist()
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            if isinstance(raw, str):
                try:
                    return json.loads(raw)
                except Exception:
                    return raw
            return raw
        except Exception as exc:
            return f"cannot parse metadata: {exc}"

    def _load_marks(self, root: Path) -> dict[str, str]:
        json_path = root / "review_marks.json"
        if json_path.exists():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                marks = data.get("marks", data) if isinstance(data, dict) else {}
                return self._clean_marks(marks)
            except Exception:
                return {}
        yaml_path = root / "review" / "review_marks.yaml"
        if yaml_path.exists():
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            return self._clean_marks(data)
        return {}

    def _save_marks(self, root: Path, marks: dict[str, str]) -> Path:
        path = root / "review_marks.json"
        payload = {
            "schema": "robodataset_studio.review_marks.v1",
            "session_root": str(root),
            "marks": dict(sorted(self._clean_marks(marks).items())),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def _clean_marks(self, data: Any) -> dict[str, str]:
        allowed = {"good", "bad", "uncertain", "unmarked", "keep", "warning", "reject", ""}
        mapping = {"keep": "good", "warning": "uncertain", "reject": "bad", "": "unmarked"}
        if not isinstance(data, dict):
            return {}
        cleaned: dict[str, str] = {}
        for key, value in data.items():
            mark = str(value)
            if mark not in allowed:
                mark = "unmarked"
            cleaned[str(key)] = mapping.get(mark, mark)
        return cleaned


review_service = ReviewService()
