from __future__ import annotations

import numpy as np


def image_bytes_to_rgb(data: bytes, meta: dict[str, object]) -> np.ndarray | None:
    encoding = str(meta.get("encoding", "")).lower()
    height = int(meta.get("height", 0) or 0)
    width = int(meta.get("width", 0) or 0)
    step = int(meta.get("step", 0) or 0)
    raw = np.frombuffer(data, dtype=np.uint8)
    if height <= 0 or width <= 0 or step <= 0:
        return None
    rows = raw.reshape((height, step))
    if encoding in {"rgb8", "bgr8"}:
        frame = rows[:, : width * 3].reshape((height, width, 3)).copy()
        if encoding == "bgr8":
            frame = frame[:, :, ::-1].copy()
        return frame
    if encoding in {"rgba8", "bgra8"}:
        frame = rows[:, : width * 4].reshape((height, width, 4))[:, :, :3].copy()
        if encoding == "bgra8":
            frame = frame[:, :, ::-1].copy()
        return frame
    if encoding in {"mono8", "8uc1"}:
        gray = rows[:, :width].reshape((height, width)).copy()
        return np.repeat(gray[:, :, None], 3, axis=2)
    if encoding in {"mono16", "16uc1", "16uc1; compresseddepth"}:
        depth = np.frombuffer(data, dtype=np.uint16).reshape((height, step // 2))[:, :width]
        max_value = int(depth.max()) or 1
        gray = np.clip(depth.astype(np.float32) * 255.0 / max_value, 0, 255).astype(np.uint8)
        return np.repeat(gray[:, :, None], 3, axis=2)
    if encoding in {"32fc1"}:
        depth = np.frombuffer(data, dtype=np.float32).reshape((height, step // 4))[:, :width]
        finite = depth[np.isfinite(depth)]
        if finite.size == 0:
            return np.zeros((height, width, 3), dtype=np.uint8)
        low = float(np.percentile(finite, 1))
        high = float(np.percentile(finite, 99))
        if high <= low:
            high = low + 1.0
        gray = np.clip((depth - low) * 255.0 / (high - low), 0, 255)
        gray = np.nan_to_num(gray, nan=0.0, posinf=255.0, neginf=0.0).astype(np.uint8)
        return np.repeat(gray[:, :, None], 3, axis=2)
    return None


def image_bytes_to_array(data: bytes, meta: dict[str, object]) -> np.ndarray | None:
    """Convert ROS Image bytes for dataset storage without preview-only colorization."""
    encoding = str(meta.get("encoding", "")).lower()
    height = int(meta.get("height", 0) or 0)
    width = int(meta.get("width", 0) or 0)
    step = int(meta.get("step", 0) or 0)
    raw = np.frombuffer(data, dtype=np.uint8)
    if height <= 0 or width <= 0 or step <= 0:
        return None
    rows = raw.reshape((height, step))
    if encoding in {"rgb8", "bgr8"}:
        frame = rows[:, : width * 3].reshape((height, width, 3)).copy()
        if encoding == "bgr8":
            frame = frame[:, :, ::-1].copy()
        return frame
    if encoding in {"rgba8", "bgra8"}:
        frame = rows[:, : width * 4].reshape((height, width, 4))[:, :, :3].copy()
        if encoding == "bgra8":
            frame = frame[:, :, ::-1].copy()
        return frame
    if encoding in {"mono8", "8uc1"}:
        return rows[:, :width].reshape((height, width)).copy()
    if encoding in {"mono16", "16uc1", "16uc1; compresseddepth"}:
        return np.frombuffer(data, dtype=np.uint16).reshape((height, step // 2))[:, :width].copy()
    if encoding in {"32fc1"}:
        return np.frombuffer(data, dtype=np.float32).reshape((height, step // 4))[:, :width].copy()
    return image_bytes_to_rgb(data, meta)
