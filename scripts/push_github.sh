#!/usr/bin/env bash
set -euo pipefail

OWNER="${1:?owner required}"
REPO="${2:?repo required}"
GIT_DIR_PATH="${3:-.git_local}"
WORK_TREE_PATH="${4:-.}"

IFS= read -r TOKEN
if [[ -z "${TOKEN}" ]]; then
  echo "missing token on stdin" >&2
  exit 1
fi

api_response="$(
  curl -sS -o /tmp/robodataset_github_create_repo.json -w "%{http_code}" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    https://api.github.com/user/repos \
    -d "{\"name\":\"${REPO}\",\"private\":false,\"description\":\"PySide6 ROS2 robot dataset collection workbench\",\"auto_init\":false}"
)"

if [[ "${api_response}" != "201" && "${api_response}" != "422" ]]; then
  echo "GitHub repo create failed with HTTP ${api_response}" >&2
  cat /tmp/robodataset_github_create_repo.json >&2
  exit 1
fi

git --git-dir="${GIT_DIR_PATH}" --work-tree="${WORK_TREE_PATH}" \
  -c "http.https://github.com/.extraheader=Authorization: Bearer ${TOKEN}" \
  push "https://github.com/${OWNER}/${REPO}.git" main:main

