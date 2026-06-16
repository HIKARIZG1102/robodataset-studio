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

## Install

From this directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

For ROS recording, run in an environment where ROS2 and the robot/camera
workspaces are already sourced, for example:

```bash
source /opt/ros/humble/setup.bash
# source your robot workspace install/setup.bash if needed
```

Optional system tools:

```bash
sudo apt install rsync openssh-client
```

## Run

Install dependencies in a project-local environment, then run:

```bash
./RoboDataset-Studio-V3.sh
```

The PySide frontend checks `http://127.0.0.1:8765/api/health` on startup. If
the backend is not running, it starts a local FastAPI process automatically. If
port `8765` is occupied, the frontend tries the next local ports.

Or run backend/frontend separately:

```bash
python -m robodataset_studio_v3.backend.main
python -m robodataset_studio_v3.frontend.main
```

If using the project-local virtual environment directly:

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
path shown in the error dialog. Backend auto-start logs are written under
`/tmp/robodataset_studio_v3_backend_<port>.log`.

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
