# Architecture Notes

RoboDataset Studio follows the plan requirement that PySide6 should act as the
control and visualization layer, while long-running collection, conversion, and
upload jobs live in backend services or subprocesses.

## Current MVP Boundaries

- `ui`: PySide6 pages, navigation, forms, tables, preview widgets, and user
  notifications.
- `core`: project state, YAML config generation, environment reporting, and
  subprocess lifecycle management.
- `ros`: ROS2 command-based graph discovery. This can later be replaced or
  extended with `rclpy` workers.
- `dataset`: mock NPZ recorder, NPZ validator, and HDF5 converter.
- `upload`: SSH upload subprocess wrapper.

## State Flow

```text
Project -> Environment -> Discovery -> Inspector -> Config -> Recording -> Review -> Convert -> Upload
```

The first frontend guardrails are implemented:

- Recording requires an in-memory collection config.
- Review and Convert require raw NPZ episodes.
- Upload checks that the local path exists and that placeholder SSH targets are
  replaced.

## Next Frontend Work

- Add visual step completion indicators in the left navigation.
- Add a process log detail drawer or dialog.
- Replace the mock image preview with a ROS2 image worker that emits throttled
  preview frames.
- Add tables/forms for stream descriptors instead of YAML-only editing.

