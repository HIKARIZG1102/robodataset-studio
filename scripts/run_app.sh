#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROS_SETUP="${ROS_SETUP:-/opt/ros/humble/setup.bash}"

if [[ -f "${ROS_SETUP}" ]]; then
  set +u
  # shellcheck disable=SC1090
  source "${ROS_SETUP}"
  set -u
fi

export PYTHONPATH="${ROOT_DIR}/src:${PYTHONPATH:-}"
if [[ -x "${ROOT_DIR}/.venv/bin/robodataset-studio" ]]; then
  exec "${ROOT_DIR}/.venv/bin/robodataset-studio" "$@"
fi

exec python3 -m robodataset_studio.main "$@"
