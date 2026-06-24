# Task Progress 2026-06-25: ROS Type Adaptation And Warnings

## Completed

- Added a shared generic ROS message conversion layer.
- Added explicit supported-type checks for non-image streams.
- Recording now fails early for unsupported configured stream types instead of
  silently skipping them.
- Recording metadata now includes diagnostics:
  - subscribed topics
  - decode errors
  - warnings
- Image decode failures now include stream name, message type, and encoding or
  compressed format.
- ROS Discovery and Config Library now preserve supported non-image topics as
  extension streams instead of ignoring them.
- Unsupported selected topics are written to config warnings and surfaced during
  recording preflight.

## Supported Generic Message Families

- `std_msgs` scalar values and multi-arrays.
- `std_msgs/msg/String` as a string array field.
- `geometry_msgs` point, vector, quaternion, pose, twist, wrench, transform and
  stamped variants.
- `sensor_msgs/msg/Imu`.
- `nav_msgs/msg/Odometry`.

## Behavior

- Image topics are saved through the image conversion layer.
- `JointState` topics still feed robot observation/action derivation.
- Supported generic topics are saved as extension arrays.
- Unsupported topics fail or warn explicitly with the topic and message type.

## Verification

```text
compileall passed
geometry_msgs/msg/Pose converted to a 7-value float32 vector
std_msgs/msg/Float64MultiArray converted to a numeric array
sensor_msgs/msg/Imu produced extension stream defaults
custom_msgs/msg/Foo failed with a topic/type-specific error
JointState-only config is treated as supported and fails only if no samples arrive
/usb_camera/image_raw preview CLI still emits rgb_base64 frames
```

## Remaining

- Add converters when a new robot publishes a custom message type.
- Add UI badges for unsupported topic warnings in the topic tree.
- Test with real non-image robot topics from WidowX or other arms when available.
