#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_NAME="${IMAGE_NAME:-robodataset-studio}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
CONTAINER_NAME="${CONTAINER_NAME:-robodataset-studio}"
IMAGE_REF="${IMAGE_NAME}:${IMAGE_TAG}"
ROS_SETUP="${ROS_SETUP:-}"
XAUTHORITY_PATH="${XAUTHORITY:-}"
declare -a workspace_mounts=()

add_workspace_mount() {
  local mount_path="$1"
  [[ -n "${mount_path}" && -e "${mount_path}" ]] || return 0
  local resolved
  resolved="$(cd "${mount_path}" 2>/dev/null && pwd -P)" || return 0
  local existing
  for existing in "${workspace_mounts[@]}"; do
    [[ "${existing}" == "${resolved}" ]] && return 0
  done
  workspace_mounts+=("${resolved}")
}

detect_ros_workspace_mounts() {
  local prefix root
  if [[ -n "${ROS_WORKSPACE_MOUNTS:-}" ]]; then
    IFS=':' read -r -a workspace_mounts <<< "${ROS_WORKSPACE_MOUNTS}"
    return 0
  fi
  IFS=':' read -r -a prefixes <<< "${COLCON_PREFIX_PATH:-}${AMENT_PREFIX_PATH:+:${AMENT_PREFIX_PATH}}"
  for prefix in "${prefixes[@]}"; do
    [[ -n "${prefix}" && "${prefix}" != /opt/ros/* ]] || continue
    root=""
    if [[ "${prefix}" == */install ]]; then
      root="$(dirname "${prefix}")"
    elif [[ "${prefix}" == */install/* ]]; then
      root="${prefix%%/install/*}"
    fi
    if [[ -n "${root}" ]]; then
      add_workspace_mount "${root}"
    fi
  done
}

if [[ -z "${ROS_SETUP}" ]]; then
  for candidate in /opt/ros/humble/setup.bash /opt/ros/jazzy/setup.bash /opt/ros/iron/setup.bash; do
    if [[ -f "${candidate}" ]]; then
      ROS_SETUP="${candidate}"
      break
    fi
  done
fi
detect_ros_workspace_mounts

docker_args=(
  --rm
  --name "${CONTAINER_NAME}"
  --privileged
  --network host
  --ipc host
  --pid host
  --user "$(id -u):$(id -g)"
  -e DISPLAY="${DISPLAY:-}"
  -e XAUTHORITY=/workspace/robodataset-studio/.docker.Xauthority
  -e HOME=/workspace/robodataset-studio
  -e QT_X11_NO_MITSHM=1
  -e ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
  -e ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-0}"
  -e ROS_SETUP="${ROS_SETUP}"
  -e ROBODATASET_RMW_IMPLEMENTATION="${ROBODATASET_RMW_IMPLEMENTATION:-}"
  -e RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-}"
  -e ROBODATASET_DOCKER=1
  -e ROBODATASET_ALLOWED_ROOT=/workspace/robodataset-studio
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw
  -v /dev/shm:/dev/shm
  -v "${ROOT_DIR}:/workspace/robodataset-studio"
)

if [[ -t 0 && -t 1 ]]; then
  docker_args+=(-it)
fi

if [[ -z "${XAUTHORITY_PATH}" || ! -f "${XAUTHORITY_PATH}" ]]; then
  for candidate in "${HOME}/.Xauthority" "/run/user/$(id -u)/gdm/Xauthority"; do
    if [[ -f "${candidate}" ]]; then
      XAUTHORITY_PATH="${candidate}"
      break
    fi
  done
fi

if [[ -n "${XAUTHORITY_PATH}" && -f "${XAUTHORITY_PATH}" ]]; then
  docker_args+=(-v "${XAUTHORITY_PATH}:/workspace/robodataset-studio/.docker.Xauthority:ro")
fi

if [[ -d /opt/ros ]]; then
  docker_args+=(-v /opt/ros:/opt/ros:ro)
fi

for mount_path in "${workspace_mounts[@]}"; do
  if [[ -n "${mount_path}" && -e "${mount_path}" ]]; then
    docker_args+=(-v "${mount_path}:${mount_path}:ro")
  fi
done

if [[ -n "${PROJECT_MOUNTS:-}" ]]; then
  echo "PROJECT_MOUNTS is ignored in restricted Docker mode; open projects under ${ROOT_DIR}" >&2
fi

if [[ -n "${DISPLAY:-}" ]] && command -v xhost >/dev/null 2>&1; then
  xhost +local:docker >/dev/null 2>&1 || true
fi

docker run "${docker_args[@]}" "${IMAGE_REF}" "$@"
