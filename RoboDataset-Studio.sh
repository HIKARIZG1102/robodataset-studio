#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT_DIR}"

ENV_FILE="${ROOT_DIR}/.robodataset_env"
NEEDS_BOOTSTRAP=0

if [[ ! -f "${ENV_FILE}" ]]; then
  NEEDS_BOOTSTRAP=1
else
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  if [[ -z "${ENV_PYTHON:-}" || ! -x "${ENV_PYTHON}" ]]; then
    NEEDS_BOOTSTRAP=1
  elif ! "${ENV_PYTHON:-${ROOT_DIR}/.venv/bin/python}" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info[:2] == (3, 10) else 1)
PY
  then
    echo "Existing RoboDataset Studio environment is not Python 3.10; rebuilding."
    NEEDS_BOOTSTRAP=1
  elif ! PYTHONPATH="${ROOT_DIR}/src:${PYTHONPATH:-}" "${ENV_PYTHON:-${ROOT_DIR}/.venv/bin/python}" - <<'PY' >/dev/null 2>&1
import importlib
for name in ["PySide6", "fastapi", "uvicorn", "numpy", "h5py", "yaml", "httpx"]:
    importlib.import_module(name)
importlib.import_module("robodataset_studio.frontend.main")
PY
  then
    NEEDS_BOOTSTRAP=1
  fi
fi

if [[ "${NEEDS_BOOTSTRAP}" == "1" ]]; then
  "${ROOT_DIR}/scripts/bootstrap.sh"
fi

exec "${ROOT_DIR}/scripts/run_app.sh" "$@"
