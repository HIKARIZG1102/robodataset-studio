#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3.10}"
VENV_DIR="${VENV_DIR:-${ROOT_DIR}/.venv}"
CONDA_EXE="${CONDA_EXE:-$(command -v conda || true)}"
CONDA_ENV_DIR="${CONDA_ENV_DIR:-${ROOT_DIR}/.conda-env}"
ENV_BACKEND="${ENV_BACKEND:-auto}"
ROS_SETUP="${ROS_SETUP:-/opt/ros/humble/setup.bash}"
ROBODATASET_RMW_IMPLEMENTATION="${ROBODATASET_RMW_IMPLEMENTATION:-rmw_cyclonedds_cpp}"

python_version() {
  "$1" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
}

check_python() {
  local python_path="$1"
  local version
  version="$(python_version "${python_path}")"
  case "${version}" in
    3.10|3.11|3.12|3.13) return 0 ;;
    *)
      echo "Python >=3.10 is required; got ${version} from ${python_path}." >&2
      return 1
      ;;
  esac
}

install_python_venv_package() {
  case "${AUTO_INSTALL_SYSTEM_DEPS:-ask}" in
    1|yes|true)
      sudo apt-get update
      sudo apt-get install -y python3.10-venv
      ;;
    0|no|false)
      return 1
      ;;
    ask|*)
      if [[ -t 0 ]]; then
        read -r -p "Install python3.10-venv with sudo now? [Y/n] " answer
        case "${answer}" in
          n|N|no|NO) return 1 ;;
          *)
            sudo apt-get update
            sudo apt-get install -y python3.10-venv
            ;;
        esac
      else
        return 1
      fi
      ;;
  esac
}

create_venv() {
  if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "Python executable not found: ${PYTHON_BIN}" >&2
    return 1
  fi
  check_python "${PYTHON_BIN}" || return 1
  if [[ ! -d "${VENV_DIR}" ]]; then
    "${PYTHON_BIN}" -m venv "${VENV_DIR}" || {
      echo "Failed to create venv with ${PYTHON_BIN}." >&2
      if command -v sudo >/dev/null 2>&1 && install_python_venv_package; then
        "${PYTHON_BIN}" -m venv "${VENV_DIR}" || return 1
      else
        return 1
      fi
    }
  fi
  ENV_PYTHON="${VENV_DIR}/bin/python"
  ENV_COMMAND="${VENV_DIR}/bin/robodataset-studio-v3"
  ENV_KIND="venv"
}

create_conda_env() {
  if [[ -z "${CONDA_EXE}" || ! -x "${CONDA_EXE}" ]]; then
    echo "conda not found. Install python3-venv or set CONDA_EXE=/path/to/conda." >&2
    return 1
  fi
  if [[ ! -d "${CONDA_ENV_DIR}" ]]; then
    "${CONDA_EXE}" create -y -p "${CONDA_ENV_DIR}" python=3.10 pip
  fi
  ENV_PYTHON="${CONDA_ENV_DIR}/bin/python"
  ENV_COMMAND="${CONDA_ENV_DIR}/bin/robodataset-studio-v3"
  ENV_KIND="conda"
  check_python "${ENV_PYTHON}" || return 1
}

case "${ENV_BACKEND}" in
  venv)
    create_venv
    ;;
  conda)
    create_conda_env
    ;;
  auto)
    if ! create_venv; then
      echo "Falling back to a project-local conda environment." >&2
      create_conda_env
    fi
    ;;
  *)
    echo "Unknown ENV_BACKEND=${ENV_BACKEND}. Use auto, venv, or conda." >&2
    exit 1
    ;;
esac

"${ENV_PYTHON}" -m pip install --upgrade pip setuptools wheel || true
if ! "${ENV_PYTHON}" -m pip install -e "${ROOT_DIR}[dev,upload]"; then
  echo "Editable install failed, retrying without build isolation." >&2
  "${ENV_PYTHON}" -m pip install --no-build-isolation -e "${ROOT_DIR}[dev,upload]"
fi

cat > "${ROOT_DIR}/.robodataset_env" <<EOF
ENV_KIND=${ENV_KIND}
ENV_PYTHON=${ENV_PYTHON}
ENV_COMMAND=${ENV_COMMAND}
ROS_SETUP=${ROS_SETUP}
ROBODATASET_RMW_IMPLEMENTATION=${ROBODATASET_RMW_IMPLEMENTATION}
EOF

"${ENV_PYTHON}" - <<'PY'
import importlib

required = ["PySide6", "fastapi", "uvicorn", "numpy", "h5py", "yaml", "httpx"]
missing = []
for name in required:
    try:
        importlib.import_module(name)
    except Exception as exc:
        missing.append(f"{name}: {exc}")
if missing:
    raise SystemExit("\n".join(missing))
try:
    importlib.import_module("rclpy")
    print("rclpy: OK")
except Exception as exc:
    print(f"rclpy: unavailable ({exc}); real ROS recording needs ROS2 sourced before launch")
print("RoboDataset Studio V3 bootstrap complete.")
PY

echo "Environment: ${ENV_KIND}"
echo "Python: ${ENV_PYTHON}"
echo "Command: ${ENV_COMMAND}"
echo "Launcher: ${ROOT_DIR}/RoboDataset-Studio-V3.sh"
