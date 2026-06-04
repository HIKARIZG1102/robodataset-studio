from __future__ import annotations

from pathlib import Path

import h5py
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

    def describe_npz(self, path: Path) -> str:
        lines = [f"file: {path}", f"size_mb: {path.stat().st_size / 1024 / 1024:.3f}"]
        try:
            with np.load(path, allow_pickle=True) as data:
                missing = [f for f in REQUIRED_FIELDS if f not in data.files]
                lines.append(f"status: {'ok' if not missing else 'warning'}")
                lines.append(f"missing_required: {', '.join(missing) if missing else '-'}")
                lines.append("")
                lines.append("fields:")
                for field in data.files:
                    value = data[field]
                    dtype = getattr(value, "dtype", "-")
                    shape = getattr(value, "shape", ())
                    lines.append(f"  {field}: shape={tuple(shape)} dtype={dtype}")
        except Exception as exc:
            lines.append("status: error")
            lines.append(f"error: {exc}")
        return "\n".join(lines)

    def describe_hdf5(self, path: Path) -> str:
        if not path.exists():
            return f"file: {path}\nstatus: missing"
        lines = [f"file: {path}", f"size_mb: {path.stat().st_size / 1024 / 1024:.3f}"]
        try:
            with h5py.File(path, "r") as h5:
                episodes = h5.get("episodes")
                episode_names = sorted(episodes.keys()) if episodes is not None else []
                lines.append(f"episodes: {len(episode_names)}")
                metadata = h5.get("metadata")
                if metadata is not None:
                    lines.append("")
                    lines.append("metadata attrs:")
                    for key, value in metadata.attrs.items():
                        text = str(value)
                        if len(text) > 180:
                            text = text[:177] + "..."
                        lines.append(f"  {key}: {text}")
                if episode_names:
                    lines.append("")
                    lines.append("first episode fields:")
                    first = episodes[episode_names[0]]
                    for field, dataset in first.items():
                        lines.append(f"  {field}: shape={tuple(dataset.shape)} dtype={dataset.dtype}")
        except Exception as exc:
            lines.append("status: error")
            lines.append(f"error: {exc}")
        return "\n".join(lines)
