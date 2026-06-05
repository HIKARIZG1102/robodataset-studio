#!/usr/bin/env bash

qt_runtime_plugin_dirs() {
  local env_python="$1"
  "${env_python}" - <<'PY'
from pathlib import Path
import PySide6

root = Path(PySide6.__file__).resolve().parent / "Qt" / "plugins"
for rel in ("platforms", "xcbglintegrations"):
    path = root / rel
    if path.exists():
        print(path)
PY
}

qt_missing_libraries() {
  local env_python="$1"
  while IFS= read -r plugin_dir; do
    find "${plugin_dir}" -maxdepth 1 -type f -name "*.so" -print
  done < <(qt_runtime_plugin_dirs "${env_python}") |
    while IFS= read -r plugin; do
      ldd "${plugin}" 2>/dev/null | awk '/not found/{print $1}'
    done |
    sort -u
}

qt_ubuntu_packages_for_libraries() {
  local lib
  while IFS= read -r lib; do
    case "${lib}" in
      libxcb-cursor.so.0) echo "libxcb-cursor0" ;;
      libxcb-icccm.so.4) echo "libxcb-icccm4" ;;
      libxcb-image.so.0) echo "libxcb-image0" ;;
      libxcb-keysyms.so.1) echo "libxcb-keysyms1" ;;
      libxcb-randr.so.0) echo "libxcb-randr0" ;;
      libxcb-render-util.so.0) echo "libxcb-render-util0" ;;
      libxcb-util.so.1) echo "libxcb-util1" ;;
      libxcb-xkb.so.1) echo "libxcb-xkb1" ;;
      libxcb-xinerama.so.0) echo "libxcb-xinerama0" ;;
      libxkbcommon-x11.so.0) echo "libxkbcommon-x11-0" ;;
      libX11-xcb.so.1) echo "libx11-xcb1" ;;
      libGL.so.1) echo "libgl1" ;;
      libEGL.so.1) echo "libegl1" ;;
      libfontconfig.so.1) echo "libfontconfig1" ;;
      libfreetype.so.6) echo "libfreetype6" ;;
      libdbus-1.so.3) echo "libdbus-1-3" ;;
      libglib-2.0.so.0) echo "libglib2.0-0" ;;
      libwayland-client.so.0) echo "libwayland-client0" ;;
      libwayland-cursor.so.0) echo "libwayland-cursor0" ;;
      libwayland-egl.so.1) echo "libwayland-egl1" ;;
      *) echo "" ;;
    esac
  done | awk 'NF' | sort -u
}

qt_required_ubuntu_packages() {
  printf '%s\n' \
    libxcb-cursor0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-util1 \
    libxcb-xkb1 \
    libxkbcommon-x11-0 \
    libx11-xcb1 \
    libgl1 \
    libegl1 \
    libfontconfig1 \
    libfreetype6 \
    libdbus-1-3 \
    libglib2.0-0 \
    libwayland-client0 \
    libwayland-cursor0 \
    libwayland-egl1
}

qt_missing_ubuntu_packages() {
  local env_python="$1"
  qt_missing_libraries "${env_python}" | qt_ubuntu_packages_for_libraries
}

qt_print_desktop_dependency_help() {
  local env_python="$1"
  local missing_libs missing_packages
  missing_libs="$(qt_missing_libraries "${env_python}" | xargs || true)"
  missing_packages="$(qt_missing_ubuntu_packages "${env_python}" | xargs || true)"
  if [[ -z "${missing_libs}" ]]; then
    return 0
  fi
  echo "Missing Qt desktop runtime libraries: ${missing_libs}" >&2
  if [[ -n "${missing_packages}" ]]; then
    echo "Install missing Ubuntu packages with:" >&2
    echo "  sudo apt install ${missing_packages}" >&2
  else
    echo "Some missing libraries are not mapped to Ubuntu packages; inspect with ldd under PySide6/Qt/plugins." >&2
  fi
  return 1
}

qt_install_desktop_dependencies_if_requested() {
  local env_python="$1"
  local missing_packages
  missing_packages="$(qt_missing_ubuntu_packages "${env_python}" | xargs || true)"
  if [[ -z "${missing_packages}" ]]; then
    return 0
  fi
  if [[ "${INSTALL_SYSTEM_DEPS:-0}" == "1" ]] && command -v sudo >/dev/null 2>&1; then
    echo "Installing Qt desktop runtime packages: ${missing_packages}" >&2
    sudo apt-get update
    sudo apt-get install -y ${missing_packages}
    return 0
  fi
  qt_print_desktop_dependency_help "${env_python}"
}
