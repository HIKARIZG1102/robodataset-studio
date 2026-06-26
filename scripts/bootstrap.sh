#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3.10}"
VENV_DIR="${VENV_DIR:-${ROOT_DIR}/.venv}"
CONDA_EXE="${CONDA_EXE:-$(command -v conda || true)}"
CONDA_ENV_DIR="${CONDA_ENV_DIR:-${ROOT_DIR}/.conda-env}"
ENV_BACKEND="${ENV_BACKEND:-auto}"
SYSTEM_RUNTIME_PACKAGES=(
  fontconfig
  fonts-noto-cjk
  libdbus-1-3
  libegl1
  libgl1
  libglib2.0-0
  libxcb-cursor0
  libxcb-xinerama0
  libxkbcommon-x11-0
  openssh-client
  rsync
  xauth
)

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
  if [[ -f "${ROS_SETUP}" ]]; then
    set +u
    # shellcheck disable=SC1090
    source "${ROS_SETUP}" >/dev/null 2>&1 || true
    set -u
  fi
  local candidates=()
  rmw_available "rmw_cyclonedds_cpp" && candidates+=("rmw_cyclonedds_cpp")
  rmw_available "rmw_fastrtps_cpp" && candidates+=("rmw_fastrtps_cpp")
  rmw_available "rmw_fastrtps_dynamic_cpp" && candidates+=("rmw_fastrtps_dynamic_cpp")
  rmw_available "rmw_connextdds" && candidates+=("rmw_connextdds")
  rmw_available "rmw_gurumdds_cpp" && candidates+=("rmw_gurumdds_cpp")
  rmw_available "rmw_zenoh_cpp" && candidates+=("rmw_zenoh_cpp")
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
  printf '%s\n' "${requested:-rmw_fastrtps_cpp}"
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
  if printf '%s\n' "${output}" | grep -qE 'RTPS_TRANSPORT_SHM Error|Failed init_port|open_and_lock_file failed|fastrtps_port'; then weighted="$((weighted - 5000))"; fi
  if printf '%s\n' "${output}" | grep -q 'sensor_msgs/msg/Image'; then weighted="$((weighted + 1000))"; fi
  if printf '%s\n' "${output}" | grep -q 'sensor_msgs/msg/CompressedImage'; then weighted="$((weighted + 800))"; fi
  if printf '%s\n' "${output}" | grep -q 'sensor_msgs/msg/JointState'; then weighted="$((weighted + 1000))"; fi
  if printf '%s\n' "${output}" | grep -Eq 'camera|wrist|wx250s|joint_states'; then weighted="$((weighted + 500))"; fi
  printf '%s\n' "${weighted}"
}

install_system_runtime_packages() {
  local packages=("$@")
  if [[ "${#packages[@]}" -eq 0 ]]; then
    return 0
  fi
  if ! command -v sudo >/dev/null 2>&1; then
    return 1
  fi
  sudo apt-get update
  sudo apt-get install -y "${packages[@]}"
}

ensure_system_runtime_packages() {
  if ! command -v apt-get >/dev/null 2>&1 || ! command -v dpkg-query >/dev/null 2>&1; then
    return 0
  fi
  local missing=()
  local package
  for package in "${SYSTEM_RUNTIME_PACKAGES[@]}"; do
    if ! dpkg-query -W -f='${Status}' "${package}" 2>/dev/null | grep -q "install ok installed"; then
      missing+=("${package}")
    fi
  done
  if [[ "${#missing[@]}" -eq 0 ]]; then
    return 0
  fi
  echo "Missing recommended system runtime packages: ${missing[*]}" >&2
  case "${AUTO_INSTALL_SYSTEM_DEPS:-ask}" in
    1|yes|true)
      install_system_runtime_packages "${missing[@]}" || true
      ;;
    0|no|false)
      echo "Install them manually if Qt, Chinese text, or upload tools fail:" >&2
      echo "  sudo apt-get update && sudo apt-get install -y ${missing[*]}" >&2
      ;;
    ask|*)
      if [[ -t 0 ]]; then
        read -r -p "Install recommended system runtime packages with sudo now? [Y/n] " answer
        case "${answer}" in
          n|N|no|NO)
            echo "Install them manually if Qt, Chinese text, or upload tools fail:" >&2
            echo "  sudo apt-get update && sudo apt-get install -y ${missing[*]}" >&2
            ;;
          *)
            install_system_runtime_packages "${missing[@]}" || true
            ;;
        esac
      else
        echo "Install them manually if Qt, Chinese text, or upload tools fail:" >&2
        echo "  sudo apt-get update && sudo apt-get install -y ${missing[*]}" >&2
      fi
      ;;
  esac
}

