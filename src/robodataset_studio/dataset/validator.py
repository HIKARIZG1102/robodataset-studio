from __future__ import annotations

from pathlib import Path

import numpy as np


REQUIRED_FIELDS = ["rgb_static", "rgb_wrist", "robot_obs", "rel_actions", "actions"]


class DatasetValidator:
    def scan_npz(self, episodes_dir: Path) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for path in sorted(episodes_dir.glob("episode_*.npz")):
            row: dict[str, object] = {"path": str(path), "name": path.name, "size_mb": round(path.stat().st_size / 1024 / 1024, 3)}
            try:
                with np.load(path, allow_pickle=True) as data:
                    fields = list(data.files)
                    missing = [f for f in REQUIRED_FIELDS if f not in fields]
                    row["fields"] = ", ".join(fields)
                    row["missing"] = ", ".join(missing)
                    row["steps"] = int(data[fields[0]].shape[0]) if fields else 0
                    row["status"] = "ok" if not missing else "warning"
            except Exception as exc:
                row["fields"] = ""
                row["missing"] = str(exc)
                row["steps"] = 0
                row["status"] = "error"
            rows.append(row)
        return rows

