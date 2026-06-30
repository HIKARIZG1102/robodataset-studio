# RoboDataset Studio

[中文说明](README.zh-CN.md)

RoboDataset Studio is a PySide6 desktop application with a local FastAPI
backend for ROS2-based robot dataset collection. It is listener-first: the app
discovers existing ROS2 nodes and topics, records selected streams, reviews
sessions, merges local files, exports HDF5 datasets, and prepares upload
manifests. It does not send robot control commands by default.

## Features

- Project-first desktop workflow: Project, Config, Collect, Review, Convert,
  Upload, Logs, Settings, and Tutorial.
- Local FastAPI backend started per frontend window, with project-scoped task
  logs and health checks.
- ROS2 graph inspection, topic echo/hz checks, image preview, and listener
  recording.
- Session review, local validation, marks, delete-to-trash behavior, merge, and
  HDF5 export.
- OpenAI-compatible AI review helpers for selected sessions.
- Docker and local installation paths for Ubuntu 22.04 / ROS2 Humble systems.

## Install And Start

Clone the repository first:

```bash
git clone https://github.com/HIKARIZG1102/robodataset-studio.git
cd robodataset-studio
```

Choose one runtime path. You do not need both Docker and local installation.

### Docker Runtime

Docker is the recommended path on a clean machine when you want a packaged
Python/Qt environment. The repository folder is mounted into the container at
`/workspace/robodataset-studio`, so project files created in Docker are normal
host files under the checkout.

Install Docker on Ubuntu if it is not already available:

```bash
sudo apt-get update
sudo apt-get install -y docker.io
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Log out and log back in after `usermod`, or use the sudo command shown below for
the current shell.

Run the published image from the repository root, the directory that contains
`Dockerfile`, `README.md`, and `scripts/`:

```bash
cd robodataset-studio
docker pull ghcr.io/hikarizg1102/robodataset-studio:latest
./scripts/docker_run.sh
```

If Docker still reports permission denied in the current login session:

```bash
cd robodataset-studio
sudo -E env ./scripts/docker_run.sh
```

`scripts/docker_run.sh` computes the repository root from its own location and
mounts that folder into the container. If you start it from somewhere else with
a copied script, Docker will not mount the expected project checkout.

Docker mode intentionally restricts project roots and collection output paths to
the mounted checkout. Use paths under:

```text
/workspace/robodataset-studio
```

The wrapper also mounts `/opt/ros` read-only when it exists and starts Docker
with host networking, host IPC, host PID, privileged mode, and shared
`/dev/shm`. This matches ROS2/DDS discovery behavior on machines where FastDDS
or camera/robot nodes rely on host shared memory and process namespace access.
For ROS2, source the host ROS environment first, then run the same command:

```bash
source /opt/ros/humble/setup.bash
./scripts/docker_run.sh
```

For extra ROS overlay workspaces, source them before launch:

```bash
source /opt/ros/humble/setup.bash
source /path/to/overlay/install/setup.bash
./scripts/docker_run.sh
```

If the launch shell already sourced ROS overlay workspaces, the Docker wrapper
auto-detects workspace roots from `COLCON_PREFIX_PATH` and `AMENT_PREFIX_PATH`
and mounts them read-only. It also creates a temporary setup chain that sources
`/opt/ros` and every detected overlay setup file inside the container. Set
`ROS_WORKSPACE_MOUNTS` only when the automatic detection misses a required
workspace. The container does not directly reuse host `PYTHONPATH` or
`LD_LIBRARY_PATH`; it reconstructs them by sourcing ROS setup files.

Manual override is still available when a workspace is not visible in the
current shell:

```bash
ROS_WORKSPACE_MOUNTS=/path/to/ws1:/path/to/ws2 \
RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
./scripts/docker_run.sh
```

To build the image locally instead of using the published image:

```bash
./scripts/docker_build.sh
./scripts/docker_run.sh
```

### Local Runtime

Local runtime installs a project-local Python 3.10 environment and can read or
write host paths outside the repository.

On Ubuntu 22.04 with ROS2 Humble installed:

```bash
sudo apt-get update
sudo apt-get install -y \
  python3.10-venv fontconfig fonts-noto-cjk \
  libdbus-1-3 libegl1 libgl1 libglib2.0-0 \
  libxcb-cursor0 libxcb-xinerama0 libxkbcommon-x11-0 \
  openssh-client rsync xauth
```

Start the app:

```bash
./RoboDataset-Studio.sh
```

The launcher calls `scripts/bootstrap.sh` on first run and installs the app in
editable mode from `pyproject.toml`. Python 3.10 is expected because ROS2 Humble
Python packages are built for the system Python 3.10 ABI.

Useful overrides:

```bash
ENV_BACKEND=venv PYTHON_BIN=/usr/bin/python3.10 ./scripts/bootstrap.sh
ROS_SETUP=/path/to/install/setup.bash ./RoboDataset-Studio.sh
ROBODATASET_RMW_IMPLEMENTATION=rmw_fastrtps_cpp ./RoboDataset-Studio.sh
```

## ROS2 / DDS Notes

RoboDataset Studio adapts the active ROS2 runtime. DDS/RMW implementations are
not normal pip dependencies of this project; they come from the installed ROS2
environment and robot workspaces.

- Common open-source RMW paths: `rmw_fastrtps_cpp` / FastDDS and
  `rmw_cyclonedds_cpp` / CycloneDDS.
- Other paths can exist when installed: `rmw_fastrtps_dynamic_cpp`,
  `rmw_connextdds`, `rmw_gurumdds_cpp`, and `rmw_zenoh_cpp`.
- Topic visibility depends on `ROS_DOMAIN_ID`, `ROS_LOCALHOST_ONLY`, multicast,
  network routing, QoS, and whether the correct ROS setup file is sourced.
- Vendor/custom message packages are loaded dynamically only when a selected
  topic uses that type. Missing packages are reported as environment/topic
  issues instead of being global install requirements.

Use Settings > Environment in the app to inspect ROS setup, RMW availability,
Python package imports, DDS library visibility, and recommended fixes.

## What Works Without External Services

After installation, local project/config management, Settings, Logs, Tutorial,
simulated collection, session review, local checks, merge, HDF5 export, and
manifest generation can run without a robot.

External state is still required for:

- real ROS recording: visible ROS2 topics matching the project config;
- image monitor: an image or compressed image topic;
- upload/verify: reachable SSH server and credentials;
- AI review: reachable OpenAI-compatible API endpoint, key, and model.

## Development Checks

```bash
python3 -m compileall -q src
QT_QPA_PLATFORM=offscreen python3 -m robodataset_studio.frontend.main
```

Docker build:

```bash
./scripts/docker_build.sh
```
