from __future__ import annotations

from io import BytesIO

import numpy as np


IMAGE_MESSAGE_TYPES = {"sensor_msgs/msg/Image", "sensor_msgs/msg/CompressedImage"}


def is_image_message_type(message_type: str) -> bool:
    return message_type in IMAGE_MESSAGE_TYPES


def image_bytes_to_rgb(data: bytes, meta: dict[str, object]) -> np.ndarray | None:
    frame = image_bytes_to_array(data, meta)
    return array_to_preview_rgb(frame)


def compressed_image_to_rgb(data: bytes, meta: dict[str, object] | None = None) -> np.ndarray | None:
    frame = _compressed_with_pillow(data)
    if frame is not None:
        return frame
    frame = _compressed_with_opencv(data)
    if frame is not None:
        return frame
    return _compressed_with_qimage(data)


def image_bytes_to_array(data: bytes, meta: dict[str, object]) -> np.ndarray | None:
    """Convert sensor_msgs/Image bytes for dataset storage without preview-only colorization."""
    encoding = _normalized_encoding(meta)
    height = int(meta.get("height", 0) or 0)
    width = int(meta.get("width", 0) or 0)
    step = int(meta.get("step", 0) or 0)
    if height <= 0 or width <= 0 or step <= 0:
        return None
    rows = _rows(data, height, step)
    if rows is None:
        return None

    if encoding in {"rgb8", "bgr8", "8uc3"}:
        frame = rows[:, : width * 3].reshape((height, width, 3)).copy()
        if encoding == "bgr8":
            frame = frame[:, :, ::-1].copy()
        return frame
    if encoding in {"rgba8", "bgra8", "8uc4"}:
        frame = rows[:, : width * 4].reshape((height, width, 4))[:, :, :3].copy()
        if encoding == "bgra8":
            frame = frame[:, :, ::-1].copy()
        return frame
    if encoding in {"mono8", "8uc1"}:
        return rows[:, :width].reshape((height, width)).copy()
    if encoding in {"mono16", "16uc1"}:
        return _typed_rows(data, meta, np.uint16, height, width, step)
    if encoding == "16sc1":
        return _typed_rows(data, meta, np.int16, height, width, step)
    if encoding == "32fc1":
        return _typed_rows(data, meta, np.float32, height, width, step)
    return None


def array_to_preview_rgb(frame: np.ndarray | None) -> np.ndarray | None:
    if frame is None:
        return None
    if frame.ndim == 3 and frame.shape[2] >= 3:
        rgb = frame[:, :, :3]
        if rgb.dtype != np.uint8:
            rgb = _normalize_scalar_image(rgb.astype(np.float32))
        return np.ascontiguousarray(rgb.astype(np.uint8, copy=False))
    if frame.ndim == 2:
        gray = frame if frame.dtype == np.uint8 else _normalize_scalar_image(frame)
        return np.repeat(gray.astype(np.uint8, copy=False)[:, :, None], 3, axis=2)
    return None


def _normalized_encoding(meta: dict[str, object]) -> str:
    encoding = str(meta.get("encoding", "") or "").strip().lower()
    return encoding.replace(" ", "")


def _rows(data: bytes, height: int, step: int) -> np.ndarray | None:
    raw = np.frombuffer(data, dtype=np.uint8)
    required = height * step
    if raw.size < required:
        return None
    return raw[:required].reshape((height, step))


def _typed_rows(
    data: bytes,
    meta: dict[str, object],
    dtype: type[np.generic],
    height: int,
    width: int,
    step: int,
) -> np.ndarray | None:
    itemsize = np.dtype(dtype).itemsize
    if step < width * itemsize:
        return None
    endian = ">" if int(meta.get("is_bigendian", 0) or 0) else "<"
    source_dtype = np.dtype(dtype).newbyteorder(endian)
    raw = np.frombuffer(data, dtype=source_dtype)
    required = height * (step // itemsize)
    if raw.size < required:
        return None
    frame = raw[:required].reshape((height, step // itemsize))[:, :width].copy()
    return frame.astype(dtype, copy=False)


def _normalize_scalar_image(frame: np.ndarray) -> np.ndarray:
    values = frame.astype(np.float32, copy=False)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return np.zeros(values.shape, dtype=np.uint8)
    low = float(np.percentile(finite, 1))
    high = float(np.percentile(finite, 99))
    if high <= low:
        high = low + 1.0
    gray = np.clip((values - low) * 255.0 / (high - low), 0, 255)
    return np.nan_to_num(gray, nan=0.0, posinf=255.0, neginf=0.0).astype(np.uint8)


def _compressed_with_pillow(data: bytes) -> np.ndarray | None:
    try:
        from PIL import Image

        with Image.open(BytesIO(data)) as image:
            return np.asarray(image.convert("RGB"), dtype=np.uint8).copy()
    except Exception:
        return None


def _compressed_with_opencv(data: bytes) -> np.ndarray | None:
    try:
        import cv2

        encoded = np.frombuffer(data, dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if image is None:
            return None
        return image[:, :, ::-1].copy()
    except Exception:
        return None


def _compressed_with_qimage(data: bytes) -> np.ndarray | None:
    try:
        from PySide6.QtGui import QImage

        image = QImage.fromData(data)
        if image.isNull():
            return None
        image = image.convertToFormat(QImage.Format_RGB888)
        width = image.width()
        height = image.height()
        ptr = image.constBits()
        return np.frombuffer(ptr, dtype=np.uint8).reshape((height, image.bytesPerLine()))[:, : width * 3].reshape((height, width, 3)).copy()
    except Exception:
        return None
