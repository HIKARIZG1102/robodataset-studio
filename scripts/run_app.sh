#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.robodataset_env"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
fi

ROS_SETUP="${ROS_SETUP:-/opt/ros/humble/setup.bash}"
if [[ -f "${ROS_SETUP}" ]]; then
  set +u
  # shellcheck disable=SC1090
  source "${ROS_SETUP}"
  set -u
fi

export RMW_IMPLEMENTATION="${ROBODATASET_RMW_IMPLEMENTATION:-rmw_cyclonedds_cpp}"
export PYTHONPATH="${ROOT_DIR}/src:${PYTHONPATH:-}"

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
