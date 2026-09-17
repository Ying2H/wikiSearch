#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PYTHON_BIN="${PYTHON_BIN:-${ROOT_DIR}/.venv/bin/python}"
SITE_URL="${SITE_URL:-http://wymbot.wikidot.com}"
MANIFEST_PATH="${MANIFEST_PATH:-/pagelist}"
SCAN_PAGES="${SCAN_PAGES:-2}"
WORKER_LIMIT="${WORKER_LIMIT:-200}"
MIN_INTERVAL="${MIN_INTERVAL:-2}"
LISTPAGES_TTL="${LISTPAGES_TTL:-1800}"
TRANSITIVE_TTL="${TRANSITIVE_TTL:-1800}"
OTHER_DYNAMIC_TTL="${OTHER_DYNAMIC_TTL:-3600}"
UNKNOWN_TTL="${UNKNOWN_TTL:-3600}"
DB_PATH="${DB_PATH:-data/target.sqlite3}"
CACHE_DIR="${CACHE_DIR:-data/target-cache}"
SNAPSHOT_DIR="${SNAPSHOT_DIR:-data/build-input}"
PAGEFIND_DIR="${PAGEFIND_DIR:-data/publish/pagefind}"
SITE_DIR="${SITE_DIR:-data/publish/site}"
DRAIN_ROUNDS="${DRAIN_ROUNDS:-3}"
PUBLISH=0

usage() {
    echo "Usage: scripts/run_pipeline.sh [--publish]"
}

while (($# > 0)); do
    case "$1" in
        --publish) PUBLISH=1 ;;
        --no-publish) PUBLISH=0 ;;
        --help|-h) usage; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

if [[ "${PYTHON_BIN}" == */* ]]; then
    [[ -x "${PYTHON_BIN}" ]] || { echo "Python executable not found: ${PYTHON_BIN}" >&2; exit 1; }
elif ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "Python executable not found: ${PYTHON_BIN}" >&2
    exit 1
fi

command -v npm >/dev/null 2>&1 || { echo "npm is required for Pagefind builds" >&2; exit 1; }
command -v flock >/dev/null 2>&1 || { echo "flock is required to serialize pipeline runs" >&2; exit 1; }

mkdir -p "$(dirname "${DB_PATH}")" "${CACHE_DIR}" "${SNAPSHOT_DIR}" "$(dirname "${PAGEFIND_DIR}")" "$(dirname "${SITE_DIR}")"
exec 9>"${ROOT_DIR}/data/pipeline.lock"
if ! flock -n 9; then
    echo "Another pipeline run is active; exiting without overlap."
    exit 0
fi

SYNC_ARGS=(
    --base-url "${SITE_URL}"
    --manifest-path "${MANIFEST_PATH}"
    --db "${DB_PATH}"
    --cache-dir "${CACHE_DIR}"
    --worker-limit "${WORKER_LIMIT}"
    --listpages-ttl "${LISTPAGES_TTL}"
    --transitive-ttl "${TRANSITIVE_TTL}"
    --other-dynamic-ttl "${OTHER_DYNAMIC_TTL}"
    --unknown-ttl "${UNKNOWN_TTL}"
    --min-interval "${MIN_INTERVAL}"
    --progress
)

"${PYTHON_BIN}" scripts/sync_once.py \
    --base-url "${SITE_URL}" \
    --manifest-path "${MANIFEST_PATH}" \
    --db "${DB_PATH}" \
    --cache-dir "${CACHE_DIR}" \
    --scan-pages "${SCAN_PAGES}" \
    --worker-limit "${WORKER_LIMIT}" \
    --listpages-ttl "${LISTPAGES_TTL}" \
    --transitive-ttl "${TRANSITIVE_TTL}" \
    --other-dynamic-ttl "${OTHER_DYNAMIC_TTL}" \
    --unknown-ttl "${UNKNOWN_TTL}" \
    --min-interval "${MIN_INTERVAL}" \
    --progress

SNAPSHOT_READY=0
for ((round = 1; round <= DRAIN_ROUNDS; round += 1)); do
    if "${PYTHON_BIN}" scripts/sync_once.py "${SYNC_ARGS[@]}" \
        --skip-scan \
        --snapshot-dir "${SNAPSHOT_DIR}"; then
        SNAPSHOT_READY=1
        break
    fi
    echo "Snapshot attempt ${round}/${DRAIN_ROUNDS} found follow-up jobs; draining dependencies."
done

if [[ "${SNAPSHOT_READY}" != "1" ]]; then
    echo "Unable to produce a consistent snapshot after ${DRAIN_ROUNDS} rounds." >&2
    exit 2
fi

NEW_MANIFEST_HASH="$(${PYTHON_BIN} -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["manifest_hash"])' "${SNAPSHOT_DIR}/manifest.json")"
NEW_ENTRYPOINT_HASH="$(${PYTHON_BIN} -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "web/index.html")"
if [[ -f "${SITE_DIR}/build.json" ]]; then
    OLD_SIGNATURE="$(${PYTHON_BIN} -c 'import json,sys; p=json.load(open(sys.argv[1], encoding="utf-8")); print(str(p.get("manifest_hash", "")) + ":" + str(p.get("entrypoint_hash", "")))' "${SITE_DIR}/build.json")"
    if [[ "${OLD_SIGNATURE}" == "${NEW_MANIFEST_HASH}:${NEW_ENTRYPOINT_HASH}" ]]; then
        echo "Corpus and entrypoint are unchanged; skip Pagefind rebuild and GitHub Pages push."
        exit 0
    fi
fi

npm run build:index -- --records "${SNAPSHOT_DIR}" --output "${PAGEFIND_DIR}"

"${PYTHON_BIN}" scripts/assemble_site.py \
    --pagefind-dir "${PAGEFIND_DIR}" \
    --manifest "${SNAPSHOT_DIR}/manifest.json" \
    --output-dir "${SITE_DIR}"

if [[ "${PUBLISH}" == "1" ]]; then
    scripts/publish_github_pages.sh "${SITE_DIR}"
fi
