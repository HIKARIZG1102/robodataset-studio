#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.robodataset_env"
EXPLICIT_RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-}"
EXPLICIT_ROBODATASET_RMW_IMPLEMENTATION="${ROBODATASET_RMW_IMPLEMENTATION:-}"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
fi
if [[ -n "${EXPLICIT_RMW_IMPLEMENTATION}" ]]; then
  RMW_IMPLEMENTATION="${EXPLICIT_RMW_IMPLEMENTATION}"
else
  unset RMW_IMPLEMENTATION || true
fi
if [[ -n "${EXPLICIT_ROBODATASET_RMW_IMPLEMENTATION}" ]]; then
  ROBODATASET_RMW_IMPLEMENTATION="${EXPLICIT_ROBODATASET_RMW_IMPLEMENTATION}"
else
  unset ROBODATASET_RMW_IMPLEMENTATION || true
fi

select_ros_setup() {
  for candidate in "${ROS_SETUP:-}" /opt/ros/humble/setup.bash /opt/ros/jazzy/setup.bash; do
    if [[ -n "${candidate}" && -f "${candidate}" ]]; then
      printf '%s\n' "${candidate}"
      return
    fi
  done
  printf '%s\n' "${ROS_SETUP:-/opt/ros/humble/setup.bash}"
}

select_rmw() {
  local requested="${ROBODATASET_RMW_IMPLEMENTATION:-${RMW_IMPLEMENTATION:-}}"
  if [[ -n "${requested}" ]] && rmw_available "${requested}"; then
    printf '%s\n' "${requested}"
    return
  fi
  local candidates=()
  rmw_available "rmw_cyclonedds_cpp" && candidates+=("rmw_cyclonedds_cpp")
  rmw_available "rmw_fastrtps_cpp" && candidates+=("rmw_fastrtps_cpp")
  if [[ "${#candidates[@]}" -gt 1 ]]; then
    local best="" best_score="-1" score
    for candidate in "${candidates[@]}"; do
      score="$(rmw_graph_score "${candidate}")"
      if [[ "${score}" -gt "${best_score}" ]]; then
        best="${candidate}"
        best_score="${score}"
      fi
    done
    if [[ -n "${best}" && "${best_score}" -ge 0 ]]; then
      printf '%s\n' "${best}"
      return
    fi
  fi
  if [[ "${#candidates[@]}" -gt 0 ]]; then
    printf '%s\n' "${candidates[0]}"
    return
  fi
  printf '%s\n' "${requested:-rmw_cyclonedds_cpp}"
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
  output="$(RMW_IMPLEMENTATION="${name}" ROBODATASET_RMW_IMPLEMENTATION="${name}" timeout 3 ros2 topic list -t --no-daemon 2>/dev/null || true)"
  if [[ -z "${output}" ]]; then
    printf '%s\n' 0
    return
  fi
  count="$(printf '%s\n' "${output}" | sed '/^[[:space:]]*$/d' | wc -l)"
  weighted="$((count))"
  if printf '%s\n' "${output}" | grep -q 'sensor_msgs/msg/Image'; then weighted="$((weighted + 1000))"; fi
  if printf '%s\n' "${output}" | grep -q 'sensor_msgs/msg/CompressedImage'; then weighted="$((weighted + 800))"; fi
  if printf '%s\n' "${output}" | grep -q 'sensor_msgs/msg/JointState'; then weighted="$((weighted + 1000))"; fi
  if printf '%s\n' "${output}" | grep -Eq 'camera|wrist|wx250s|joint_states'; then weighted="$((weighted + 500))"; fi
  printf '%s\n' "${weighted}"
}

ROS_SETUP="$(select_ros_setup)"
if [[ -f "${ROS_SETUP}" ]]; then
  set +u
  # shellcheck disable=SC1090
  source "${ROS_SETUP}"
  set -u
fi

RMW_IMPLEMENTATION="$(select_rmw)"
export RMW_IMPLEMENTATION
export ROBODATASET_RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION}"
export ROS_SETUP
export ROS_LOG_DIR="${ROS_LOG_DIR:-/tmp/robodataset_ros_logs}"
mkdir -p "${ROS_LOG_DIR}" 2>/dev/null || true
export PYTHONPATH="${ROOT_DIR}/src:${PYTHONPATH:-}"

if [[ "${1:-}" == "--print-env" ]]; then
  echo "ROS_SETUP=${ROS_SETUP}"
  echo "RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION}"
  echo "ROBODATASET_RMW_IMPLEMENTATION=${ROBODATASET_RMW_IMPLEMENTATION}"
  echo "ROS_LOG_DIR=${ROS_LOG_DIR}"
  echo "ENV_PYTHON=${ENV_PYTHON:-}"
  exit 0
fi

if [[ -n "${ENV_PYTHON:-}" && -x "${ENV_PYTHON}" ]]; then
  if [[ -n "${ENV_PYTHON:-}" ]] && ! "${ENV_PYTHON}" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info[:2] == (3, 10) else 1)
PY
  then
    echo "Configured environment is not Python 3.10. Run scripts/bootstrap.sh first." >&2
    exit 1
  fi
  exec "${ENV_PYTHON}" -m robodataset_studio_v3.frontend.main "$@"
fi

if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  exec "${ROOT_DIR}/.venv/bin/python" -m robodataset_studio_v3.frontend.main "$@"
fi

if [[ -x "${ROOT_DIR}/.conda-env/bin/python" ]]; then
  exec "${ROOT_DIR}/.conda-env/bin/python" -m robodataset_studio_v3.frontend.main "$@"
fi

exec python3 -m robodataset_studio_v3.frontend.main "$@"
