#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT_DIR}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
export PYTHONPATH="${ROOT_DIR}/src:${PYTHONPATH:-}"

exec "${PYTHON_BIN}" -m robodataset_studio_v3.frontend.main
