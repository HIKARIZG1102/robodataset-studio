# Task Progress 2026-06-25: General Image Decode Support

## Completed

- Audited image preview, snapshot, config generation, validator, and recorder paths.
- Reworked `ros/image_conversion.py` into the shared decode layer.
- Added support for common raw `sensor_msgs/msg/Image` encodings:
  - `rgb8`, `bgr8`, `rgba8`, `bgra8`
  - `mono8`, `8UC1`
  - `mono16`, `16UC1`, `16SC1`
  - `32FC1`
- Added row stride and short-buffer checks for raw images.
- Added big-endian handling for 16-bit and float image data.
- Added preview normalization for depth and float images.
- Added `sensor_msgs/msg/CompressedImage` support for preview and recording.
- Compressed image decode tries available libraries in this order:
  - Pillow
  - OpenCV
  - PySide6 `QImage`
- Updated Inspector to recognize both raw and compressed image topic types.
- Updated ROS discovery/config pages to treat compressed images as image streams.
- Updated the recorder to save compressed image topics as decoded RGB arrays.
- Updated dataset validator image-field checks to accept compressed image streams.

## Findings

- OpenCV cannot be treated as a reliable hard dependency in this environment:
  system `cv2` failed to import because of a NumPy ABI mismatch.
- Pillow worked for PNG/JPEG style compressed image decode.
- The running backend process still needs restart before the already-open app
  exposes newly added `/api/ros/image-snapshot` response fields.

## Verification

```text
compileall passed
rgb8 with row padding decoded correctly
big-endian 16UC1 decoded correctly
32FC1 preview normalization produced uint8 RGB
Pillow compressed PNG decoded correctly
/usb_camera/image_raw preview CLI emitted a frame with rgb_base64
direct RosService.image_snapshot returned image_rgb_base64 and image_ppm_base64
offscreen Inspector accepted a compressed-image-style RGB payload
```

## Remaining

- Restart the app to load these code changes into the running frontend/backend.
- Test with a real `sensor_msgs/msg/CompressedImage` camera topic when available.
- If downstream training expects depth arrays rather than RGB preview arrays for
  compressed depth topics, add a separate compressed-depth storage policy.
