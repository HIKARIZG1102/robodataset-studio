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
    def list_npz(self, episodes_dir: Path) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for path in sorted(episodes_dir.glob("episode_*.npz")):
            row: dict[str, object] = {
                "path": str(path),
                "name": path.name,
                "size_mb": round(path.stat().st_size / 1024 / 1024, 3),
                "status": "uncheck",
                "missing": "",
                "quality": "",
            }
            try:
                with np.load(path, allow_pickle=True) as data:
                    fields = list(data.files)
                    row["fields"] = ", ".join(fields)
                    row["steps"] = self._infer_transition_steps(data, fields)
            except Exception as exc:
                row["fields"] = ""
                row["missing"] = str(exc)
                row["steps"] = 0
                row["quality"] = str(exc)
                row["status"] = "error"
            rows.append(row)
        return rows

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
                    detail = self.value_summary(value)
                    if detail:
                        lines.append(f"    {detail}")
                metadata = self.metadata_summary(data)
                if metadata:
                    lines.append("")
                    lines.append("metadata:")
                    lines.extend(f"  {line}" for line in metadata)
        except Exception as exc:
            lines.append("status: error")
            lines.append(f"error: {exc}")
        return "\n".join(lines)

    def episode_ai_summaries(
        self,
        rows: list[dict[str, object]],
        config: dict[str, Any] | None = None,
        limit: int = 80,
    ) -> list[dict[str, Any]]:
        image_fields = self.image_fields(config)
        summaries: list[dict[str, Any]] = []
        for row in rows[:limit]:
            path = Path(str(row.get("path", "")))
            summary: dict[str, Any] = {
                "name": row.get("name", path.name),
                "status": row.get("status", ""),
                "missing": row.get("missing", ""),
                "quality": row.get("quality", ""),
                "steps": row.get("steps", ""),
                "size_mb": row.get("size_mb", ""),
                "fields": [],
            }
            try:
                with np.load(path, allow_pickle=True) as data:
                    for field in data.files:
                        value = data[field]
                        field_summary: dict[str, Any] = {
                            "name": field,
                            "shape": list(getattr(value, "shape", ())),
                            "dtype": str(getattr(value, "dtype", "")),
                        }
                        if field in image_fields or (getattr(value, "ndim", 0) >= 3 and getattr(value, "shape", (0,))[-1] in {1, 3, 4}):
                            field_summary.update(self._numeric_stats(value, prefix="image_"))
                        elif field in {"robot_obs", "rel_actions", "actions"}:
                            field_summary.update(self._numeric_stats(value))
                            if getattr(value, "ndim", 0) > 0:
                                field_summary["abs_sum"] = float(np.sum(np.abs(value)))
                        elif getattr(value, "dtype", None) is not None and value.dtype.kind in {"f", "i", "u", "b"}:
                            field_summary.update(self._numeric_stats(value))
                        summary["fields"].append(field_summary)
            except Exception as exc:
                summary["load_error"] = str(exc)
            summaries.append(summary)
        return summaries

    def _numeric_stats(self, value: np.ndarray, prefix: str = "") -> dict[str, Any]:
        try:
            if value.size == 0:
                return {f"{prefix}empty": True}
            return {
                f"{prefix}mean": float(np.mean(value)),
                f"{prefix}std": float(np.std(value)),
                f"{prefix}min": float(np.min(value)),
                f"{prefix}max": float(np.max(value)),
                f"{prefix}finite": bool(np.isfinite(value).all()),
            }
        except Exception:
            return {}

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

    def value_summary(self, value: np.ndarray) -> str:
        try:
            if value.dtype.kind in {"f", "i", "u", "b"}:
                if value.ndim == 0:
                    return f"value={value.item()}"
                if value.ndim == 1 and value.size <= 32:
                    return "values=[" + ", ".join(f"{float(item):.5g}" for item in value.tolist()) + "]"
                if value.ndim >= 3 and value.shape[-1] in {1, 3, 4}:
                    return (
                        f"image_stats mean={float(np.mean(value)):.2f} "
                        f"std={float(np.std(value)):.2f} min={float(np.min(value)):.0f} max={float(np.max(value)):.0f}"
                    )
                return (
                    f"stats mean={float(np.mean(value)):.5g} std={float(np.std(value)):.5g} "
                    f"min={float(np.min(value)):.5g} max={float(np.max(value)):.5g}"
                )
            if value.shape == ():
                text = str(value.item())
                return "text=" + (text[:180] + "..." if len(text) > 180 else text)
        except Exception:
            return ""
        return ""

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

    def check_hdf5(self, path: Path, config: dict[str, Any] | None = None) -> list[dict[str, object]]:
        required_fields = self.required_fields(config)
        image_fields = self.image_fields(config)
        action_dim = self.action_dim(config)
        if not path.exists():
            return [
                {
                    "scope": str(path),
                    "status": "error",
                    "issue": "missing_hdf5_file",
                    "detail": "selected HDF5 file does not exist",
                }
            ]
        rows: list[dict[str, object]] = []
        try:
            with h5py.File(path, "r") as h5:
                episodes = h5.get("episodes")
                if episodes is None:
                    rows.append(
                        {
                            "scope": "/",
                            "status": "error",
                            "issue": "missing_group",
                            "detail": "HDF5 file has no /episodes group",
                        }
                    )
                    return rows
                episode_names = sorted(episodes.keys())
                if not episode_names:
                    rows.append(
                        {
                            "scope": "/episodes",
                            "status": "error",
                            "issue": "empty_episodes",
                            "detail": "no episode groups found",
                        }
                    )
                metadata = h5.get("metadata")
                if metadata is None:
                    rows.append(
                        {
                            "scope": "/",
                            "status": "warning",
                            "issue": "missing_metadata_group",
                            "detail": "metadata group is absent; training may still work but provenance is incomplete",
                        }
                    )
                else:
                    try:
                        expected_count = int(metadata.attrs.get("num_episodes", len(episode_names)))
                    except (TypeError, ValueError):
                        expected_count = len(episode_names)
                    if expected_count != len(episode_names):
                        rows.append(
                            {
                                "scope": "/metadata",
                                "status": "warning",
                                "issue": "episode_count_mismatch",
                                "detail": f"metadata num_episodes={expected_count}, actual={len(episode_names)}",
                            }
                        )
                    if not str(metadata.attrs.get("config_yaml", "")).strip():
                        rows.append(
                            {
                                "scope": "/metadata",
                                "status": "warning",
                                "issue": "missing_config_yaml",
                                "detail": "metadata/config_yaml attr is empty",
                            }
                        )
                for episode_name in episode_names:
                    group = episodes[episode_name]
                    fields = set(group.keys())
                    missing = [field for field in required_fields if field not in fields]
                    if missing:
                        rows.append(
                            {
                                "scope": f"/episodes/{episode_name}",
                                "status": "error",
                                "issue": "missing_required_fields",
                                "detail": ", ".join(missing),
                            }
                        )
                    for field in sorted(fields):
                        dataset = group[field]
                        shape = tuple(dataset.shape)
                        dtype = str(dataset.dtype)
                        if field in image_fields:
                            if len(shape) < 3 or shape[-1] not in {1, 3, 4}:
                                rows.append(
                                    {
                                        "scope": f"/episodes/{episode_name}/{field}",
                                        "status": "warning",
                                        "issue": "image_shape",
                                        "detail": f"shape={shape} dtype={dtype}",
                                    }
                                )
                        if field in {"rel_actions", "actions"}:
                            dim = int(shape[-1]) if shape else 0
                            if dim != action_dim:
                                rows.append(
                                    {
                                        "scope": f"/episodes/{episode_name}/{field}",
                                        "status": "warning",
                                        "issue": "action_dim",
                                        "detail": f"expected={action_dim}, actual={dim}",
                                    }
                                )
                        if field in {"robot_obs", "rel_actions", "actions"}:
                            try:
                                sample = dataset[()]
                                if not np.isfinite(sample).all():
                                    rows.append(
                                        {
                                            "scope": f"/episodes/{episode_name}/{field}",
                                            "status": "error",
                                            "issue": "nan_or_inf",
                                            "detail": f"shape={shape} dtype={dtype}",
                                        }
                                    )
                            except Exception as exc:
                                rows.append(
                                    {
                                        "scope": f"/episodes/{episode_name}/{field}",
                                        "status": "error",
                                        "issue": "unreadable_dataset",
                                        "detail": str(exc),
                                    }
                                )
                    for metadata_field in METADATA_FIELDS:
                        if metadata_field not in group.attrs:
                            rows.append(
                                {
                                    "scope": f"/episodes/{episode_name}",
                                    "status": "warning",
                                    "issue": f"missing_metadata_attr:{metadata_field}",
                                    "detail": "metadata extension is absent",
                                }
                            )
                if not rows:
                    rows.append(
                        {
                            "scope": str(path),
                            "status": "ok",
                            "issue": "-",
                            "detail": f"{len(episode_names)} episode(s) checked",
                        }
                    )
        except Exception as exc:
            rows.append({"scope": str(path), "status": "error", "issue": "hdf5_open_failed", "detail": str(exc)})
        return rows

    def hdf5_check_summary(self, path: Path, rows: list[dict[str, object]]) -> str:
        episode_names: list[str] = []
        try:
            if path.exists():
                with h5py.File(path, "r") as h5:
                    episodes = h5.get("episodes")
                    if episodes is not None:
                        episode_names = sorted(episodes.keys())
        except Exception:
            episode_names = []

        episode_status = {name: "ok" for name in episode_names}
        episode_issues: dict[str, list[str]] = {name: [] for name in episode_names}
        file_issues: list[str] = []
        for row in rows:
            status = str(row.get("status", ""))
            if status == "ok":
                continue
            issue = str(row.get("issue", ""))
            detail = str(row.get("detail", ""))
            scope = str(row.get("scope", ""))
            episode_name = self._episode_name_from_scope(scope)
            if episode_name and (not episode_names or episode_name in episode_status):
                if status == "error":
                    episode_status[episode_name] = "error"
                elif episode_status.get(episode_name) != "error":
                    episode_status[episode_name] = "warning"
                episode_issues.setdefault(episode_name, []).append(f"{issue}: {detail}")
            else:
                file_issues.append(f"{status} {scope} {issue}: {detail}")

        total = len(episode_names)
        ok_count = sum(1 for status in episode_status.values() if status == "ok")
        warning_count = sum(1 for status in episode_status.values() if status == "warning")
        error_count = sum(1 for status in episode_status.values() if status == "error")
        valid_count = ok_count
        invalid_count = warning_count + error_count
        lines = [
            f"file: {path}",
            f"episodes: total={total} valid={valid_count} invalid={invalid_count} warnings={warning_count} errors={error_count}",
            f"file-level issues: {len(file_issues)}",
        ]
        if file_issues:
            lines.append("file-level details:")
            lines.extend(f"  - {issue}" for issue in file_issues[:12])
            if len(file_issues) > 12:
                lines.append(f"  - ... {len(file_issues) - 12} more")
        bad_episodes = [name for name, status in episode_status.items() if status != "ok"]
        if bad_episodes:
            lines.append("episode issues:")
            for name in bad_episodes[:20]:
                issues = "; ".join(episode_issues.get(name, []))
                lines.append(f"  - {name}: {episode_status[name]} | {issues}")
            if len(bad_episodes) > 20:
                lines.append(f"  - ... {len(bad_episodes) - 20} more")
        elif total:
            lines.append("episode issues: none")
        elif rows:
            lines.append("episode issues: no readable episode group")
        return "\n".join(lines)

    def _episode_name_from_scope(self, scope: str) -> str:
        parts = [part for part in scope.split("/") if part]
        if len(parts) >= 2 and parts[0] == "episodes":
            return parts[1]
        return ""

    def check_calvin_layout(self, root: Path) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        if not root.exists():
            return [{"path": str(root), "status": "error", "issue": "missing_root", "detail": "selected path does not exist"}]
        if root.is_file():
            return [{"path": str(root), "status": "error", "issue": "not_a_directory", "detail": "layout check expects a folder"}]

        session_dirs = self._find_session_dirs(root)
        hdf5_files = sorted(root.glob("**/*.hdf5")) + sorted(root.glob("**/*.h5"))
        if not session_dirs and not hdf5_files:
            rows.append(
                {
                    "path": str(root),
                    "status": "warning",
                    "issue": "no_calvin_artifacts",
                    "detail": "no session training folders or HDF5 files found",
                }
            )

        for session_dir in session_dirs:
            training = session_dir / "training"
            episodes = sorted(training.glob("episode_*.npz"))
            config_path = session_dir / "collection_config.yaml"
            annotations = training / "lang_annotations" / "auto_lang_ann.npy"
            manifest = session_dir / "merge_manifest.json"
            if not episodes:
                rows.append(
                    {
                        "path": str(training),
                        "status": "error",
                        "issue": "empty_training",
                        "detail": "training folder has no episode_*.npz files",
                    }
                )
            else:
                rows.append(
                    {
                        "path": str(session_dir),
                        "status": "ok",
                        "issue": "-",
                        "detail": f"{len(episodes)} npz episode(s)",
                    }
                )
            if not config_path.exists():
                rows.append(
                    {
                        "path": str(session_dir),
                        "status": "warning",
                        "issue": "missing_collection_config",
                        "detail": "collection_config.yaml is absent",
                    }
                )
            if not annotations.exists():
                rows.append(
                    {
                        "path": str(training),
                        "status": "warning",
                        "issue": "missing_language_annotations",
                        "detail": "lang_annotations/auto_lang_ann.npy is absent",
                    }
                )
            if "merged_calvin" in session_dir.parts and not manifest.exists():
                rows.append(
                    {
                        "path": str(session_dir),
                        "status": "warning",
                        "issue": "missing_merge_manifest",
                        "detail": "merged output has no merge_manifest.json next to training",
                    }
                )

        for hdf5_path in hdf5_files:
            hdf5_rows = self.check_hdf5(hdf5_path)
            worst = self._worst_status(str(row.get("status", "")) for row in hdf5_rows)
            issue = "-" if worst == "ok" else ", ".join(sorted({str(row.get("issue", "")) for row in hdf5_rows if row.get("status") != "ok"}))
            rows.append(
                {
                    "path": str(hdf5_path),
                    "status": worst,
                    "issue": issue or "-",
                    "detail": f"HDF5 check rows={len(hdf5_rows)}",
                }
            )
        return rows

    def _find_session_dirs(self, root: Path) -> list[Path]:
        candidates: set[Path] = set()
        if (root / "training").is_dir():
            candidates.add(root)
        for training in root.glob("**/training"):
            if training.is_dir():
                candidates.add(training.parent)
        return sorted(candidates)

    def _worst_status(self, statuses: Any) -> str:
        rank = {"ok": 0, "uncheck": 0, "warning": 1, "error": 2}
        worst = "ok"
        for status in statuses:
            if rank.get(status, 0) > rank.get(worst, 0):
                worst = status
        return worst
