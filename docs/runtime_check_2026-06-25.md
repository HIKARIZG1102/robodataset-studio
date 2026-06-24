# Runtime Check 2026-06-25

Branch: `v3-fastapi-pyside`

Clone path:

```text
/home/hikarizg/codexworkspace/robodataset-studio-v3
```

## Environment

- OS environment has `/usr/bin/python3.10`.
- ROS Humble setup exists at `/opt/ros/humble/setup.bash`.
- `rclpy` imports successfully under Python 3.10.

## Install Script Finding

Initial bootstrap failed on a fresh venv because Ubuntu's default venv provided:

```text
pip 22.0.2
setuptools 59.6.0
```

With old setuptools, editable install fell back incorrectly and installed the
project as:

```text
UNKNOWN-0.0.0
```

Then dependency verification failed for packages such as `PySide6`, `fastapi`,
and `h5py`.

The bootstrap fix is to upgrade build tooling before editable install, while
keeping setuptools below 80 to avoid conflicts with ROS/colcon packages visible
through `--system-site-packages`:

```bash
python -m pip install --upgrade pip "setuptools>=68,<80" wheel
```

After this change, a clean bootstrap succeeds.

## Smoke Tests

Passed:

```bash
ENV_BACKEND=venv PYTHON_BIN=/usr/bin/python3.10 ./scripts/bootstrap.sh
```

Passed imports:

```text
PySide6
fastapi
uvicorn
numpy
h5py
yaml
httpx
rclpy
robodataset_studio_v3.frontend.main
robodataset_studio_v3.backend.main
```

Backend health check passed:

```text
GET http://127.0.0.1:8765/api/health
{"status":"ok","service":"robodataset-studio-v3"}
```

Frontend offscreen creation passed:

```text
RoboDataset Studio V3
central widget: True
```

## Notes

- `./RoboDataset-Studio-V3.sh --help` currently starts the GUI rather than
  printing CLI help. This is not fatal, but it is worth documenting or handling
  later.
- `pyproject.toml` declares an empty `upload` extra, while `requirements.txt`
  includes `paramiko`. If upload code starts importing `paramiko` directly,
  add it to the `upload` extra or main dependencies.

