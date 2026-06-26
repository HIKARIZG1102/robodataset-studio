from __future__ import annotations

import re
import shutil
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


EPISODE_RE = re.compile(r"episode_(\d+)\.npz$")


class CalvinMergePlanner:
    def build_plan(self, raw_root: Path, split: str = "training") -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        if not raw_root.exists():
            return rows
        for session_dir in sorted(path for path in raw_root.iterdir() if path.is_dir()):
            split_dir = session_dir / split
            episode_paths = sorted(split_dir.glob("episode_*.npz"), key=self._episode_index)
            ann_path = split_dir / "lang_annotations" / "auto_lang_ann.npy"
            rows.append(
                {
                    "session": session_dir.name,
                    "path": str(session_dir),
                    "split": split,
                    "episodes": len(episode_paths),
                    "has_annotations": ann_path.exists(),
                    "first_episode": episode_paths[0].name if episode_paths else "",
                    "last_episode": episode_paths[-1].name if episode_paths else "",
                    "status": "ready" if episode_paths and ann_path.exists() else "incomplete",
                }
            )
        return rows

    def _episode_index(self, path: Path) -> int:
        match = EPISODE_RE.match(path.name)
        return int(match.group(1)) if match else -1


class CalvinSessionMerger:
    def merge(
        self,
        raw_root: Path,
        merged_training_dir: Path,
        *,
        split: str = "training",
        include_incomplete: bool = True,
        selected_sessions: list[str] | None = None,
    ) -> dict[str, Any]:
        planner = CalvinMergePlanner()
        plan = planner.build_plan(raw_root, split=split)
        selected_names = {str(session) for session in selected_sessions or []}
        selected = [
            row
            for row in plan
            if row["episodes"]
            and (include_incomplete or row["status"] == "ready")
            and (not selected_names or row["session"] in selected_names or row["path"] in selected_names)
        ]
        if not selected:
            raise RuntimeError(f"No raw episodes found under {raw_root}")

        merged_training_dir.mkdir(parents=True, exist_ok=True)
        for stale_episode in merged_training_dir.glob("episode_*.npz"):
            stale_episode.unlink()
        stale_annotation = merged_training_dir / "lang_annotations" / "auto_lang_ann.npy"
        if stale_annotation.exists():
            stale_annotation.unlink()
        copied: list[dict[str, Any]] = []
        old_to_new_by_session: dict[str, dict[int, int]] = {}
        next_index = 0
        for row in selected:
            session_dir = Path(str(row["path"]))
            split_dir = session_dir / split
            old_to_new: dict[int, int] = {}
            for source in sorted(split_dir.glob("episode_*.npz"), key=planner._episode_index):
                old_to_new[planner._episode_index(source)] = next_index
                target_name = f"episode_{next_index:07d}.npz"
                target = merged_training_dir / target_name
                shutil.copy2(source, target)
                copied.append(
                    {
                        "source_session": row["session"],
                        "source": str(source),
                        "target": str(target),
                        "target_episode": target_name,
                    }
                )
                next_index += 1
            old_to_new_by_session[str(row["session"])] = old_to_new

        annotation_sources = []
        annotations = []
        for row in selected:
            if not row.get("has_annotations"):
                continue
            source = Path(str(row["path"])) / split / "lang_annotations" / "auto_lang_ann.npy"
            annotation_sources.append(source)
            try:
                annotations.append((row, self._load_annotations(source)))
            except Exception:
                annotations = []
                break
        annotation_target = None
        if annotation_sources:
            annotation_target = merged_training_dir / "lang_annotations" / "auto_lang_ann.npy"
            annotation_target.parent.mkdir(parents=True, exist_ok=True)
            merged_annotations = self._merge_annotations(annotations, old_to_new_by_session)
            if merged_annotations:
                np.save(annotation_target, merged_annotations, allow_pickle=True)
            else:
                shutil.copy2(annotation_sources[0], annotation_target)

        manifest = {
            "schema": "robodataset_studio.calvin_merge_manifest.v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "raw_root": str(raw_root),
            "merged_training_dir": str(merged_training_dir),
            "split": split,
            "session_count": len(selected),
            "episode_count": len(copied),
            "annotation_source": str(annotation_sources[0]) if annotation_sources else "",
            "annotation_target": str(annotation_target) if annotation_target else "",
            "episodes": copied,
        }
        manifest_path = merged_training_dir.parent / "merge_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return manifest

    def _load_annotations(self, path: Path) -> dict[str, Any]:
        data = np.load(path, allow_pickle=True)
        if isinstance(data, np.ndarray) and data.shape == ():
            data = data.item()
        return data if isinstance(data, dict) else {}

    def _annotation_intervals(self, annotations: dict[str, Any]) -> tuple[str, np.ndarray] | None:
        info = annotations.get("info", {})
        if not isinstance(info, dict):
            return None
        for key in ("indx", "indices", "episode_index"):
            if key not in info:
                continue
            intervals = np.asarray(info[key], dtype=np.int64)
            if intervals.ndim == 2 and intervals.shape[1] == 2:
                return key, intervals
        return None

    def _merge_annotations(
        self,
        annotations_by_row: list[tuple[dict[str, object], dict[str, Any]]],
        old_to_new_by_session: dict[str, dict[int, int]],
    ) -> dict[str, Any] | None:
        if not annotations_by_row:
            return None
        merged_intervals: list[list[int]] = []
        merged_language: dict[str, list[Any]] = {}
        interval_key = "indx"

        for row, annotations in annotations_by_row:
            interval_data = self._annotation_intervals(annotations)
            if interval_data is None:
                return None
            interval_key, intervals = interval_data
            language = annotations.get("language", {})
            if not isinstance(language, dict):
                language = {}
            old_to_new = old_to_new_by_session.get(str(row["session"]), {})
            kept_annotation_indices: list[int] = []
            for ann_idx, interval in enumerate(intervals):
                start, end = int(interval[0]), int(interval[1])
                mapped = [old_to_new[index] for index in range(start, end + 1) if index in old_to_new]
                if not mapped:
                    continue
                merged_intervals.append([min(mapped), max(mapped)])
                kept_annotation_indices.append(ann_idx)
            for key, values in language.items():
                arr = np.asarray(values)
                if arr.ndim > 0 and len(arr) == len(intervals):
                    merged_language.setdefault(key, []).extend(arr[kept_annotation_indices].tolist())
                elif len(annotations_by_row) == 1:
                    merged_language[key] = arr.tolist() if arr.ndim > 0 else [arr.item()]

        if not merged_intervals:
            return None
        return {
            "info": {interval_key: np.asarray(merged_intervals, dtype=np.int64)},
            "language": {key: np.asarray(values) for key, values in merged_language.items()},
        }
