# RoboDataset Studio V3

RoboDataset Studio V3 is a fresh project for the next architecture:

- PySide6 remains the desktop frontend.
- FastAPI runs as a local backend service.
- The UI is project-first: no project means only the top menu is active.
- One project version maps to one project workspace and one main config.
- The legacy `robodataset-studio/` project is intentionally left untouched and
  remains the reference implementation.

## Current Scope

This repository is currently a skeleton. It defines the intended package
layout, API boundaries, UI shell, project storage layout, and configuration
schema direction. Real ROS2 recording, review, conversion, upload, and AI
features should be migrated incrementally from the legacy project.

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
      collection_config.yaml
      raw_sessions/
      review/
      exports/
  app_state/
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
