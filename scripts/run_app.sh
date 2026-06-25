#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.robodataset_env"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
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
  if rmw_available "rmw_fastrtps_cpp"; then
    printf '%s\n' "rmw_fastrtps_cpp"
    return
  fi
  if rmw_available "rmw_cyclonedds_cpp"; then
    printf '%s\n' "rmw_cyclonedds_cpp"
    return
  fi
  printf '%s\n' "${requested:-rmw_fastrtps_cpp}"
}

rmw_available() {
  local name="$1"
  if command -v ros2 >/dev/null 2>&1 && ros2 pkg list 2>/dev/null | grep -qx "${name}"; then
    return 0
  fi
  if command -v ldconfig >/dev/null 2>&1 && ldconfig -p 2>/dev/null | grep -q "lib${name}.so"; then
    return 0
  fi
  return 1
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
