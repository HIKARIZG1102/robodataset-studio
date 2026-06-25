FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV QT_X11_NO_MITSHM=1
ENV ROBODATASET_VENV=/opt/robodataset-studio/venv
ENV ROBODATASET_DOCKER=1
ENV ROBODATASET_ALLOWED_ROOT=/workspace/robodataset-studio
ENV PATH=/opt/robodataset-studio/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    python3-pip \
    python3-venv \
    python3-packaging \
    python3-numpy \
    python3-netifaces \
    python3-yaml \
    libpython3.10 \
    libegl1 \
    libdbus-1-3 \
    libfontconfig1 \
    libfreetype6 \
    libfastcdr1 \
    libfastrtps2.5 \
    libfoonathan-memory0.7.1 \
    libgl1 \
    libglib2.0-0 \
    libyaml-cpp0.7 \
    libcunit1 \
    libssl3 \
    libcycloneddsidl0 \
    libiceoryx-binding-c1 \
    libiceoryx-posh1 \
    libiceoryx-utils1 \
    libiceoryx-platform1 \
    libtinyxml2-9 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcb-cursor0 \
    libxcb-glx0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render0 \
    libxcb-render-util0 \
    libxcb-shape0 \
    libxcb-shm0 \
    libxcb-sync1 \
    libxcb-xfixes0 \
    libxcb-xinerama0 \
    libxcb-xkb1 \
    libxkbcommon0 \
    libxkbcommon-x11-0 \
    libspdlog1 \
    openssh-client \
    rsync \
    xauth \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace/robodataset-studio
COPY pyproject.toml README.md ./
COPY src ./src
COPY scripts ./scripts
COPY config ./config
COPY RoboDataset-Studio-V3.sh RoboDataset-Studio-V3-Guide.html ./

RUN mkdir -p /workspace/robodataset-studio/robodataset/projects

RUN python3 -m venv --system-site-packages "${ROBODATASET_VENV}" \
    && "${ROBODATASET_VENV}/bin/python" -m pip install --no-cache-dir --upgrade pip "setuptools>=68,<80" wheel \
    && "${ROBODATASET_VENV}/bin/python" -m pip install --no-cache-dir -e ".[upload]"

RUN printf '%s\n' \
    '#!/usr/bin/env bash' \
    'set -euo pipefail' \
    'cd /workspace/robodataset-studio' \
    'if [[ -n "${ROS_SETUP:-}" && -f "${ROS_SETUP}" ]]; then source "${ROS_SETUP}" >/dev/null 2>&1 || true; fi' \
    'export PATH="${ROBODATASET_VENV:-/opt/robodataset-studio/venv}/bin:${PATH}"' \
    'export PYTHONPATH="/workspace/robodataset-studio/src:${PYTHONPATH:-}"' \
    'export ROS_LOG_DIR="${ROS_LOG_DIR:-/tmp/robodataset_ros_logs}"' \
    'mkdir -p "${ROS_LOG_DIR}"' \
    'exec "${ROBODATASET_VENV:-/opt/robodataset-studio/venv}/bin/python" -m robodataset_studio_v3.frontend.main "$@"' \
    > /usr/local/bin/robodataset-studio && chmod +x /usr/local/bin/robodataset-studio

ENTRYPOINT ["robodataset-studio"]
