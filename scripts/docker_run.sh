#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_ROOT="/workspace/robodataset-studio"
IMAGE_NAME="${IMAGE_NAME:-ghcr.io/hikarizg1102/robodataset-studio}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
CONTAINER_NAME="${CONTAINER_NAME:-robodataset-studio}"
IMAGE_REF="${IMAGE_NAME}:${IMAGE_TAG}"
ROS_SETUP="${ROS_SETUP:-}"
CONTAINER_ROS_SETUP="${ROS_SETUP}"
XAUTHORITY_PATH="${XAUTHORITY:-}"
LOCAL_UID="${LOCAL_UID:-${SUDO_UID:-$(id -u)}}"
LOCAL_GID="${LOCAL_GID:-${SUDO_GID:-$(id -g)}}"
declare -a workspace_mounts=()
declare -a ros_setup_chain=()

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

add_ros_setup() {
  local setup_path="$1"
  [[ -n "${setup_path}" && -f "${setup_path}" ]] || return 0
  local existing
  for existing in "${ros_setup_chain[@]}"; do
    [[ "${existing}" == "${setup_path}" ]] && return 0
  done
  ros_setup_chain+=("${setup_path}")
}

build_ros_setup_chain() {
  local root setup_file chain_file
  add_ros_setup "${ROS_SETUP}"
  for candidate in /opt/ros/humble/setup.bash /opt/ros/jazzy/setup.bash /opt/ros/iron/setup.bash; do
    add_ros_setup "${candidate}"
  done
  for root in "${workspace_mounts[@]}"; do
    if [[ -f "${root}/install/setup.bash" ]]; then
      add_ros_setup "${root}/install/setup.bash"
    else
      add_ros_setup "${root}/install/setup.sh"
    fi
  done
  [[ "${#ros_setup_chain[@]}" -gt 0 ]] || return 0
  chain_file="${ROOT_DIR}/.docker_ros_setup.bash"
  {
    printf '#!/usr/bin/env bash\n'
    printf 'set +u\n'
    for setup_file in "${ros_setup_chain[@]}"; do
      printf 'if [ -f %q ]; then source %q; fi\n' "${setup_file}" "${setup_file}"
    done
    printf 'set -u\n'
  } > "${chain_file}"
  ROS_SETUP="${chain_file}"
  CONTAINER_ROS_SETUP="${CONTAINER_ROOT}/.docker_ros_setup.bash"
}

source_ros_setup_for_probe() {
  if [[ -f "${ROS_SETUP}" ]]; then
    set +u
    # shellcheck disable=SC1090
    source "${ROS_SETUP}" >/dev/null 2>&1 || true
    set -u
  fi
}

rmw_available() {
  local name="$1"
  if command -v ros2 >/dev/null 2>&1 && ros2 pkg prefix "${name}" >/dev/null 2>&1; then
    return 0
  fi
  if command -v ldconfig >/dev/null 2>&1 && ldconfig -p 2>/dev/null | grep -q "lib${name}.so"; then
    return 0
  fi
  return 1
}

rmw_graph_score() {
  local name="$1"
  local output count weighted
  output="$(RMW_IMPLEMENTATION="${name}" ROBODATASET_RMW_IMPLEMENTATION="${name}" timeout 3 ros2 topic list -t --no-daemon 2>&1 || true)"
  if [[ -z "${output}" ]]; then
    printf '%s\n' 0
    return
  fi
  count="$(printf '%s\n' "${output}" | grep -v 'RTPS_TRANSPORT_SHM Error\\|Failed init_port\\|open_and_lock_file failed\\|fastrtps_port' | sed '/^[[:space:]]*$/d' | wc -l)"
  weighted="$((count))"
  if printf '%s\n' "${output}" | grep -q 'sensor_msgs/msg/Image'; then weighted="$((weighted + 1000))"; fi
  if printf '%s\n' "${output}" | grep -q 'sensor_msgs/msg/CompressedImage'; then weighted="$((weighted + 800))"; fi
  if printf '%s\n' "${output}" | grep -q 'sensor_msgs/msg/JointState'; then weighted="$((weighted + 1000))"; fi
  if printf '%s\n' "${output}" | grep -Eq 'camera|wrist|joint_states'; then weighted="$((weighted + 500))"; fi
  printf '%s\n' "${weighted}"
}

select_rmw() {
  local requested="${ROBODATASET_RMW_IMPLEMENTATION:-${RMW_IMPLEMENTATION:-}}"
  if [[ -n "${requested}" ]]; then
    RMW_IMPLEMENTATION="${requested}"
    ROBODATASET_RMW_IMPLEMENTATION="${requested}"
    return 0
  fi
  source_ros_setup_for_probe
  local candidates=()
  rmw_available "rmw_fastrtps_cpp" && candidates+=("rmw_fastrtps_cpp")
  rmw_available "rmw_cyclonedds_cpp" && candidates+=("rmw_cyclonedds_cpp")
  rmw_available "rmw_fastrtps_dynamic_cpp" && candidates+=("rmw_fastrtps_dynamic_cpp")
  local best="" best_score="-1" score candidate
  for candidate in "${candidates[@]}"; do
    score="$(rmw_graph_score "${candidate}")"
    if [[ "${score}" -gt "${best_score}" ]]; then
      best="${candidate}"
      best_score="${score}"
    fi
  done
  RMW_IMPLEMENTATION="${best:-rmw_fastrtps_cpp}"
  ROBODATASET_RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION}"
}

detect_ros_workspace_mounts
build_ros_setup_chain
select_rmw

docker_args=(
  --rm
  --name "${CONTAINER_NAME}"
  --privileged
  --network host
  --ipc host
  --pid host
  --user "${LOCAL_UID}:${LOCAL_GID}"
  -e DISPLAY="${DISPLAY:-}"
  -e XAUTHORITY=/workspace/robodataset-studio/.docker.Xauthority
  -e HOME=/workspace/robodataset-studio
  -e QT_X11_NO_MITSHM=1
  -e ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
  -e ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-0}"
  -e ROS_SETUP="${CONTAINER_ROS_SETUP}"
  -e ROBODATASET_RMW_IMPLEMENTATION="${ROBODATASET_RMW_IMPLEMENTATION:-}"
  -e RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-}"
  -e ROBODATASET_DOCKER=1
  -e ROBODATASET_ALLOWED_ROOT="${CONTAINER_ROOT}"
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw
  -v /dev/shm:/dev/shm
  -v "${ROOT_DIR}:${CONTAINER_ROOT}"
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
