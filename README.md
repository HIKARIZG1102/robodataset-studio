# RoboDataset Studio V3

RoboDataset Studio V3 is a fresh project for the next architecture:

- PySide6 remains the desktop frontend.
- FastAPI runs as a local backend service.
- The UI is project-first: no project means only the top menu is active.
- One project version maps to one project workspace and one main config.
- The legacy `robodataset-studio/` project is intentionally left untouched and
  remains the reference implementation.

## Current Scope

V3 now has a runnable PySide frontend, local FastAPI backend, project/config
storage, ROS inspection, recording, review, conversion, upload, AI, settings,
and task APIs. The backend has started migrating the validated V2 production
logic for CALVIN review, NPZ merge, HDF5 conversion, ROS listener recording,
rsync upload, remote verification, and OpenAI-compatible AI calls.

Some UI surfaces are still intentionally simple and will be refined after the
backend migration is fully validated on the robot.

## Install And Start

The recommended path is the project launcher. It uses the same environment
selection style as V2:

```bash
./RoboDataset-Studio-V3.sh
```

On first run, or when required Python packages are missing, the launcher calls:

```bash
scripts/bootstrap.sh
```

Bootstrap creates a project-local Python 3.10 environment and installs V3 in
editable mode. Python 3.10 is required because ROS Humble Python packages such
as `rclpy` and `sensor_msgs` are installed for the system Python 3.10 ABI. Do
not run the app from a conda/base Python 3.13 environment.

By default bootstrap tries `.venv` first and falls back to `.conda-env` if venv
creation is not available. If an existing V3 environment is not Python 3.10, the
launcher marks it invalid and bootstrap rebuilds it.

```bash
ENV_BACKEND=auto ./scripts/bootstrap.sh   # default: try venv, then conda
ENV_BACKEND=venv ./scripts/bootstrap.sh   # force .venv
ENV_BACKEND=conda ./scripts/bootstrap.sh  # force .conda-env
PYTHON_BIN=/usr/bin/python3.10 ./scripts/bootstrap.sh
```

The selected environment is recorded in:

```text
.robodataset_env
```

That file is local machine state and should not be committed. It stores only
the selected environment command and ROS setup path, not project data.

After bootstrap, start the app with either command:

```bash
./RoboDataset-Studio-V3.sh
./scripts/run_app.sh
```

`run_app.sh` sources `/opt/ros/humble/setup.bash` when available and exports
`RMW_IMPLEMENTATION=rmw_cyclonedds_cpp` by default. Override these when needed:

```bash
ROS_SETUP=/path/to/install/setup.bash ./RoboDataset-Studio-V3.sh
ROBODATASET_RMW_IMPLEMENTATION=rmw_fastrtps_cpp ./RoboDataset-Studio-V3.sh
```

For ROS recording, launch the app from an environment where the robot/camera
workspaces are available, or set `ROS_SETUP` to the correct setup script.

Optional system tools for upload:

```bash
sudo apt install rsync openssh-client
```

## Backend Startup

The PySide frontend checks `http://127.0.0.1:8765/api/health` on startup. If
the backend is not running, it starts a local FastAPI process automatically. If
port `8765` is occupied, the frontend tries the next local ports.

Backend auto-start logs are written under:

```text
/tmp/robodataset_studio_v3_backend_<port>.log
```

For debugging, run backend/frontend separately:

```bash
PYTHONPATH=src .venv/bin/python -m robodataset_studio_v3.backend.main
PYTHONPATH=src .venv/bin/python -m robodataset_studio_v3.frontend.main
```

Backend health check:

```bash
PYTHONPATH=src .venv/bin/python -m robodataset_studio_v3.backend.main
curl http://127.0.0.1:8765/api/health
```

If the frontend reports that the backend did not become healthy, check the log
path shown in the error dialog.

AI calls use OpenAI-compatible endpoints. The API key is read from:

```bash
export ROBOT_DATA_AI_API_KEY=...
```

The key is not written to project_config.yaml or dataset_config.yaml.

## Architecture

```text
PySide6 Desktop Frontend
  |
  | HTTP / WebSocket
  v
FastAPI Local Backend
  |
  v
Services: Project / Config / ROS / Inspector / Recording / Review / Convert / Upload / AI
```

## Default Project Storage

Project data is relative to this repository by default:

```text
robodataset/
  projects/
    catch_the_satellite_v1/
      project.yaml
      project_config.yaml
      dataset_config.yaml
      raw_sessions/
      review/
      exports/
```

Absolute paths may still be supported later when operators intentionally choose
an external disk or shared dataset mount.

When creating a project, the project root defaults to the relative path
`robodataset/projects`. Operators can Browse to an external disk when they want
the project data outside the repository.

## UI Direction

When no project is open, only the top menu is available.

After opening or creating a project, the workspace exposes:

```text
[Collect] [Review] [Convert] [Upload] [Logs]
```

Global inspector is a right-side collapsible drawer:

```text
[Topic Inspector] [Image Monitor]
```

Project creation and configuration should be modal dialogs, not permanent
pages.
