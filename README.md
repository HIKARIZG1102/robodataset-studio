# RoboDataset Studio

RoboDataset Studio is a fresh project for the next architecture:

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

## ROS2-First Communication Scope

RoboDataset Studio is primarily a ROS2 listener-based robot dataset tool.
It is designed to discover existing ROS2 nodes/topics, subscribe to selected
streams, record synchronized dataset samples, review sessions, convert outputs,
and upload results. It does not send robot control commands by default.

The software must adapt several communication layers:

- ROS setup/workspaces: `ROS_SETUP`, overlay workspaces, Python ABI compatibility
  with `rclpy`, `sensor_msgs`, and other ROS2 Python packages.
- RMW/DDS: `rmw_fastrtps_cpp` / FastDDS and `rmw_cyclonedds_cpp` / CycloneDDS
  are the common open-source paths. `rmw_fastrtps_dynamic_cpp`,
  `rmw_connextdds`, `rmw_gurumdds_cpp`, and `rmw_zenoh_cpp` are detected when
  installed, but vendor DDS stacks may require separate runtimes/licenses.
  DDS/RMW is part of the ROS2 runtime installed on the robot workstation; it is
  not a normal `pip` dependency of this app.
- DDS transport and discovery: UDP/multicast, loopback/local-only mode,
  `ROS_DOMAIN_ID`, `ROS_LOCALHOST_ONLY`, shared-memory transport, LAN/VPN
  behavior, and FastDDS SHM failure modes.
  Nodes from another workstation can appear in the graph when they share the
  same DDS domain and network. That is live ROS2 discovery, not project data
  stored in the repository. Use a separate `ROS_DOMAIN_ID` or
  `ROS_LOCALHOST_ONLY=1` for local-only tests.
- QoS: image/sensor topics usually require sensor-data QoS, while state and
  metadata topics may use different reliability/durability settings.
- ROS message families: images, compressed images, joint states, IMU, odometry,
  geometry messages, and common `std_msgs` scalar/array topics.
  Vendor/custom message packages are not hard-coded as global dependencies.
  When a selected topic uses a custom type, Studio tries to load that exact
  `package/msg/Type` through the active ROS workspace and reports that topic's
  missing package if it is unavailable.
- Image encodings: `rgb8`, `bgr8`, `mono8`, `16UC1`, `16SC1`, `32FC1`, padded
  row strides, endian handling, and compressed JPEG/PNG-style streams.
- Dataset storage mapping: ROS messages must be converted into arrays,
  extension streams, metadata, and CALVIN-compatible keys without silently
  dropping unsupported data.

When a layer is unsupported or misconfigured, V3 should surface an explicit
warning or error with the topic, message type, encoding, RMW, or environment
detail instead of failing silently.

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

`run_app.sh` sources the first available ROS setup file from `ROS_SETUP`,
`/opt/ros/humble/setup.bash`, or `/opt/ros/jazzy/setup.bash`. It auto-selects
an installed RMW implementation by probing the ROS graph. Settings >
Environment also reports missing RMW shared libraries, missing ros2 CLI Python
modules, and graph probe errors. Override these when needed:

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

## Docker Packaging

The repository also includes a generic Docker wrapper named
`robodataset-studio` rather than `robodataset-studio-v3`. The Docker image is
intended to package only the Studio GUI, local FastAPI backend, Python
dependencies, and upload tools. The image contains the application source and
creates a container-local virtual environment at
`/opt/robodataset-studio/venv`, installing the same runtime dependencies that
the local bootstrap would normally install. It does not install ROS inside the
image. Instead, the run wrapper passes through the host ROS environment so the
container matches the machine that is already publishing ROS2 topics:

