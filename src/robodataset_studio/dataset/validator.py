from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np


REQUIRED_FIELDS = ["rgb_static", "rgb_wrist", "robot_obs", "rel_actions", "actions"]
IMAGE_FIELDS = ["rgb_static", "rgb_wrist"]
ACTION_DIM = 7
METADATA_FIELDS = {
    "episode_metadata",
    "collection_config",
    "task_info",
    "environment_info",
    "robot_info",
    "stream_schema",
}


class DatasetValidator:
    def scan_npz(self, episodes_dir: Path, config: dict[str, Any] | None = None) -> list[dict[str, object]]:
        required_fields = self.required_fields(config)
        image_fields = self.image_fields(config)
        action_dim = self.action_dim(config)
        rows: list[dict[str, object]] = []
        for path in sorted(episodes_dir.glob("episode_*.npz")):
            row: dict[str, object] = {"path": str(path), "name": path.name, "size_mb": round(path.stat().st_size / 1024 / 1024, 3)}
            try:
                with np.load(path, allow_pickle=True) as data:
                    fields = list(data.files)
                    missing = [f for f in required_fields if f not in fields]
                    row["fields"] = ", ".join(fields)
                    row["missing"] = ", ".join(missing)
                    row["steps"] = self._infer_transition_steps(data, fields)
                    issues = self.quality_issues(data, image_fields, action_dim)
                    row["quality"] = ", ".join(issues) if issues else "-"
                    row["status"] = "error" if any(issue.startswith("nan_or_inf") for issue in issues) else "warning" if missing or issues else "ok"
            except Exception as exc:
                row["fields"] = ""
                row["missing"] = str(exc)
                row["steps"] = 0
                row["quality"] = str(exc)
                row["status"] = "error"
            rows.append(row)
        return rows

    def quality_report(self, rows: list[dict[str, object]], marks: dict[str, str] | None = None) -> dict[str, Any]:
        marks = marks or {}
        by_status = {"ok": 0, "warning": 0, "error": 0}
        issue_counts: dict[str, int] = {}
        mark_counts: dict[str, int] = {}
        episodes = []
        for row in rows:
            name = str(row.get("name", ""))
            status = str(row.get("status", ""))
            if status in by_status:
                by_status[status] += 1
            quality = str(row.get("quality", "") or "")
            issues = [issue.strip() for issue in quality.split(",") if issue.strip() and issue.strip() != "-"]
            for issue in issues:
                issue_counts[issue] = issue_counts.get(issue, 0) + 1
            mark = marks.get(name, "unmarked")
            mark_counts[mark] = mark_counts.get(mark, 0) + 1
            episodes.append(
                {
                    "name": name,
                    "path": row.get("path", ""),
                    "status": status,
                    "quality_issues": issues,
                    "missing": str(row.get("missing", "")),
                    "mark": mark,
                }
            )
        return {
            "total": len(rows),
            "by_status": by_status,
            "issue_counts": dict(sorted(issue_counts.items())),
            "mark_counts": dict(sorted(mark_counts.items())),
            "episodes": episodes,
        }

    def quality_issues(
        self,
        data: np.lib.npyio.NpzFile,
        image_fields: list[str] | None = None,
        action_dim: int | None = None,
    ) -> list[str]:
        image_fields = image_fields or IMAGE_FIELDS
        expected_action_dim = int(action_dim or ACTION_DIM)
        issues: list[str] = []
        for field in image_fields:
            if field in data.files:
                image = data[field]
                if not np.isfinite(image).all():
                    issues.append(f"nan_or_inf:{field}")
                elif image.size:
                    mean = float(np.mean(image))
                    if mean <= 3.0:
                        issues.append(f"black_frame:{field}")
                    elif mean >= 252.0:
                        issues.append(f"white_frame:{field}")
                    if image.ndim < 3 or image.shape[-1] not in {1, 3, 4}:
                        issues.append(f"image_shape:{field}{tuple(image.shape)}")
        for field in ["robot_obs", "rel_actions", "actions"]:
            if field in data.files and not np.isfinite(data[field]).all():
                issues.append(f"nan_or_inf:{field}")
        for field in ["rel_actions", "actions"]:
            if field in data.files:
                value = data[field]
                dim = int(value.shape[-1]) if getattr(value, "ndim", 0) else 0
                if dim != expected_action_dim:
                    issues.append(f"action_dim:{field}={dim}")
        return issues

    def _infer_transition_steps(self, data: np.lib.npyio.NpzFile, fields: list[str]) -> int:
        if not fields:
            return 0
        if "rel_actions" in data.files and getattr(data["rel_actions"], "ndim", 0) == 1:
            return 1
        first = data[fields[0]]
        shape = getattr(first, "shape", ())
        if len(shape) == 3 and shape[-1] in {1, 3, 4}:
            return 1
        return int(shape[0]) if shape else 1

    def describe_npz(self, path: Path, config: dict[str, Any] | None = None) -> str:
        required_fields = self.required_fields(config)
        image_fields = self.image_fields(config)
        action_dim = self.action_dim(config)
        lines = [f"file: {path}", f"size_mb: {path.stat().st_size / 1024 / 1024:.3f}"]
        try:
            with np.load(path, allow_pickle=True) as data:
                missing = [f for f in required_fields if f not in data.files]
                lines.append(f"status: {'ok' if not missing else 'warning'}")
                lines.append(f"missing_required: {', '.join(missing) if missing else '-'}")
                issues = self.quality_issues(data, image_fields, action_dim)
                lines.append(f"quality_issues: {', '.join(issues) if issues else '-'}")
                lines.append("")
                lines.append("fields:")
                for field in data.files:
                    value = data[field]
                    dtype = getattr(value, "dtype", "-")
                    shape = getattr(value, "shape", ())
                    lines.append(f"  {field}: shape={tuple(shape)} dtype={dtype}")
                metadata = self.metadata_summary(data)
                if metadata:
                    lines.append("")
                    lines.append("metadata:")
                    lines.extend(f"  {line}" for line in metadata)
        except Exception as exc:
            lines.append("status: error")
            lines.append(f"error: {exc}")
        return "\n".join(lines)

    def metadata_summary(self, data: np.lib.npyio.NpzFile) -> list[str]:
        lines: list[str] = []
        for field in [name for name in data.files if name in METADATA_FIELDS]:
            parsed = self._load_json_scalar(data[field])
            if not isinstance(parsed, dict):
                continue
            if field == "environment_info":
                desc = str(parsed.get("description") or parsed.get("type") or "").strip()
                if desc:
                    lines.append(f"environment_info: {desc[:180]}")
            elif field == "task_info":
                instruction = parsed.get("instruction", {})
                text = str(instruction.get("text", "") if isinstance(instruction, dict) else "").strip()
                if text:
                    lines.append(f"task_info: {text[:180]}")
            elif field == "stream_schema":
                streams = parsed.get("streams", [])
                if isinstance(streams, list):
                    lines.append(f"stream_schema: {len(streams)} stream(s)")
            elif field == "robot_info":
                name = str(parsed.get("name") or parsed.get("model") or "").strip()
                if name:
                    lines.append(f"robot_info: {name[:180]}")
            elif field == "collection_config":
                sections = ", ".join(sorted(str(key) for key in parsed.keys()))
                lines.append(f"collection_config: {sections[:180]}")
        return lines

    def _load_json_scalar(self, value: np.ndarray) -> Any:
        try:
            text = str(value.item() if getattr(value, "shape", ()) == () else value)
            return json.loads(text)
        except Exception:
            return None

    def required_fields(self, config: dict[str, Any] | None = None) -> list[str]:
        if not config:
            return list(REQUIRED_FIELDS)
        dataset_cfg = config.get("dataset", {})
        requires_robot_obs = bool(dataset_cfg.get("requires_robot_obs", True))
        requires_actions = bool(dataset_cfg.get("requires_actions", True))
        fields = []
        for stream in config.get("streams", []):
            if stream.get("message_type") != "sensor_msgs/msg/Image":
                continue
            if stream.get("required", True) is False:
                continue
            if stream.get("calvin_key") is None:
                continue
            key = str(stream.get("calvin_key") or stream.get("name") or "").strip()
            if key and key not in fields:
                fields.append(key)
        if requires_robot_obs:
            fields.append("robot_obs")
        if requires_actions:
            fields.extend(["rel_actions", "actions"])
        return fields

    def image_fields(self, config: dict[str, Any] | None = None) -> list[str]:
        if not config:
            return list(IMAGE_FIELDS)
        fields = []
        for stream in config.get("streams", []):
            if stream.get("message_type") != "sensor_msgs/msg/Image":
                continue
            if stream.get("calvin_key") is None:
                continue
            key = str(stream.get("calvin_key") or stream.get("name") or "").strip()
            if key and key not in fields:
                fields.append(key)
        return fields or list(IMAGE_FIELDS)

    def action_dim(self, config: dict[str, Any] | None = None) -> int:
        if not config:
            return ACTION_DIM
        try:
            dim = int(config.get("action", {}).get("dim") or 0)
        except (TypeError, ValueError):
            dim = 0
        if dim > 0:
            return dim
        state_keys = config.get("state", {}).get("keys", [])
        if isinstance(state_keys, list):
            for key in state_keys:
                if isinstance(key, dict):
                    try:
                        output_dim = int(key.get("output_dim") or 0)
                    except (TypeError, ValueError):
                        output_dim = 0
                    if output_dim > 0:
                        return output_dim
        return ACTION_DIM

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
