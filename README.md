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

Dataset outputs are also project-local by default. If the Project page dataset
root is left empty or set to `robodataset`, recordings and conversions are
written under:

```text
robodataset/
  raw_sessions/
  merged_calvin/
```

Relative dataset roots are resolved against this repository directory, not the
current shell working directory. Absolute paths are still supported when an
operator intentionally wants to write to an external disk or shared dataset
mount.

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
- SSH upload workflow with split internal/public host fields, port, username,
  password/key authentication, remote directory browsing, folder creation, and
  `rsync` upload from the selected remote directory.

## Review Tools

The Review workspace has three separate tabs:

- **Episode Review** scans one recorded session root. It loads
  `training/episode_*.npz`, shows per-file fields, shapes, dtypes, metadata,
  local validation results, manual marks, and supports moving unwanted episode
  files into `review_deleted/`.
- **HDF5 Inspect** opens the current HDF5 output and reports the top-level HDF5
  structure, episode count, metadata attributes, and representative episode
  fields. Use it after converting NPZ data to HDF5 to confirm that the file is
  readable and contains the expected schema.
- **CALVIN Layout** scans the configured dataset root and summarizes raw,
  merged, and converted CALVIN-style areas. It is meant for checking whether
  `raw_sessions/<task>/<version>/<session>/training`, merged outputs,
  `merge_manifest.json`, and HDF5 files are present in the expected places.

## Upload Requirements

The Upload page can send either a whole directory or one selected file.

Server-side baseline requirements:

- The server must run an SSH server and allow login with the configured
  username.
- The target remote directory must exist or be creatable, and the user must have
  write permission there.
- The target filesystem must have enough free space for the selected local file
  or directory.
- Linux or Unix-like servers are the best-supported target. Other SSH/SFTP
  servers may work if they expose normal paths and file reads.

Authentication modes:

- **Password authentication** uses Paramiko SFTP in a background thread. It does
  not require remote `rsync` or remote `python3`. Normal upload, remote manifest
  verification, and repair/resume all work through SFTP in this mode.
- **SSH key / agent authentication** uses local `rsync` over SSH for normal
  upload and repair/resume. This mode expects `rsync` to be available on both
  the local machine and the remote server. Remote manifest verification uses
  `ssh python3 -`, so the remote server must have `python3`.

Resume and repair behavior:

- Regular `rsync` upload uses `--partial --append-verify` for safer interrupted
  transfers. `--partial-dir` is intentionally not used because current rsync
  rejects it together with `--append-verify`.
- `Repair / Resume verified upload` first compares the remote files against a
  local temporary manifest, then retransfers only missing or hash-mismatched
  files. With password authentication the retransmission is done by SFTP; with
  key/agent authentication it is done by `rsync --files-from`.

Manifest behavior:

- Upload manifests are temporary local JSON files generated under the system
  temp directory.
- The manifest is not stored in the selected dataset directory and is not
  uploaded to the server.
- Remote verification compares the remote files against the local temporary
  manifest. It checks relative path, byte size, and SHA-256 hash for every local
  file.
- Upload, remote verification, and repair/resume automatically refresh the
  temporary manifest, so users do not need to manually generate one first.

Remote space checks:

- The app first tries Paramiko SFTP filesystem statistics when available.
- If that API is unavailable on the server, it falls back to
  `df -PB1 <remote_path>`.
- If the server does not support either method, the UI should report the
  failure and upload can still be attempted manually if the user knows enough
  space is available.

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
