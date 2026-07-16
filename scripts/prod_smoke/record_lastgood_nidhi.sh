#!/usr/bin/env bash
#
# record_lastgood_nidhi.sh — Mark the CURRENTLY-running Nidhi backend image as
# "last known good" by pointing a stable local docker tag (:lastgood) at its
# image ID. Call ONLY after a smoke test has PASSED.
#
# INTENDED TO RUN ON THE PROD VPS (72.60.218.127). Nidhi images are pulled as
# :latest with empty RepoDigests, so we use a local :lastgood tag (see
# New-Nova's record_lastgood.sh for the full rationale). A tag PROTECTS the
# image ID from `docker image prune` / Watchtower cleanup.
#
set -uo pipefail

STATE_DIR="${NIDHI_STATE_DIR:-/var/lib/nidhi-deploy}"
REGISTRY="${NIDHI_REGISTRY:-aadisheshu}"
BACKEND_IMAGE="${REGISTRY}/nidhi_backend"
BACKEND_CONTAINER="${NIDHI_BACKEND_CONTAINER:-nidhi-backend}"
LASTGOOD_TAG="${NIDHI_LASTGOOD_TAG:-lastgood}"
HISTORY_DEPTH="${NIDHI_HISTORY_DEPTH:-3}"

log() { echo "[record_lastgood_nidhi] $(date '+%Y-%m-%d %H:%M:%S') $*"; }

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker not available — this script must run where the container lives." >&2
  exit 3
fi

tag_image_id() { docker image inspect -f '{{.Id}}' "$1" 2>/dev/null || true; }

record_one() {
  local container="$1" repo="$2" statefile="$3"
  local img_id
  img_id="$(docker inspect -f '{{.Image}}' "${container}" 2>/dev/null)" || {
    echo "ERROR: container ${container} not found / not running." >&2; return 1; }
  [[ -z "${img_id}" ]] && { echo "ERROR: could not read image ID for ${container}." >&2; return 1; }

  local current_lastgood
  current_lastgood="$(tag_image_id "${repo}:${LASTGOOD_TAG}")"
  if [[ -n "${current_lastgood}" && "${current_lastgood}" != "${img_id}" ]]; then
    local i
    for (( i=HISTORY_DEPTH-1; i>=1; i-- )); do
      src="${repo}:${LASTGOOD_TAG}-$((i-1))"; dst="${repo}:${LASTGOOD_TAG}-${i}"
      [[ $((i-1)) -eq 0 ]] && src="${repo}:${LASTGOOD_TAG}"
      [[ -n "$(tag_image_id "${src}")" ]] && docker tag "${src}" "${dst}" 2>/dev/null || true
    done
    log "Rotated ${repo} history (previous good = ${current_lastgood} -> ${LASTGOOD_TAG}-1)"
  fi

  docker tag "${img_id}" "${repo}:${LASTGOOD_TAG}" || {
    echo "ERROR: failed to tag ${img_id} as ${repo}:${LASTGOOD_TAG}" >&2; return 1; }
  printf '%s  recorded=%s\n' "${img_id}" "$(date '+%Y-%m-%d %H:%M:%S')" > "${statefile}"
  log "Recorded ${container} -> ${repo}:${LASTGOOD_TAG} (${img_id})"
}

mkdir -p "${STATE_DIR}"
rc=0
record_one "${BACKEND_CONTAINER}" "${BACKEND_IMAGE}" "${STATE_DIR}/lastgood_backend" || rc=1
if (( rc == 0 )); then
  log "Last-good recorded. Rollback target = ${BACKEND_IMAGE}:${LASTGOOD_TAG}"
fi
exit "${rc}"
