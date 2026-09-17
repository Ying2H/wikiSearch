#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "Python executable not found: ${PYTHON_BIN}" >&2
    exit 1
fi

if [[ ! -x "${ROOT_DIR}/.venv/bin/python" ]]; then
    "${PYTHON_BIN}" -m venv "${ROOT_DIR}/.venv"
fi

"${ROOT_DIR}/.venv/bin/python" -m pip install \
    --disable-pip-version-check \
    --no-input \
    -r "${ROOT_DIR}/requirements.txt"

if [[ -f "${ROOT_DIR}/package-lock.json" ]]; then
    if ! command -v npm >/dev/null 2>&1; then
        echo "Node.js/npm is required to install the Pagefind builder dependency." >&2
        exit 1
    fi
    (cd "${ROOT_DIR}" && npm ci)
fi

echo "Virtual environment ready: ${ROOT_DIR}/.venv/bin/python"
