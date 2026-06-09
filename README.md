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

Python dependencies are installed into a project-local environment by default:
`.venv/` for venv or `.conda-env/` for the conda fallback.

If ROS2 is not sourced, discovery falls back to an empty graph and the mock
recorder/converter still work for UI and data-flow testing.

By default, the launcher uses CycloneDDS (`rmw_cyclonedds_cpp`) and also exports
`config/fastdds_no_shm.xml` as a FastDDS fallback profile. This avoids
`fastrtps_port* open_and_lock_file` errors that can cause unstable image
preview on shared workstations. To override the RMW implementation:

```bash
ROBODATASET_RMW_IMPLEMENTATION=rmw_fastrtps_cpp ./RoboDataset-Studio.sh
```

For ROS2 Humble recording, use Python 3.10 because the system `rclpy` extension
is built for Python 3.10 on Ubuntu 22.04. `scripts/bootstrap.sh` defaults to
`/usr/bin/python3.10`, sources `/opt/ros/humble/setup.bash` when present, and
falls back to a project-local conda environment at `.conda-env/` if Python venv
is unavailable.

On a new Ubuntu machine, either install the venv package:

```bash
sudo apt install python3.10-venv libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-util1 libxcb-xkb1 libxkbcommon-x11-0 libx11-xcb1 libgl1 libegl1 libfontconfig1 libfreetype6 libdbus-1-3 libglib2.0-0 libwayland-client0 libwayland-cursor0 libwayland-egl1
```

or let bootstrap/startup ask to install missing system packages automatically:

```bash
scripts/bootstrap.sh
```

The Qt/PySide6 desktop runtime needs X11/Wayland/OpenGL system libraries.
`scripts/bootstrap.sh` and `RoboDataset-Studio.sh` scan the installed Qt plugins
with `ldd` and prompt for sudo installation of exact missing Ubuntu packages
before the app starts. Control the behavior with:

```bash
AUTO_INSTALL_SYSTEM_DEPS=1 scripts/bootstrap.sh  # install without prompting
AUTO_INSTALL_SYSTEM_DEPS=0 scripts/bootstrap.sh  # only print commands
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
- Project-local config library under `config_library/` for saved listener
  configs that can be loaded, copied, or deleted from the Config page.
- Listener-only ROS2 recorder that subscribes to already-running image and
  joint topics, then writes Hermes-style CALVIN-like transition files:
  `training/episode_*.npz` plus `training/lang_annotations/auto_lang_ann.npy`.
- Mock NPZ recorder producing the same CALVIN-like transition layout.
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
