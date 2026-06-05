#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3.10}"
VENV_DIR="${VENV_DIR:-${ROOT_DIR}/.venv}"
ROS_SETUP="${ROS_SETUP:-/opt/ros/humble/setup.bash}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Python 3.10 is required for ROS2 Humble rclpy bindings: ${PYTHON_BIN}" >&2
  echo "Set PYTHON_BIN=/path/to/python3.10 if it is installed elsewhere." >&2
  exit 1
fi

PYTHON_VERSION="$("${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "${PYTHON_VERSION}" != "3.10" && "${ALLOW_NON_ROS_PYTHON:-0}" != "1" ]]; then
  echo "Python 3.10 is required for ROS2 Humble rclpy bindings; got ${PYTHON_VERSION} from ${PYTHON_BIN}." >&2
  echo "Set ALLOW_NON_ROS_PYTHON=1 only for UI/mock workflows without real ROS2 recording." >&2
  exit 1
fi

if [[ -f "${ROS_SETUP}" ]]; then
  set +u
  # shellcheck disable=SC1090
  source "${ROS_SETUP}"
  set -u
else
  echo "Warning: ROS setup not found: ${ROS_SETUP}" >&2
  echo "UI and mock workflows can run, but real ROS2 recording requires ROS2 Humble." >&2
fi

if [[ ! -d "${VENV_DIR}" ]]; then
  if ! "${PYTHON_BIN}" -m venv "${VENV_DIR}"; then
    echo "Failed to create virtual environment with ${PYTHON_BIN}." >&2
    echo "On Ubuntu 22.04 install: sudo apt install python3.10-venv" >&2
    exit 1
  fi
fi

"${VENV_DIR}/bin/python" -m pip install --upgrade pip setuptools wheel
"${VENV_DIR}/bin/python" -m pip install -e "${ROOT_DIR}[dev,upload]"

cat > "${ROOT_DIR}/RoboDataset-Studio.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROS_SETUP="${ROS_SETUP:-/opt/ros/humble/setup.bash}"

if [[ -f "${ROS_SETUP}" ]]; then
  set +u
  # shellcheck disable=SC1090
  source "${ROS_SETUP}"
  set -u
fi

export PYTHONPATH="${ROOT_DIR}/src:${PYTHONPATH:-}"
exec "${ROOT_DIR}/.venv/bin/robodataset-studio" "$@"
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

"${VENV_DIR}/bin/python" - <<'PY'
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

echo "Launcher: ${ROOT_DIR}/RoboDataset-Studio.sh"
echo "Desktop entry: ${ROOT_DIR}/RoboDataset-Studio.desktop"
