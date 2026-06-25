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
- Diagnosed a later "no image topics found" report as a ROS discovery scope
  mismatch: the USB camera publisher used `ROS_LOCALHOST_ONLY=1` while the app
  had previously been started with a different localhost-only setting.
- Added ROS discovery environment fields to `/api/ros/graph` and surfaced them
  in the Inspector preview log when no image topic is found.
- Renamed the project-image button to "Sync image from project" with a sync
  icon, and restored project-only behavior: if no project is open, the user is
  told to open one instead of falling back to the selected ROS topic.

## Findings

- The camera topic itself is healthy.
- The previous display path was fragile because it required Qt image plugin
  support and re-decoded an already converted RGB frame.
- Existing frontend windows must be restarted before they load this Python code
  change.
- `This plugin supports grabbing the mouse only for popup windows` is a Qt
  platform plugin warning and does not explain missing ROS image topics. It may
  appear under Wayland/XCB popup/menu mouse-grab paths.
- Project image sync and direct ROS image monitoring are intentionally separate
  actions. Direct topic preview remains on "Start image monitor".

## Verification

```text
/usb_camera/image_raw sensor_msgs/msg/Image visible in /api/ros/graph
image_preview_cli emitted status and frame payload
rgb payload length: 1228800 bytes for 640x480 rgb8
compileall passed
offscreen Inspector frame decode produced a non-null QImage
ROS_LOCALHOST_ONLY=1 with rmw_fastrtps_cpp shows /usb_camera/image_raw via ros2 topic list
/api/ros/graph reports /usb_camera/image_raw after restarting the app with matching ROS_LOCALHOST_ONLY
```

## Remaining

- Test the Inspector button in the real window after restart.
- If the real window still does not display, inspect the Preview Log tab for
  process start errors, topic selection mismatch, or the printed ROS discovery
  environment fields.
