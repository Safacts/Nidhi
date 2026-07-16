#!/usr/bin/env bash
#
# postdeploy_check_nidhi.sh — Nidhi deploy orchestrator with auto-rollback +
# alerting. Runs AFTER a new image is pushed (Watchtower pulls + recreates).
#
#   1. WAITS for the fresh deploy to settle (landing page / reachable).
#   2. Runs smoke_nidhi.py against the URL.
#   3. SUCCESS -> records running image as last-good (if docker available).
#   4. FAILURE -> confirms across CONFIRM_TRIES attempts (avoid blip rollback),
#      then rolls back to :lastgood and re-smokes; sends ALERT email.
#
# Best on the PROD VPS. Works smoke-only on any host (no docker -> no rollback).
#
set -uo pipefail

BASE_URL="${NIDHI_BASE_URL:-https://rubix.tail2d2f35.ts.net/nidhi}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SMOKE_PY="${SMOKE_PY:-${SCRIPT_DIR}/smoke_nidhi.py}"
RECORD_SH="${RECORD_SH:-${SCRIPT_DIR}/record_lastgood_nidhi.sh}"
ROLLBACK_SH="${ROLLBACK_SH:-${SCRIPT_DIR}/rollback_nidhi.sh}"

ALERT_HELPER="${ALERT_HELPER:-/home/rubix/workspace/_AI_AGENTS/send_report.py}"
ALERT_EMAILS="${ALERT_EMAILS:-kongaaadisheshu@gmail.com gametest.transform@gmail.com}"
JIRA_ALERT="${JIRA_ALERT:-0}"
JIRA_SYNC_PY="${JIRA_SYNC_PY:-/home/rubix/workspace/_AI_AGENTS/sync_to_jira.py}"
NIRIKSHAN_URL="${NIRIKSHAN_URL:-http://localhost:8000}"

SETTLE_MAX_TRIES="${SETTLE_MAX_TRIES:-30}"
SETTLE_INTERVAL="${SETTLE_INTERVAL:-10}"
SMOKE_TIMEOUT="${SMOKE_TIMEOUT:-15}"
CONFIRM_TRIES="${CONFIRM_TRIES:-3}"
CONFIRM_INTERVAL="${CONFIRM_INTERVAL:-15}"

log() { echo "[postdeploy_check_nidhi] $(date '+%Y-%m-%d %H:%M:%S') $*"; }

docker_available() { command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; }

notify_rollback() {
  local platform_key="$1" reason="$2" rolled_back_to="$3" recovered="$4"
  [[ -z "${NIRIKSHAN_URL}" ]] && return 0
  command -v curl >/dev/null 2>&1 || return 0
  local payload
  payload=$(printf '{"platform":"%s","event":"rollback","reason":"%s","rolled_back_to":"%s","recovered":"%s","host":"%s","ts":"%s"}' \
    "${platform_key}" "${reason}" "${rolled_back_to}" "${recovered}" "$(hostname)" "$(date '+%Y-%m-%dT%H:%M:%S%z')")
  curl -s -o /dev/null -X POST "${NIRIKSHAN_URL}/api/events/rollback" \
       --connect-timeout 3 --max-time 5 -H 'Content-Type: application/json' -d "${payload}" 2>/dev/null || true
}

send_alert() {
  local subject="$1" body="$2"
  local tmp; tmp="$(mktemp /tmp/nidhi_alert.XXXXXX.txt)"
  { echo "# Deploy Alert — Nidhi"; echo; echo "** ${subject} **"; echo; echo "${body}";
    echo; echo "Generated: $(date '+%Y-%m-%d %H:%M:%S')"; echo "Host: $(hostname)"; } > "${tmp}"
  if [[ -x "${ALERT_HELPER}" || ( -f "${ALERT_HELPER}" && -x "$(command -v python3)" ) ]]; then
    log "Sending alert email via ${ALERT_HELPER}"
    python3 "${ALERT_HELPER}" "${tmp}" ${ALERT_EMAILS} || echo "WARN: alert helper exited non-zero" >&2
  else
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" >&2
    echo "ALERT (helper ${ALERT_HELPER} not available):" >&2
    echo "Subject: ${subject}"; echo "${body}" >&2
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" >&2
  fi
  [[ "${JIRA_ALERT}" == "1" && -f "${JIRA_SYNC_PY}" ]] && python3 "${JIRA_SYNC_PY}" --review >/dev/null 2>&1 || true
  rm -f "${tmp}"
}

