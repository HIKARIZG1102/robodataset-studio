#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_NAME="${IMAGE_NAME:-robodataset-studio}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

docker build -t "${IMAGE_NAME}:${IMAGE_TAG}" "${ROOT_DIR}"
