from __future__ import annotations

import re
import shutil
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
    ) -> dict[str, Any]:
        planner = CalvinMergePlanner()
        plan = planner.build_plan(raw_root, split=split)
        selected = [row for row in plan if row["episodes"] and (include_incomplete or row["status"] == "ready")]
        if not selected:
            raise RuntimeError(f"No raw episodes found under {raw_root}")

        merged_training_dir.mkdir(parents=True, exist_ok=True)
        copied: list[dict[str, Any]] = []
        next_index = 0
        for row in selected:
            session_dir = Path(str(row["path"]))
            split_dir = session_dir / split
            for source in sorted(split_dir.glob("episode_*.npz"), key=planner._episode_index):
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

        annotation_sources = [
            Path(str(row["path"])) / split / "lang_annotations" / "auto_lang_ann.npy"
            for row in selected
            if row.get("has_annotations")
        ]
        annotation_target = None
        if annotation_sources:
            annotation_target = merged_training_dir / "lang_annotations" / "auto_lang_ann.npy"
            annotation_target.parent.mkdir(parents=True, exist_ok=True)
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
