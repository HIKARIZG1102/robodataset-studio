#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESKTOP_DEPS="${ROOT_DIR}/scripts/desktop_deps.sh"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3.10}"
VENV_DIR="${VENV_DIR:-${ROOT_DIR}/.venv}"
CONDA_EXE="${CONDA_EXE:-$(command -v conda || true)}"
CONDA_ENV_DIR="${CONDA_ENV_DIR:-${ROOT_DIR}/.conda-env}"
ENV_BACKEND="${ENV_BACKEND:-auto}"
ROS_SETUP="${ROS_SETUP:-/opt/ros/humble/setup.bash}"
FASTDDS_NO_SHM_PROFILE="${ROOT_DIR}/config/fastdds_no_shm.xml"
ROBODATASET_RMW_IMPLEMENTATION="${ROBODATASET_RMW_IMPLEMENTATION:-rmw_cyclonedds_cpp}"

# shellcheck disable=SC1090
source "${DESKTOP_DEPS}"

source_ros() {
  if [[ -f "${ROS_SETUP}" ]]; then
    set +u
    # shellcheck disable=SC1090
    source "${ROS_SETUP}"
    set -u
  else
    echo "Warning: ROS setup not found: ${ROS_SETUP}" >&2
    echo "UI and mock workflows can run, but real ROS2 recording requires ROS2 Humble." >&2
  fi
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

python_version() {
  "$1" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
}

check_python310() {
  local python_path="$1"
  local version
  version="$(python_version "${python_path}")"
  if [[ "${version}" != "3.10" && "${ALLOW_NON_ROS_PYTHON:-0}" != "1" ]]; then
    echo "Python 3.10 is required for ROS2 Humble rclpy bindings; got ${version} from ${python_path}." >&2
    echo "Set ALLOW_NON_ROS_PYTHON=1 only for UI/mock workflows without real ROS2 recording." >&2
    return 1
  fi
}

create_venv() {
  if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "Python executable not found: ${PYTHON_BIN}" >&2
    return 1
  fi
  check_python310 "${PYTHON_BIN}" || return 1
  if [[ ! -d "${VENV_DIR}" ]]; then
    "${PYTHON_BIN}" -m venv "${VENV_DIR}" || {
      echo "Failed to create venv with ${PYTHON_BIN}." >&2
      echo "On Ubuntu 22.04 install: sudo apt install python3.10-venv" >&2
      if command -v sudo >/dev/null 2>&1 && install_python_venv_package; then
        "${PYTHON_BIN}" -m venv "${VENV_DIR}" || return 1
      else
        return 1
      fi
    }
  fi
  ENV_PYTHON="${VENV_DIR}/bin/python"
  ENV_COMMAND="${VENV_DIR}/bin/robodataset-studio"
  ENV_KIND="venv"
}

create_conda_env() {
  if [[ -z "${CONDA_EXE}" || ! -x "${CONDA_EXE}" ]]; then
    echo "conda not found. Install python3.10-venv or set CONDA_EXE=/path/to/conda." >&2
    return 1
  fi
  if [[ ! -d "${CONDA_ENV_DIR}" ]]; then
    "${CONDA_EXE}" create -y -p "${CONDA_ENV_DIR}" python=3.10 pip
  fi
  ENV_PYTHON="${CONDA_ENV_DIR}/bin/python"
  ENV_COMMAND="${CONDA_ENV_DIR}/bin/robodataset-studio"
  ENV_KIND="conda"
  check_python310 "${ENV_PYTHON}" || return 1
}

source_ros

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

"${ENV_PYTHON}" -m pip install --upgrade pip setuptools wheel || {
  echo "Warning: pip build-tool upgrade failed; continuing with the existing local environment." >&2
}
if ! "${ENV_PYTHON}" -m pip install -e "${ROOT_DIR}[dev,upload]"; then
  echo "Editable install failed, retrying without build isolation for offline/local environments." >&2
  "${ENV_PYTHON}" -m pip install --no-build-isolation -e "${ROOT_DIR}[dev,upload]"
fi
qt_install_desktop_dependencies_if_requested "${ENV_PYTHON}" || true

cat > "${ROOT_DIR}/.robodataset_env" <<EOF
ENV_KIND=${ENV_KIND}
ENV_PYTHON=${ENV_PYTHON}
ENV_COMMAND=${ENV_COMMAND}
ROS_SETUP=${ROS_SETUP}
FASTDDS_NO_SHM_PROFILE=${FASTDDS_NO_SHM_PROFILE}
ROBODATASET_RMW_IMPLEMENTATION=${ROBODATASET_RMW_IMPLEMENTATION}
EOF

cat > "${ROOT_DIR}/RoboDataset-Studio.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ROOT_DIR}/.robodataset_env"
DESKTOP_DEPS="${ROOT_DIR}/scripts/desktop_deps.sh"

# shellcheck disable=SC1090
source "${DESKTOP_DEPS}"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
else
  ENV_COMMAND="${ROOT_DIR}/.venv/bin/robodataset-studio"
  ROS_SETUP="${ROS_SETUP:-/opt/ros/humble/setup.bash}"
fi

if [[ -f "${ROS_SETUP}" ]]; then
  set +u
  # shellcheck disable=SC1090
  source "${ROS_SETUP}"
  set -u
fi

if [[ "${ROBODATASET_DISABLE_FASTDDS_SHM:-1}" == "1" && -f "${FASTDDS_NO_SHM_PROFILE:-}" ]]; then
  export RMW_IMPLEMENTATION="${ROBODATASET_RMW_IMPLEMENTATION:-rmw_cyclonedds_cpp}"
  export FASTDDS_DEFAULT_PROFILES_FILE="${FASTDDS_NO_SHM_PROFILE}"
  export FASTRTPS_DEFAULT_PROFILES_FILE="${FASTDDS_NO_SHM_PROFILE}"
fi

if [[ -n "${DISPLAY:-}" && "${QT_QPA_PLATFORM:-}" != "offscreen" && -n "${ENV_PYTHON:-}" ]]; then
  qt_install_desktop_dependencies_if_requested "${ENV_PYTHON}" || exit 1
fi

export PYTHONPATH="${ROOT_DIR}/src:${PYTHONPATH:-}"
exec "${ENV_COMMAND}" "$@"
EOF
chmod +x "${ROOT_DIR}/RoboDataset-Studio.sh"

cat > "${ROOT_DIR}/RoboDataset-Studio.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=RoboDataset Studio
Comment=ROS2 listener-only robot dataset collection workbench
Exec=${ROOT_DIR}/RoboDataset-Studio.sh
Path=${ROOT_DIR}
Terminal=false
Categories=Development;Science;Robotics;
EOF
chmod +x "${ROOT_DIR}/RoboDataset-Studio.desktop"

"${ENV_PYTHON}" - <<'PY'
import importlib

required = ["PySide6", "numpy", "h5py", "yaml", "pytest"]
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
    print(f"rclpy: unavailable ({exc})")
print("RoboDataset Studio bootstrap complete.")
PY

echo "Environment: ${ENV_KIND}"
echo "Python: ${ENV_PYTHON}"
echo "Launcher: ${ROOT_DIR}/RoboDataset-Studio.sh"
echo "Desktop entry: ${ROOT_DIR}/RoboDataset-Studio.desktop"
