#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_NAME="${IMAGE_NAME:-robodataset-studio}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
CONTAINER_NAME="${CONTAINER_NAME:-robodataset-studio}"
IMAGE_REF="${IMAGE_NAME}:${IMAGE_TAG}"
DATA_DIR="${ROBODATASET_DOCKER_DATA_DIR:-${ROOT_DIR}/robodataset}"
MOUNT_SOURCE="${ROBODATASET_DOCKER_MOUNT_SOURCE:-0}"
ROS_SETUP="${ROS_SETUP:-}"
if [[ -z "${ROS_SETUP}" ]]; then
  for candidate in /opt/ros/humble/setup.bash /opt/ros/jazzy/setup.bash /opt/ros/iron/setup.bash; do
    if [[ -f "${candidate}" ]]; then
      ROS_SETUP="${candidate}"
      break
    fi
  done
fi

docker_args=(
  --rm
  --name "${CONTAINER_NAME}"
  --network host
  --ipc host
  -e DISPLAY="${DISPLAY:-}"
  -e QT_X11_NO_MITSHM=1
  -e ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
  -e ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-0}"
  -e ROS_SETUP="${ROS_SETUP}"
  -e ROBODATASET_RMW_IMPLEMENTATION="${ROBODATASET_RMW_IMPLEMENTATION:-rmw_cyclonedds_cpp}"
  -e RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-}"
  -e AMENT_PREFIX_PATH="${AMENT_PREFIX_PATH:-}"
  -e CMAKE_PREFIX_PATH="${CMAKE_PREFIX_PATH:-}"
  -e COLCON_PREFIX_PATH="${COLCON_PREFIX_PATH:-}"
  -e LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}"
  -e PYTHONPATH="${PYTHONPATH:-}"
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw
  -v "${DATA_DIR}:/workspace/robodataset-studio/robodataset"
)

mkdir -p "${DATA_DIR}"

if [[ -t 0 && -t 1 ]]; then
  docker_args+=(-it)
fi

if [[ "${MOUNT_SOURCE}" == "1" || "${MOUNT_SOURCE}" == "true" || "${MOUNT_SOURCE}" == "yes" ]]; then
  docker_args+=(-v "${ROOT_DIR}:/workspace/robodataset-studio")
fi

if [[ -f "${HOME}/.Xauthority" ]]; then
  docker_args+=(-v "${HOME}/.Xauthority:/root/.Xauthority:ro")
fi

if [[ -d /opt/ros ]]; then
  docker_args+=(-v /opt/ros:/opt/ros:ro)
fi

if [[ -n "${ROS_WORKSPACE_MOUNTS:-}" ]]; then
  IFS=':' read -r -a workspace_mounts <<< "${ROS_WORKSPACE_MOUNTS}"
  for mount_path in "${workspace_mounts[@]}"; do
    if [[ -n "${mount_path}" && -e "${mount_path}" ]]; then
      docker_args+=(-v "${mount_path}:${mount_path}:ro")
    fi
  done
fi

if [[ -n "${PROJECT_MOUNTS:-}" ]]; then
  IFS=':' read -r -a project_mounts <<< "${PROJECT_MOUNTS}"
  for mount_path in "${project_mounts[@]}"; do
    if [[ -n "${mount_path}" && -e "${mount_path}" ]]; then
      docker_args+=(-v "${mount_path}:${mount_path}:rw")
    fi
  done
fi

if [[ -n "${DISPLAY:-}" ]] && command -v xhost >/dev/null 2>&1; then
  xhost +local:docker >/dev/null 2>&1 || true
fi

docker run "${docker_args[@]}" "${IMAGE_REF}" "$@"
