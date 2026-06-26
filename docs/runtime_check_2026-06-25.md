# Runtime Check 2026-06-25

Branch: `v3-fastapi-pyside`

Clone path:

```text
<repo-root>
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

## Environment Adaptation Audit

Additional check after testing the in-app ROS terminal:

- The host has `rmw_fastrtps_cpp` installed.
- The host does not have `rmw_cyclonedds_cpp` installed.
- Commands that inherited `RMW_IMPLEMENTATION=rmw_cyclonedds_cpp` failed with:

```text
failed to load shared library 'librmw_cyclonedds_cpp.so'
```

Fix applied:

- `scripts/bootstrap.sh` and `scripts/run_app.sh` now auto-detect available ROS
  setup files and RMW implementations.
- Runtime Python code now uses `robodataset_studio_v3.core.runtime_env` to
  select an installed RMW implementation.
- Direct backend startup also applies the same ROS/RMW environment normalization.
- On this host, `select_rmw()` returns `rmw_fastrtps_cpp`.
- If a stale or unavailable RMW is requested, it falls back to an installed
  implementation.

Verification:

```text
ros_setup /opt/ros/humble/setup.bash
available ['rmw_fastrtps_cpp']
selected rmw_fastrtps_cpp
explicit_bad_falls_back rmw_fastrtps_cpp
```

The in-app terminal command that previously failed no longer reports the RMW
library error when run with `rmw_fastrtps_cpp`; quiet topics may still produce no
message before timeout, which is normal for `/parameter_events`.

## Notes

- `./RoboDataset-Studio-V3.sh --help` currently starts the GUI rather than
  printing CLI help. This is not fatal, but it is worth documenting or handling
  later.
- `scripts/run_app.sh --print-env` now prints the selected ROS/RMW environment
  without starting the GUI.
- `pyproject.toml` now includes `paramiko` in the `upload` extra so password/key
  SSH upload support is installed by bootstrap.

## Strict Environment Dependencies

These are the remaining intentional environment dependencies:

- Real ROS listening requires a Linux ROS2 environment with compatible Python
  bindings. On ROS Humble this means Python 3.10.
- `scripts/bootstrap.sh` is Bash-oriented and primarily targets Ubuntu robot
  workstations. Non-Linux systems can still inspect/configure projects, but real
  ROS capture is not expected to work without ROS2 Python bindings.
- In-app ROS terminal commands use `bash -lc` and source `ROS_SETUP`.
- Upload uses `ssh` plus `rsync` or `scp` when available; password/key support
  can use `paramiko`.
- Local FastAPI backend binds to `127.0.0.1` and starts at port `8765`, then the
  frontend searches nearby ports if needed.
- Runtime logs are written under `/tmp` by default.

Adaptation now in place:

- ROS setup file selection checks `ROS_SETUP`, Humble, then Jazzy.
- RMW selection validates the requested implementation and falls back to an
  installed one.
- `--print-env` allows quick environment diagnosis without starting the GUI.