Install Docker on Ubuntu 22.04:

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 docker-buildx
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
newgrp docker
docker version
docker compose version
```

If Docker Hub is slow or blocked, configure the Docker daemon to use the local
proxy available on that machine. For example, with a Clash HTTP proxy on
`127.0.0.1:7890`:

```bash
sudo mkdir -p /etc/systemd/system/docker.service.d
sudo tee /etc/systemd/system/docker.service.d/proxy.conf >/dev/null <<'EOF'
[Service]
Environment="HTTP_PROXY=http://127.0.0.1:7890"
Environment="HTTPS_PROXY=http://127.0.0.1:7890"
Environment="NO_PROXY=localhost,127.0.0.1,::1"
EOF
sudo systemctl daemon-reload
sudo systemctl restart docker
```

Build and run the local image:

```bash
./scripts/docker_build.sh
./scripts/docker_run.sh
```

Equivalent Compose workflow:

```bash
LOCAL_UID=$(id -u) LOCAL_GID=$(id -g) docker compose up --build robodataset-studio
```

After the GitHub Actions Docker workflow publishes a package, users can run a
prebuilt image without building locally:

```bash
docker pull ghcr.io/hikarizg1102/robodataset-studio:latest
IMAGE_NAME=ghcr.io/hikarizg1102/robodataset-studio ./scripts/docker_run.sh
```

The container uses host networking and X11 forwarding by default so the GUI can
open and the ROS2 graph can be discovered from the same ROS domain:

- Image name: `robodataset-studio:latest`
- Container command: `robodataset-studio`
- Container venv: `/opt/robodataset-studio/venv`
- App path inside container: `/workspace/robodataset-studio`
- Default workspace mount: host repository root to container
  `/workspace/robodataset-studio`
- Docker path policy: project roots, recording output, review/convert inputs,
  export outputs, upload local paths, and SSH key paths must stay under
  `/workspace/robodataset-studio`
- GUI forwarding: `DISPLAY`, `/tmp/.X11-unix`, and Xauthority. The run script
  mounts `$XAUTHORITY` first, then falls back to `~/.Xauthority` or
  `/run/user/$(id -u)/gdm/Xauthority`.
- ROS passthrough: host network, `/opt/ros:/opt/ros:ro`, `ROS_SETUP`,
  `ROS_DOMAIN_ID`, `ROS_LOCALHOST_ONLY`, RMW, `PYTHONPATH`, `LD_LIBRARY_PATH`,
  and colcon/ament prefix variables

If the GUI fails with `Authorization required`, `could not connect to display`,
or a Qt `xcb` platform initialization error, check the host display and
Xauthority path:

```bash
echo "$DISPLAY"
echo "$XAUTHORITY"
ls -l "$XAUTHORITY"
XAUTHORITY=/run/user/$(id -u)/gdm/Xauthority ./scripts/docker_run.sh
```

On desktops where `xhost` can access the active display, this can also unblock
local containers:

```bash
xhost +local:docker
./scripts/docker_run.sh
```

A fully expanded GUI run command, equivalent to the wrapper, is:

```bash
docker run --rm --name robodataset-studio \
  --network host --ipc host \
  --user "$(id -u):$(id -g)" \
  -e DISPLAY="$DISPLAY" \
  -e XAUTHORITY=/workspace/robodataset-studio/.docker.Xauthority \
  -e HOME=/workspace/robodataset-studio \
  -e QT_X11_NO_MITSHM=1 \
  -e ROS_SETUP="${ROS_SETUP:-/opt/ros/humble/setup.bash}" \
  -e ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}" \
  -e ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-0}" \
  -e ROBODATASET_RMW_IMPLEMENTATION="${ROBODATASET_RMW_IMPLEMENTATION:-}" \
  -e RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-}" \
  -e AMENT_PREFIX_PATH="${AMENT_PREFIX_PATH:-}" \
  -e CMAKE_PREFIX_PATH="${CMAKE_PREFIX_PATH:-}" \
  -e COLCON_PREFIX_PATH="${COLCON_PREFIX_PATH:-}" \
  -e LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}" \
  -e PYTHONPATH="${PYTHONPATH:-}" \
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
  -v "${XAUTHORITY:-/run/user/$(id -u)/gdm/Xauthority}:/workspace/robodataset-studio/.docker.Xauthority:ro" \
  -e ROBODATASET_DOCKER=1 \
  -e ROBODATASET_ALLOWED_ROOT=/workspace/robodataset-studio \
  -v "$PWD:/workspace/robodataset-studio" \
  -v /opt/ros:/opt/ros:ro \
  robodataset-studio:latest
