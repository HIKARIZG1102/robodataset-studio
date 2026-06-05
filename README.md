# RoboDataset Studio

RoboDataset Studio is a PySide6 desktop MVP for ROS2 robot dataset collection.
It follows the project plan in `项目计划书.md`: local desktop UI, Python backend
services, process-managed ROS2 probes, YAML config generation, NPZ recording,
HDF5 conversion, review, and upload workflow.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
robodataset-studio
```

If ROS2 is not sourced, discovery falls back to an empty graph and the mock
recorder/converter still work for UI and data-flow testing.

Run backend smoke tests with ROS2 pytest plugins disabled:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q
```

## MVP Scope

- Project, Environment, Discovery, Inspector, Config, Recording, Review,
  Convert, Upload, Process, and Settings pages.
- `ros2 node/topic` discovery through subprocess commands.
- Managed `topic echo` and `topic hz` subprocesses with safe stop.
- Auto-generated `collection_config.yaml` with robot, camera, stream, dataset,
  recording, Genesis, and AI sections.
- Mock NPZ recorder producing CALVIN-compatible fields.
- HDF5 converter for generated NPZ episodes.
- Review scanner with field and size summaries.
- SSH upload command wrapper through `rsync` or `scp` style subprocess command.

## Repository Layout

```text
src/robodataset_studio/
  core/       project, config, process, environment services
  ros/        ROS2 graph discovery and topic probe helpers
  dataset/    recorder, validator, converter
  upload/     upload job helpers
  ui/         PySide6 pages and main window
scripts/      command-line helpers
docs/         architecture notes
```