ROS_SETUP="$(select_ros_setup)"
ROBODATASET_RMW_IMPLEMENTATION="$(select_rmw)"
ensure_system_runtime_packages

python_version() {
  "$1" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
}

check_pip() {
  "$1" -c 'import pip' >/dev/null 2>&1
}

check_python() {
  local python_path="$1"
  local version
  version="$(python_version "${python_path}")"
  case "${version}" in
    3.10) return 0 ;;
    *)
      echo "Python 3.10 is required for ROS Humble compatibility; got ${version} from ${python_path}." >&2
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
  if [[ -x "${VENV_DIR}/bin/python" ]] && ! check_python "${VENV_DIR}/bin/python"; then
    echo "Existing venv is not Python 3.10; rebuilding ${VENV_DIR}." >&2
    rm -rf "${VENV_DIR}"
  fi
  if [[ ! -d "${VENV_DIR}" ]]; then
    "${PYTHON_BIN}" -m venv --system-site-packages "${VENV_DIR}" || "${PYTHON_BIN}" -m venv --system-site-packages --without-pip "${VENV_DIR}" || {
      echo "Failed to create venv with ${PYTHON_BIN}." >&2
      if command -v sudo >/dev/null 2>&1 && install_python_venv_package; then
        "${PYTHON_BIN}" -m venv --system-site-packages "${VENV_DIR}" || return 1
      else
        rm -rf "${VENV_DIR}"
        echo "Install python3.10-venv, then rerun: ENV_BACKEND=venv PYTHON_BIN=/usr/bin/python3.10 ./scripts/bootstrap.sh" >&2
        return 1
      fi
    }
  fi
  ENV_PYTHON="${VENV_DIR}/bin/python"
  if ! check_pip "${ENV_PYTHON}"; then
    echo "Python 3.10 venv exists but pip is unavailable: ${VENV_DIR}" >&2
    rm -rf "${VENV_DIR}"
    echo "Install python3.10-venv for venv mode, or use ENV_BACKEND=conda." >&2
    return 1
  fi
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
  if ! check_python "${ENV_PYTHON}"; then
    echo "Existing conda env is not Python 3.10; rebuilding ${CONDA_ENV_DIR}." >&2
    rm -rf "${CONDA_ENV_DIR}"
    "${CONDA_EXE}" create -y -p "${CONDA_ENV_DIR}" python=3.10 pip
  fi
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

"${ENV_PYTHON}" -m pip install --upgrade pip "setuptools>=68,<80" wheel || true
if ! "${ENV_PYTHON}" -m pip install -e "${ROOT_DIR}[dev,upload]"; then
  echo "Editable install failed, retrying without build isolation." >&2
  "${ENV_PYTHON}" -m pip install --no-build-isolation -e "${ROOT_DIR}[dev,upload]"
fi

cat > "${ROOT_DIR}/.robodataset_env" <<EOF
ENV_KIND=${ENV_KIND}
ENV_PYTHON=${ENV_PYTHON}
ENV_COMMAND=${ENV_COMMAND}
ROS_SETUP=${ROS_SETUP}
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
print("RoboDataset Studio bootstrap complete.")
PY

echo "Environment: ${ENV_KIND}"
echo "Python: ${ENV_PYTHON}"
echo "Command: ${ENV_COMMAND}"
echo "Launcher: ${ROOT_DIR}/RoboDataset-Studio-V3.sh"
