# Task Progress 2026-06-25: Inspector Image Monitor

## Completed

- Verified the ROS graph exposes `/usb_camera/image_raw`.
- Verified `/usb_camera/image_raw` type is `sensor_msgs/msg/Image`.
- Verified the temporary USB camera node is publishing real frames.
- Verified `image_preview_cli` can subscribe and receive frames.
- Found the Inspector image path depended on Qt decoding a base64 PPM payload.
- Added a raw `rgb_base64` frame payload to `image_preview_cli`.
- Updated Inspector to decode raw RGB directly before falling back to PPM.
- Verified the new Inspector decode path with an offscreen Qt smoke test.

## Findings

- The camera topic itself is healthy.
- The previous display path was fragile because it required Qt image plugin
  support and re-decoded an already converted RGB frame.
- Existing frontend windows must be restarted before they load this Python code
  change.

## Verification

```text
/usb_camera/image_raw sensor_msgs/msg/Image visible in /api/ros/graph
image_preview_cli emitted status and frame payload
rgb payload length: 1228800 bytes for 640x480 rgb8
compileall passed
offscreen Inspector frame decode produced a non-null QImage
```

## Remaining

- Restart the running frontend and test the Inspector button in the real window.
- If the real window still does not display, inspect the Preview Log tab for
  process start errors or topic selection mismatch.
