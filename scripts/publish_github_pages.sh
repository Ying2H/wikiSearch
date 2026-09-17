#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SITE_DIR="${1:-${ROOT_DIR}/data/publish/site}"
REMOTE_NAME="${GITHUB_REMOTE:-origin}"
PAGES_DIR="${PAGES_DIR:-${ROOT_DIR}/data/github-pages}"
GIT_NAME="${GIT_NAME:-work}"
GIT_EMAIL="${GIT_EMAIL:-work@local}"

[[ -f "${SITE_DIR}/index.html" ]] || { echo "Static site entrypoint not found: ${SITE_DIR}/index.html" >&2; exit 1; }

case "${PAGES_DIR}" in
    "${ROOT_DIR}/data/"*) ;;
    *) echo "PAGES_DIR must remain below ${ROOT_DIR}/data" >&2; exit 1 ;;
esac

REMOTE_URL="$(git -C "${ROOT_DIR}" remote get-url "${REMOTE_NAME}")"
mkdir -p "${PAGES_DIR}"

if [[ ! -d "${PAGES_DIR}/.git" ]]; then
    git init --initial-branch=gh-pages "${PAGES_DIR}"
    git -C "${PAGES_DIR}" remote add "${REMOTE_NAME}" "${REMOTE_URL}"
else
    git -C "${PAGES_DIR}" remote set-url "${REMOTE_NAME}" "${REMOTE_URL}" 2>/dev/null || \
        git -C "${PAGES_DIR}" remote add "${REMOTE_NAME}" "${REMOTE_URL}"
fi

if git ls-remote --exit-code --heads "${REMOTE_URL}" gh-pages >/dev/null 2>&1; then
    git -C "${PAGES_DIR}" fetch --depth=1 "${REMOTE_NAME}" gh-pages
    git -C "${PAGES_DIR}" checkout -B gh-pages "${REMOTE_NAME}/gh-pages"
else
    if git -C "${PAGES_DIR}" show-ref --verify --quiet refs/heads/gh-pages; then
        git -C "${PAGES_DIR}" checkout gh-pages
    else
        git -C "${PAGES_DIR}" checkout --orphan gh-pages
    fi
    git -C "${PAGES_DIR}" rm -rf . >/dev/null 2>&1 || true
    git -C "${PAGES_DIR}" clean -fdx >/dev/null 2>&1 || true
fi

cp -a "${SITE_DIR}"/. "${PAGES_DIR}"/
git -C "${PAGES_DIR}" config user.name "${GIT_NAME}"
git -C "${PAGES_DIR}" config user.email "${GIT_EMAIL}"
git -C "${PAGES_DIR}" add --all

if git -C "${PAGES_DIR}" diff --cached --quiet; then
    echo "GitHub Pages output is unchanged; no push needed."
    exit 0
fi

git -C "${PAGES_DIR}" commit -m "deploy: update search index"
git -C "${PAGES_DIR}" push "${REMOTE_NAME}" gh-pages
