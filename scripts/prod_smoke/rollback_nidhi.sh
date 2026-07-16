#!/usr/bin/env bash
#
# rollback_nidhi.sh — Roll Nidhi back to the last-known-good backend image.
#
# INTENDED TO RUN ON THE PROD VPS (72.60.218.127). Pins the compose image line
# to :lastgood (a local tag that does NOT exist in the registry) and recreates
# the service, which also stops Watchtower (it only advances :latest) from
# immediately re-deploying the broken build.
#
# Usage:
#   rollback_nidhi.sh            # roll back to :lastgood
#   rollback_nidhi.sh 1          # roll back one FURTHER (:lastgood-1)
#   ROLLBACK_DEPTH=2 rollback_nidhi.sh
#
set -uo pipefail

ROLLBACK_DEPTH="${1:-${ROLLBACK_DEPTH:-0}}"
COMPOSE_FILE="${NIDHI_COMPOSE_FILE:-/services/nidhi-platform/docker-compose.yml}"
STATE_DIR="${NIDHI_STATE_DIR:-/var/lib/nidhi-deploy}"
LASTGOOD_BACKEND="${STATE_DIR}/lastgood_backend"
REGISTRY="${NIDHI_REGISTRY:-aadisheshu}"
BACKEND_IMAGE="${REGISTRY}/nidhi_backend"
BACKEND_SVC="${NIDHI_BACKEND_SVC:-nidhi-backend}"
LASTGOOD_TAG="${NIDHI_LASTGOOD_TAG:-lastgood}"
NIRIKSHAN_URL="${NIRIKSHAN_URL:-http://localhost:8000}"

if [[ "${ROLLBACK_DEPTH}" =~ ^[0-9]+$ ]] && (( ROLLBACK_DEPTH > 0 )); then
  ROLLBACK_TAG="${LASTGOOD_TAG}-${ROLLBACK_DEPTH}"
else
  ROLLBACK_TAG="${LASTGOOD_TAG}"
fi

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  COMPOSE_BIN="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_BIN="docker-compose"
else
  echo "ERROR: docker compose is not available on this host." >&2; exit 3
fi

log() { echo "[rollback_nidhi] $(date '+%Y-%m-%d %H:%M:%S') $*"; }

notify_rollback() {
  local platform_key="$1" reason="$2" rolled_back_to="$3" recovered="$4"
  [[ -z "${NIRIKSHAN_URL}" ]] && return 0
  command -v curl >/dev/null 2>&1 || return 0
  local payload
  payload=$(printf '{"platform":"%s","event":"rollback","reason":"%s","rolled_back_to":"%s","recovered":"%s","host":"%s","ts":"%s"}' \
    "${platform_key}" "${reason}" "${rolled_back_to}" "${recovered}" \
    "$(hostname)" "$(date '+%Y-%m-%dT%H:%M:%S%z')")
  curl -s -o /dev/null -X POST "${NIRIKSHAN_URL}/api/events/rollback" \
       --connect-timeout 3 --max-time 5 -H 'Content-Type: application/json' \
       -d "${payload}" 2>/dev/null || true
}

[[ ! -f "${COMPOSE_FILE}" ]] && { echo "ERROR: compose file not found: ${COMPOSE_FILE}" >&2; exit 2; }
if ! docker image inspect "${BACKEND_IMAGE}:${ROLLBACK_TAG}" >/dev/null 2>&1; then
  echo "ERROR: ${BACKEND_IMAGE}:${ROLLBACK_TAG} not found locally. Run record_lastgood_nidhi.sh first." >&2
  exit 1
fi

log "Backend last-good: $(cat "${LASTGOOD_BACKEND}" 2>/dev/null || echo '?')"
cp -a "${COMPOSE_FILE}" "${COMPOSE_FILE}.bak.$(date +%s)" 2>/dev/null || true

log "Pinning compose image line to :${ROLLBACK_TAG}"
sed -i -E "s#(image: ${BACKEND_IMAGE}):[A-Za-z0-9._-]+#\1:${ROLLBACK_TAG}#" "${COMPOSE_FILE}"
grep -E "image: ${BACKEND_IMAGE}" "${COMPOSE_FILE}" || true

log "Recreating ${BACKEND_SVC} via compose"
if ${COMPOSE_BIN} -f "${COMPOSE_FILE}" up -d "${BACKEND_SVC}"; then
  log "Rollback complete. Service recreated from :${ROLLBACK_TAG}."
  log "NOTE: compose pinned to :${ROLLBACK_TAG}; Watchtower will NOT auto-deploy until you repoint to :latest."
  notify_rollback "nidhi" "smoke_fail" "${ROLLBACK_TAG}" "unknown"
  exit 0
else
  echo "ERROR: docker compose up failed — manual intervention required." >&2
  exit 4
fi