wait_for_settle() {
  local tries=0
  log "Waiting for deploy to settle (polling ${BASE_URL}/)..."
  while (( tries < SETTLE_MAX_TRIES )); do
    if python3 - <<PY 2>/dev/null
import sys, urllib.request
try:
    urllib.request.urlopen("${BASE_URL}/", timeout=${SMOKE_TIMEOUT}); sys.exit(0)
except Exception:
    sys.exit(1)
PY
    then log "Backend/frontend reachable — deploy settled."; return 0; fi
    tries=$((tries+1))
    log "  attempt ${tries}/${SETTLE_MAX_TRIES}: not ready yet, sleeping ${SETTLE_INTERVAL}s"
    sleep "${SETTLE_INTERVAL}"
  done
  log "TIMEOUT waiting for deploy to settle."
  return 1
}

[[ ! -f "${SMOKE_PY}" ]] && { echo "ERROR: smoke_nidhi.py not found at ${SMOKE_PY}" >&2; exit 2; }

CAN_ROLLBACK=0
if docker_available; then CAN_ROLLBACK=1; log "docker available — will record last-good and can auto-rollback."
else log "docker NOT available — smoke-only mode (no record/rollback)."; fi

if ! wait_for_settle; then
  send_alert "Nidhi deploy did NOT settle" \
    "The stack at ${BASE_URL} did not become reachable within $((SETTLE_MAX_TRIES*SETTLE_INTERVAL))s after a deploy."
  exit 1
fi

log "Running smoke test..."
if python3 "${SMOKE_PY}" --url "${BASE_URL}" --timeout "${SMOKE_TIMEOUT}"; then
  log "SMOKE PASS — Nidhi is healthy."
  if (( CAN_ROLLBACK )); then
    [[ -x "${RECORD_SH}" ]] && { "${RECORD_SH}" && log "Recorded current image as last-good." || log "WARN: record failed (non-fatal)."; } \
      || log "WARN: ${RECORD_SH} not executable — skipping."
  else log "NOTE: docker unavailable here; last-good NOT recorded."; fi
  notify_rollback "nidhi" "deploy_ok" "none" "true"
  exit 0
else
  confirmed_fail=1
  for attempt in $(seq 1 "${CONFIRM_TRIES}"); do
    log "Smoke failed — confirmation attempt ${attempt}/${CONFIRM_TRIES} (sleep ${CONFIRM_INTERVAL}s)..."
    sleep "${CONFIRM_INTERVAL}"
    if python3 "${SMOKE_PY}" --url "${BASE_URL}" --timeout "${SMOKE_TIMEOUT}" >/dev/null 2>&1; then
      log "Recovered on confirmation attempt ${attempt} — transient blip, NOT rolling back."; confirmed_fail=0; break
    fi
  done
  (( confirmed_fail == 0 )) && exit 0

  SUMMARY="$(python3 "${SMOKE_PY}" --url "${BASE_URL}" --timeout "${SMOKE_TIMEOUT}" --quiet 2>&1)"
  log "SMOKE FAIL CONFIRMED across ${CONFIRM_TRIES} attempts."; echo "${SUMMARY}" >&2

  if (( CAN_ROLLBACK )); then
    log "Invoking rollback_nidhi.sh..."
    if "${ROLLBACK_SH}"; then
      log "Rollback applied. Re-running smoke to confirm recovery..."
      if python3 "${SMOKE_PY}" --url "${BASE_URL}" --timeout "${SMOKE_TIMEOUT}"; then
        notify_rollback "nidhi" "smoke_fail" "lastgood" "true"
        send_alert "Nidhi AUTO-ROLLED BACK (recovered)" \
"Smoke test FAILED on the new Nidhi deploy at ${BASE_URL}.
Action: rolled back to last-good image and re-ran smoke — it now PASSES.

Failed checks:
${SUMMARY}"
        exit 1
      else
        notify_rollback "nidhi" "smoke_fail" "lastgood" "false"
        send_alert "Nidhi ROLLBACK FAILED (still broken)" \
"Smoke FAILED at ${BASE_URL}, AND rollback did NOT recover it. Manual intervention required.

Failed checks (post-rollback):
$(python3 "${SMOKE_PY}" --url "${BASE_URL}" --timeout "${SMOKE_TIMEOUT}" --quiet 2>&1)"
        exit 1
      fi
    else
      send_alert "Nidhi ROLLBACK SCRIPT FAILED" \
"Smoke FAILED at ${BASE_URL}, but rollback_nidhi.sh exited non-zero. Manual rollback required.

Failed checks:
${SUMMARY}"
      exit 1
    fi
  else
    send_alert "Nidhi deploy FAILED (no auto-rollback from this host)" \
"Smoke FAILED at ${BASE_URL}. This orchestrator has no docker access, so it could NOT auto-rollback.
Run rollback_nidhi.sh on the VPS (72.60.218.127) to revert to last-good.

Failed checks:
${SUMMARY}"
    exit 1
  fi
fi
