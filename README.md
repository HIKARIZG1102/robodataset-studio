# RoboDataset Studio

RoboDataset Studio is a PySide6 desktop MVP for ROS2 robot dataset collection.
It follows the project plan in `项目计划书.md`: local desktop UI, Python backend
services, process-managed ROS2 probes, YAML config generation, NPZ recording,
HDF5 conversion, review, and upload workflow.

## Quick Start

```bash
scripts/bootstrap.sh
./RoboDataset-Studio.sh
```

The bootstrap script creates a local Python environment, installs the project,
and writes two local launchers that are intentionally ignored by git:

- `RoboDataset-Studio.sh`
- `RoboDataset-Studio.desktop`

If ROS2 is not sourced, discovery falls back to an empty graph and the mock
recorder/converter still work for UI and data-flow testing.

For ROS2 Humble recording, use Python 3.10 because the system `rclpy` extension
is built for Python 3.10 on Ubuntu 22.04. `scripts/bootstrap.sh` defaults to
`/usr/bin/python3.10`, sources `/opt/ros/humble/setup.bash` when present, and
falls back to a project-local conda environment at `.conda-env/` if Python venv
is unavailable.

On a new Ubuntu machine, either install the venv package:

```bash
sudo apt install python3.10-venv
```

or let bootstrap try the system install on machines where sudo is available:

```bash
INSTALL_SYSTEM_DEPS=1 scripts/bootstrap.sh
```

or force the conda backend:

```bash
ENV_BACKEND=conda scripts/bootstrap.sh
```

Override paths only when needed:

```bash
PYTHON_BIN=/usr/bin/python3.10 CONDA_EXE=/path/to/conda ROS_SETUP=/opt/ros/humble/setup.bash scripts/bootstrap.sh
```

Run backend smoke tests with ROS2 pytest plugins disabled:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ./.conda-env/bin/python -m pytest -q
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
