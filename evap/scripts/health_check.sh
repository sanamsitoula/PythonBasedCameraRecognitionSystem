#!/bin/bash
# ==============================================================================
# EVAP System Health Check Script
# Usage: ./health_check.sh [--json] [--quiet]
# Exit codes:
#   0 = All systems healthy
#   1 = Degraded (some services have warnings)
#   2 = Critical (one or more essential services are down)
# ==============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load environment
if [[ -f "${SCRIPT_DIR}/../.env" ]]; then
  set -a; source "${SCRIPT_DIR}/../.env"; set +a
fi

# ── Config ─────────────────────────────────────────────────────────────────────
BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
PGHOST="${PGHOST:-${POSTGRES_HOST:-localhost}}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-${POSTGRES_USER:-evap}}"
PGPASSWORD="${PGPASSWORD:-${POSTGRES_PASSWORD:-}}"
PGDATABASE="${PGDATABASE:-${POSTGRES_DB:-evap}}"
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_PASSWORD="${REDIS_PASSWORD:-}"
RABBITMQ_HOST="${RABBITMQ_HOST:-localhost}"
RABBITMQ_PORT="${RABBITMQ_PORT:-15672}"
RABBITMQ_USER="${RABBITMQ_USER:-evap}"
RABBITMQ_PASSWORD="${RABBITMQ_PASSWORD:-}"
export PGPASSWORD

OUTPUT_JSON=false
QUIET=false
for arg in "$@"; do
  case "$arg" in
    --json)   OUTPUT_JSON=true ;;
    --quiet)  QUIET=true ;;
  esac
done

# ── State tracking ─────────────────────────────────────────────────────────────
declare -A STATUS        # service -> healthy|degraded|critical
declare -A MESSAGES      # service -> message
OVERALL=0                # 0=healthy 1=degraded 2=critical

set_status() {
  local svc="$1" st="$2" msg="$3"
  STATUS[$svc]="$st"
  MESSAGES[$svc]="$msg"
  if [[ "$st" == "critical" && $OVERALL -lt 2 ]]; then OVERALL=2
  elif [[ "$st" == "degraded" && $OVERALL -lt 1 ]]; then OVERALL=1
  fi
}

# ── Check: Backend API ─────────────────────────────────────────────────────────
check_backend() {
  local resp
  resp=$(curl -sf --max-time 5 "${BACKEND_URL}/health" 2>/dev/null || echo "")
  if [[ -z "$resp" ]]; then
    set_status backend critical "No response from ${BACKEND_URL}/health"
    return
  fi
  local status_field
  status_field=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','unknown'))" 2>/dev/null || echo "unknown")
  if [[ "$status_field" == "healthy" || "$status_field" == "ok" ]]; then
    set_status backend healthy "HTTP 200, status=${status_field}"
  else
    set_status backend degraded "HTTP 200 but status=${status_field}: ${resp}"
  fi
}

# ── Check: PostgreSQL ──────────────────────────────────────────────────────────
check_postgres() {
  if ! command -v pg_isready &>/dev/null; then
    set_status postgres degraded "pg_isready not installed; skipping deep check"
    return
  fi
  if pg_isready -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" -q; then
    local conn_count
    conn_count=$(PGPASSWORD="${PGPASSWORD}" psql -h "${PGHOST}" -p "${PGPORT}" \
      -U "${PGUSER}" -d "${PGDATABASE}" -t \
      -c "SELECT count(*) FROM pg_stat_activity WHERE datname='${PGDATABASE}';" \
      2>/dev/null | tr -d ' \n' || echo "?")
    set_status postgres healthy "Accepting connections. Active connections: ${conn_count}"
  else
    set_status postgres critical "pg_isready returned non-zero: ${PGHOST}:${PGPORT}"
  fi
}

