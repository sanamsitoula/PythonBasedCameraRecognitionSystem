#!/bin/bash
# ==============================================================================
# EVAP Daily PostgreSQL Backup Script
# Usage: ./backup.sh [--dry-run]
# Schedule via cron: 0 2 * * * /opt/evap/scripts/backup.sh >> /var/log/evap/backup.log 2>&1
# ==============================================================================

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/evap}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILENAME="evap_backup_${TIMESTAMP}.sql.gz"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_FILENAME}"
LOG_PREFIX="[EVAP BACKUP][$(date '+%Y-%m-%d %H:%M:%S')]"

# Database connection — prefer env, fall back to .env file
if [[ -z "${DATABASE_URL:-}" && -f "${SCRIPT_DIR}/../.env" ]]; then
  set -a; source "${SCRIPT_DIR}/../.env"; set +a
fi

PGHOST="${PGHOST:-${POSTGRES_HOST:-localhost}}"
PGPORT="${PGPORT:-${POSTGRES_PORT:-5432}}"
PGUSER="${PGUSER:-${POSTGRES_USER:-evap}}"
PGPASSWORD="${PGPASSWORD:-${POSTGRES_PASSWORD:-}}"
PGDATABASE="${PGDATABASE:-${POSTGRES_DB:-evap}}"
export PGPASSWORD

# S3 / object storage
S3_BUCKET="${S3_BUCKET:-}"
S3_PREFIX="${S3_PREFIX:-backups/postgres}"
AWS_CLI="${AWS_CLI:-aws}"

# Email alerts
ALERT_EMAIL="${ALERT_EMAIL:-}"
SMTP_FROM="${SMTP_FROM:-evap-backup@localhost}"

# ── Helpers ────────────────────────────────────────────────────────────────────
log()   { echo "${LOG_PREFIX} $*"; }
warn()  { echo "${LOG_PREFIX} [WARN] $*" >&2; }
error() { echo "${LOG_PREFIX} [ERROR] $*" >&2; }

send_failure_email() {
  local subject="$1"
  local body="$2"
  if [[ -n "${ALERT_EMAIL}" ]]; then
    echo "${body}" | mail -s "${subject}" -r "${SMTP_FROM}" "${ALERT_EMAIL}" 2>/dev/null || true
  fi
}

cleanup_old_backups() {
  log "Removing backups older than ${BACKUP_RETENTION_DAYS} days from ${BACKUP_DIR}"
  find "${BACKUP_DIR}" -name "evap_backup_*.sql.gz" -mtime "+${BACKUP_RETENTION_DAYS}" -exec rm -f {} \; -print | while read -r f; do
    log "  Deleted: ${f}"
  done
}

upload_to_s3() {
  local local_path="$1"
  local filename
  filename="$(basename "${local_path}")"
  if [[ -z "${S3_BUCKET}" ]]; then
    log "S3_BUCKET not configured — skipping S3 upload."
    return 0
  fi
  log "Uploading to s3://${S3_BUCKET}/${S3_PREFIX}/${filename} ..."
  if "${AWS_CLI}" s3 cp "${local_path}" "s3://${S3_BUCKET}/${S3_PREFIX}/${filename}" \
      --storage-class STANDARD_IA \
      --only-show-errors; then
    log "S3 upload successful."
  else
    warn "S3 upload failed — backup kept locally."
  fi

  # Remove old S3 backups beyond retention (list and delete)
  log "Cleaning up S3 backups older than ${BACKUP_RETENTION_DAYS} days ..."
  local cutoff_epoch
  cutoff_epoch=$(date -d "-${BACKUP_RETENTION_DAYS} days" +%s 2>/dev/null || date -v "-${BACKUP_RETENTION_DAYS}d" +%s)
  "${AWS_CLI}" s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}/" 2>/dev/null \
    | awk '{print $1, $2, $4}' \
    | while read -r date time fname; do
        local fepoch
        fepoch=$(date -d "${date} ${time}" +%s 2>/dev/null || date -j -f "%Y-%m-%d %H:%M:%S" "${date} ${time}" +%s 2>/dev/null || echo 0)
        if [[ "${fepoch}" -lt "${cutoff_epoch}" && "${fname}" == evap_backup_*.sql.gz ]]; then
          log "  Deleting from S3: ${fname}"
          "${AWS_CLI}" s3 rm "s3://${S3_BUCKET}/${S3_PREFIX}/${fname}" --only-show-errors
        fi
      done || true
}

verify_backup() {
  local path="$1"
  log "Verifying backup integrity: ${path}"
  if gzip -t "${path}"; then
    local size
    size=$(du -sh "${path}" | cut -f1)
    log "Backup verification passed. Size: ${size}"
    return 0
  else
    error "Backup file is corrupt: ${path}"
    return 1
  fi
}

# ── Pre-flight checks ──────────────────────────────────────────────────────────
DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=true
  log "DRY RUN mode — no actual backup will be performed."
fi

for cmd in pg_dump gzip; do
  if ! command -v "${cmd}" &>/dev/null; then
    error "Required command not found: ${cmd}"
    send_failure_email "[EVAP] Backup PRE-FLIGHT FAILED on $(hostname)" \
      "Required command '${cmd}' not found on $(hostname) at ${TIMESTAMP}."
    exit 1
  fi
done

mkdir -p "${BACKUP_DIR}"
chmod 750 "${BACKUP_DIR}"

# ── Perform backup ─────────────────────────────────────────────────────────────
if $DRY_RUN; then
  log "Would run: pg_dump -h ${PGHOST} -p ${PGPORT} -U ${PGUSER} -d ${PGDATABASE} | gzip > ${BACKUP_PATH}"
  exit 0
fi

log "Starting backup of database '${PGDATABASE}' on ${PGHOST}:${PGPORT} ..."
log "Output: ${BACKUP_PATH}"

START_TS=$(date +%s)

if ! pg_dump \
    --host="${PGHOST}" \
    --port="${PGPORT}" \
    --username="${PGUSER}" \
    --dbname="${PGDATABASE}" \
    --format=plain \
    --no-password \
    --verbose \
    2>"${BACKUP_DIR}/evap_backup_${TIMESTAMP}.log" \
  | gzip -9 > "${BACKUP_PATH}"; then
  error "pg_dump failed! Check log: ${BACKUP_DIR}/evap_backup_${TIMESTAMP}.log"
  rm -f "${BACKUP_PATH}"
  send_failure_email "[EVAP] Database Backup FAILED on $(hostname)" \
    "pg_dump failed for database '${PGDATABASE}' on $(hostname) at ${TIMESTAMP}. Check /var/log/evap/backup.log"
  exit 2
fi

END_TS=$(date +%s)
DURATION=$(( END_TS - START_TS ))
log "Backup completed in ${DURATION}s."

# ── Verify ─────────────────────────────────────────────────────────────────────
if ! verify_backup "${BACKUP_PATH}"; then
  send_failure_email "[EVAP] Backup VERIFICATION FAILED on $(hostname)" \
    "Backup file ${BACKUP_PATH} failed gzip integrity check."
  exit 3
fi

# ── Upload to S3 ───────────────────────────────────────────────────────────────
upload_to_s3 "${BACKUP_PATH}"

# ── Clean up local old backups ─────────────────────────────────────────────────
cleanup_old_backups

log "Backup job finished successfully: ${BACKUP_FILENAME}"
exit 0