```

Useful checks:

```bash
docker run --rm --entrypoint /opt/robodataset-studio/venv/bin/python \
  robodataset-studio:latest \
  -c 'import robodataset_studio_v3, PySide6, fastapi, numpy; print("import-ok", numpy.__version__)'

docker ps --filter name=robodataset-studio
docker logs --tail 120 robodataset-studio
docker rm -f robodataset-studio
```

The default Docker run mounts the current checkout over the app path. This
makes the container use the same visible project tree as the cloned repository
on the host:

```bash
./scripts/docker_run.sh
```

If your ROS overlay workspace is outside `/opt/ros`, pass it through with a
colon-separated list:

```bash
ROS_SETUP=/path/to/overlay/install/setup.bash \
ROS_WORKSPACE_MOUNTS=/path/to/overlay:/another/overlay \
./scripts/docker_run.sh
```

Docker mode intentionally keeps Studio file operations inside the cloned
repository folder. The run wrapper mounts the host checkout as:

```bash
$PWD:/workspace/robodataset-studio
```

In the GUI, create/open projects under `/workspace/robodataset-studio`, for
example `/workspace/robodataset-studio/robodataset/projects`. Attempts to open
or write project roots, collection sessions, review folders, conversion output,
upload local paths, or SSH key paths outside that workspace are rejected with a
clear error. This keeps Docker behavior predictable and ensures files are
visible from the host clone.

The run wrapper starts the container with the current host UID/GID, so files
created by recording, review, conversion, and upload manifest generation remain
editable from the host file manager.

Docker and host launches can run at the same time. Each PySide window starts
its own FastAPI backend on the first free local port, so a Docker window and a
host/git-clone window do not share backend state. Concurrent writes to the same
project are protected by `.robodataset.lock` in the project root: recording and
simulated recording refuse to start when another backend is already writing that
project. Session folders also include microseconds and the backend PID in their
name to avoid accidental name collisions.

Do not mount the host root `/` over the container root `/`. That hides the
container's Ubuntu system, Python environment, and Studio installation. The
supported Docker workflow is intentionally limited to the cloned repository
folder.

The default image is based on Ubuntu 22.04 with Python 3.10, which matches ROS
Humble's Python ABI. If the host ROS installation uses a different Python ABI,
use a matching derived Docker base image or run the app directly on the host.

This image includes Studio's software dependencies but does not include ROS,
hardware-specific drivers, vendor SDKs, or custom robot workspaces. For broad
use, keep those on the host and publish ROS2 topics from the host. If direct
device access is needed inside the container, extend `scripts/docker_run.sh` or
`docker-compose.yml` with the appropriate `--device` or volume mounts for that
machine.

Upload server fields are stored in the reusable total config under `upload`.
After a project loads a total config, the Upload page reads host, port,
username, password/key path, and remote root from that project config. Separate
server profiles in local settings are no longer used. The Upload page refreshes
from the current project config while it is open.

ROS listener selections are stored in the reusable total config under `ros`.
They are not written into `dataset_config.yaml`; the dataset config only keeps
the derived stream, state, action, recording, and schema description.

## Backend Startup

Each PySide frontend starts its own local FastAPI backend. The first window
tries `http://127.0.0.1:8765`; if that port is occupied, the frontend tries the
next local ports. Shutdown only stops the backend process started by that
window.

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

AI calls use OpenAI-compatible endpoints. Configure them in `Settings -> AI`:

- Base URL, API key, model, and timeout.
- Prompt budget, default `120000` characters.
- Probe stdout budget, default `12000` characters.

The key is stored only in local settings and is not written to
`project_config.yaml`, `dataset_config.yaml`, or reusable total configs. The
environment variable `ROBOT_DATA_AI_API_KEY` is still accepted as a fallback for
backend-only debugging.

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

When creating a project, the project root defaults to the relative path
`robodataset/projects`. In a normal host/git-clone run, operators may browse to
an external disk when they intentionally want project data outside the
repository. In Docker mode, file operations are restricted to the mounted clone
at `/workspace/robodataset-studio`, so create projects under that workspace.

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
