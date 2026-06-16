#!/bin/bash
# ==============================================================================
# EVAP Database Restore Script
# Usage: ./restore.sh <BACKUP_FILE> [--yes]
#   BACKUP_FILE: path to a .sql.gz backup file created by backup.sh
#   --yes: skip confirmation prompt (for automated use)
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_PREFIX="[EVAP RESTORE][$(date '+%Y-%m-%d %H:%M:%S')]"

log()   { echo "${LOG_PREFIX} $*"; }
error() { echo "${LOG_PREFIX} [ERROR] $*" >&2; }

# ── Arguments ──────────────────────────────────────────────────────────────────
BACKUP_FILE="${1:-}"
SKIP_CONFIRM="${2:-}"

if [[ -z "${BACKUP_FILE}" ]]; then
  error "Usage: $0 <BACKUP_FILE> [--yes]"
  error "Example: $0 /var/backups/evap/evap_backup_20260615_020000.sql.gz"
  exit 1
fi

# ── Load environment ───────────────────────────────────────────────────────────
if [[ -z "${DATABASE_URL:-}" && -f "${SCRIPT_DIR}/../.env" ]]; then
  set -a; source "${SCRIPT_DIR}/../.env"; set +a
fi

PGHOST="${PGHOST:-${POSTGRES_HOST:-localhost}}"
PGPORT="${PGPORT:-${POSTGRES_PORT:-5432}}"
PGUSER="${PGUSER:-${POSTGRES_USER:-evap}}"
PGPASSWORD="${PGPASSWORD:-${POSTGRES_PASSWORD:-}}"
PGDATABASE="${PGDATABASE:-${POSTGRES_DB:-evap}}"
PGADMINUSER="${PGADMINUSER:-postgres}"   # Superuser for drop/create operations
export PGPASSWORD

# ── Verify backup file ─────────────────────────────────────────────────────────
if [[ ! -f "${BACKUP_FILE}" ]]; then
  error "Backup file not found: ${BACKUP_FILE}"
  exit 1
fi

log "Verifying backup file integrity: ${BACKUP_FILE}"
if ! gzip -t "${BACKUP_FILE}"; then
  error "Backup file is corrupt (failed gzip integrity check): ${BACKUP_FILE}"
  exit 2
fi
BACKUP_SIZE=$(du -sh "${BACKUP_FILE}" | cut -f1)
log "Backup file OK. Size: ${BACKUP_SIZE}"

# ── Confirmation ───────────────────────────────────────────────────────────────
if [[ "${SKIP_CONFIRM}" != "--yes" ]]; then
  echo ""
  echo "  !!  WARNING: THIS WILL DESTROY ALL DATA IN DATABASE '${PGDATABASE}'  !!"
  echo "  !!  on host ${PGHOST}:${PGPORT}                                      !!"
  echo "  !!  and restore from: $(basename "${BACKUP_FILE}")                   !!"
  echo ""
  read -r -p "Type 'yes' to proceed: " CONFIRM
  if [[ "${CONFIRM}" != "yes" ]]; then
    log "Aborted by user."
    exit 0
  fi
fi

# ── Check connectivity ─────────────────────────────────────────────────────────
log "Testing database connectivity ..."
if ! pg_isready -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d postgres &>/dev/null; then
  error "Cannot connect to PostgreSQL at ${PGHOST}:${PGPORT}. Is it running?"
  exit 3
fi
log "Connectivity OK."

# ── Terminate existing connections ─────────────────────────────────────────────
log "Terminating existing connections to '${PGDATABASE}' ..."
PGPASSWORD="${PGPASSWORD}" psql \
  -h "${PGHOST}" -p "${PGPORT}" -U "${PGADMINUSER}" -d postgres \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${PGDATABASE}' AND pid <> pg_backend_pid();" \
  > /dev/null 2>&1 || true

# ── Drop and recreate database ─────────────────────────────────────────────────
log "Dropping database '${PGDATABASE}' ..."
PGPASSWORD="${PGPASSWORD}" dropdb \
  --host="${PGHOST}" --port="${PGPORT}" --username="${PGADMINUSER}" \
  --if-exists "${PGDATABASE}"

log "Creating database '${PGDATABASE}' owned by '${PGUSER}' ..."
PGPASSWORD="${PGPASSWORD}" createdb \
  --host="${PGHOST}" --port="${PGPORT}" --username="${PGADMINUSER}" \
  --owner="${PGUSER}" "${PGDATABASE}"

# ── Restore ────────────────────────────────────────────────────────────────────
log "Restoring from ${BACKUP_FILE} ..."
START_TS=$(date +%s)

if ! gunzip -c "${BACKUP_FILE}" | PGPASSWORD="${PGPASSWORD}" psql \
    --host="${PGHOST}" \
    --port="${PGPORT}" \
    --username="${PGADMINUSER}" \
    --dbname="${PGDATABASE}" \
    --echo-errors \
    > /tmp/evap_restore_$$.log 2>&1; then
  error "Restore failed. Check /tmp/evap_restore_$$.log"
  cat /tmp/evap_restore_$$.log >&2
  exit 4
fi

END_TS=$(date +%s)
DURATION=$(( END_TS - START_TS ))
log "Restore completed in ${DURATION}s."

# ── Verify restore ─────────────────────────────────────────────────────────────
log "Verifying restore — checking table count ..."
TABLE_COUNT=$(PGPASSWORD="${PGPASSWORD}" psql \
  -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" \
  -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" \
  | tr -d ' ')

if [[ -z "${TABLE_COUNT}" || "${TABLE_COUNT}" -lt 1 ]]; then
  error "Restore verification failed: no tables found in '${PGDATABASE}'."
  exit 5
fi

log "Restore verified. Found ${TABLE_COUNT} public tables."
log "Database '${PGDATABASE}' successfully restored from $(basename "${BACKUP_FILE}")."
rm -f /tmp/evap_restore_$$.log
exit 0