# ── Check: Redis ───────────────────────────────────────────────────────────────
check_redis() {
  if ! command -v redis-cli &>/dev/null; then
    set_status redis degraded "redis-cli not installed; skipping check"
    return
  fi
  local auth_args=()
  [[ -n "${REDIS_PASSWORD}" ]] && auth_args=(-a "${REDIS_PASSWORD}")
  local pong
  pong=$(redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" "${auth_args[@]}" PING 2>/dev/null || echo "")
  if [[ "$pong" == "PONG" ]]; then
    local mem
    mem=$(redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" "${auth_args[@]}" \
      INFO memory 2>/dev/null | grep used_memory_human | cut -d: -f2 | tr -d '\r' || echo "?")
    set_status redis healthy "PONG received. Memory used: ${mem}"
  else
    set_status redis critical "No PONG from ${REDIS_HOST}:${REDIS_PORT}"
  fi
}

# ── Check: RabbitMQ ────────────────────────────────────────────────────────────
check_rabbitmq() {
  local resp
  resp=$(curl -sf --max-time 5 \
    -u "${RABBITMQ_USER}:${RABBITMQ_PASSWORD}" \
    "http://${RABBITMQ_HOST}:${RABBITMQ_PORT}/api/healthchecks/node" 2>/dev/null || echo "")
  if [[ -z "$resp" ]]; then
    set_status rabbitmq critical "No response from RabbitMQ management API at ${RABBITMQ_HOST}:${RABBITMQ_PORT}"
    return
  fi
  local st
  st=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','unknown'))" 2>/dev/null || echo "unknown")
  if [[ "$st" == "ok" ]]; then
    set_status rabbitmq healthy "Management API: status=ok"
  else
    set_status rabbitmq degraded "Management API returned status=${st}"
  fi
}

# ── Check: Celery Workers ─────────────────────────────────────────────────────
check_celery() {
  local resp
  resp=$(curl -sf --max-time 5 "${BACKEND_URL}/api/v1/system/celery-status" 2>/dev/null || echo "")
  if [[ -z "$resp" ]]; then
    set_status celery degraded "Could not reach celery status endpoint"
    return
  fi
  local worker_count
  worker_count=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('online_workers', 0))" 2>/dev/null || echo "0")
  if [[ "$worker_count" -ge 1 ]]; then
    set_status celery healthy "${worker_count} worker(s) online"
  else
    set_status celery critical "0 Celery workers online"
  fi
}

# ── Check: Camera Streams ──────────────────────────────────────────────────────
check_cameras() {
  local resp
  resp=$(curl -sf --max-time 10 "${BACKEND_URL}/api/v1/cameras/status-summary" 2>/dev/null || echo "")
  if [[ -z "$resp" ]]; then
    set_status cameras degraded "Could not reach camera status endpoint"
    return
  fi
  local total online offline
  total=$(echo "$resp"   | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('total',0))"   2>/dev/null || echo "?")
  online=$(echo "$resp"  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('online',0))"  2>/dev/null || echo "?")
  offline=$(echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('offline',0))" 2>/dev/null || echo "?")
  if [[ "$offline" == "0" ]]; then
    set_status cameras healthy "All ${total} cameras online"
  elif [[ "$online" == "0" ]]; then
    set_status cameras critical "All cameras offline (total: ${total})"
  else
    set_status cameras degraded "${offline}/${total} cameras offline"
  fi
}

# ── Run all checks ─────────────────────────────────────────────────────────────
check_backend
check_postgres
check_redis
check_rabbitmq
check_celery
check_cameras

# ── Output ─────────────────────────────────────────────────────────────────────
OVERALL_LABEL="healthy"
[[ $OVERALL -eq 1 ]] && OVERALL_LABEL="degraded"
[[ $OVERALL -eq 2 ]] && OVERALL_LABEL="critical"

if $OUTPUT_JSON; then
  python3 - <<PYEOF
import json, sys
checks = {
$(for svc in "${!STATUS[@]}"; do
    echo "  \"${svc}\": {\"status\": \"${STATUS[$svc]}\", \"message\": \"${MESSAGES[$svc]}\"},"
  done)
}
result = {
    "overall": "${OVERALL_LABEL}",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "hostname": "$(hostname)",
    "checks": checks
}
print(json.dumps(result, indent=2))
PYEOF
else
  if ! $QUIET; then
    echo "============================================================"
    echo " EVAP Health Check — $(date '+%Y-%m-%d %H:%M:%S %Z')"
    echo "============================================================"
    for svc in backend postgres redis rabbitmq celery cameras; do
      printf " %-12s  [%-8s]  %s\n" "${svc}" "${STATUS[$svc]:-unknown}" "${MESSAGES[$svc]:-}"
    done
    echo "------------------------------------------------------------"
    printf " OVERALL: %s\n" "${OVERALL_LABEL^^}"
    echo "============================================================"
  fi
fi

exit $OVERALL
