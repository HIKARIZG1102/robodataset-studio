from __future__ import annotations

import re
from pathlib import Path


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

