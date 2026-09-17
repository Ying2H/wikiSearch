#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="/etc/systemd/system"

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run this installer as root." >&2
    exit 1
fi

[[ "${ROOT_DIR}" == "/root/code/wymboTSearch" ]] || {
    echo "This deployment template expects /root/code/wymboTSearch; found ${ROOT_DIR}" >&2
    exit 1
}

install -m 0644 "${ROOT_DIR}/deploy/systemd/wymbot-search-sync.service" "${UNIT_DIR}/wymbot-search-sync.service"
install -m 0644 "${ROOT_DIR}/deploy/systemd/wymbot-search-sync.timer" "${UNIT_DIR}/wymbot-search-sync.timer"
systemctl daemon-reload
systemctl enable --now wymbot-search-sync.timer
systemctl status --no-pager wymbot-search-sync.timer
