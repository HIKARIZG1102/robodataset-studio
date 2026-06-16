# V3 Architecture Notes

## Product Shape

V3 keeps PySide6 as the desktop frontend and introduces FastAPI as a local
backend. The app should behave like a common desktop tool:

- Before a project is opened, only the menu bar is active.
- Creating/opening a project loads the project workspace.
- Project configuration is a dialog, not a permanent page.
- Global inspector is a right dock that can be opened at any time.
- Feature pages are organized as tabs: Collect, Review, Convert, Upload, Logs.

## Project Rule

One project version maps to one workspace and one main config:

```text
<name>_<version>/
  project.yaml
  collection_config.yaml
  raw_sessions/
  review/
  exports/
```

Examples:

```text
catch_the_satellite_v1
catch_the_satellite_v2
test1_depth_v1
```

## Backend Rule

FastAPI owns:

- project storage
- config validation and preview
- ROS discovery and inspection
- recording task lifecycle
- review and mark state
- conversion tasks
- upload/verify/repair tasks
- AI prompt and response tasks

PySide owns:

- menu and dialogs
- visual layout
- file browse dialogs
- displaying task progress/logs
- right-side inspector drawer

## First Migration Targets

1. Project service
2. Config schema and config preview
3. ROS discovery tree
4. Global inspector dock
5. Recording task API
6. Review APIs
7. Convert APIs
8. Upload APIs
9. AI APIs
