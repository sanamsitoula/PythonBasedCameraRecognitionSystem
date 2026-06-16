#!/bin/bash
# ==============================================================================
# EVAP Database Migration Runner
# Usage: ./migrate.sh [--seed] [--dry-run]
#   --seed:    Also run seed data after migrations
#   --dry-run: Print what would be done, make no changes
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${SCRIPT_DIR}/../backend"
LOG_PREFIX="[EVAP MIGRATE][$(date '+%Y-%m-%d %H:%M:%S')]"

log()   { echo "${LOG_PREFIX} $*"; }
error() { echo "${LOG_PREFIX} [ERROR] $*" >&2; }

# Load environment
if [[ -f "${SCRIPT_DIR}/../.env" ]]; then
  set -a; source "${SCRIPT_DIR}/../.env"; set +a
fi

PGHOST="${PGHOST:-${POSTGRES_HOST:-localhost}}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-${POSTGRES_USER:-evap}}"
PGPASSWORD="${PGPASSWORD:-${POSTGRES_PASSWORD:-}}"
PGDATABASE="${PGDATABASE:-${POSTGRES_DB:-evap}}"
export PGPASSWORD

RUN_SEED=false
DRY_RUN=false
for arg in "$@"; do
  case "$arg" in
    --seed)     RUN_SEED=true ;;
    --dry-run)  DRY_RUN=true ;;
  esac
done

psql_exec() {
  local sql="$1"
  local desc="${2:-SQL}"
  if $DRY_RUN; then
    log "[DRY-RUN] Would execute SQL: ${desc}"
    return 0
  fi
  PGPASSWORD="${PGPASSWORD}" psql \
    -h "${PGHOST}" -p "${PGPORT}" \
    -U "${PGUSER}" -d "${PGDATABASE}" \
    -v ON_ERROR_STOP=1 \
    -c "${sql}" > /dev/null
}

run_sql_file() {
  local file="$1"
  local desc="${2:-$(basename "${file}")}"
  if [[ ! -f "${file}" ]]; then
    log "  SQL file not found, skipping: ${file}"
    return 0
  fi
  if $DRY_RUN; then
    log "[DRY-RUN] Would execute SQL file: ${file}"
    return 0
  fi
  log "  Executing: ${desc}"
  PGPASSWORD="${PGPASSWORD}" psql \
    -h "${PGHOST}" -p "${PGPORT}" \
    -U "${PGUSER}" -d "${PGDATABASE}" \
    -v ON_ERROR_STOP=1 \
    -f "${file}" > /dev/null
}

# ── Wait for postgres ──────────────────────────────────────────────────────────
log "Waiting for PostgreSQL to be ready ..."
RETRIES=30
until pg_isready -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -q; do
  RETRIES=$(( RETRIES - 1 ))
  if [[ $RETRIES -le 0 ]]; then
    error "PostgreSQL did not become ready in time."
    exit 1
  fi
  sleep 2
done
log "PostgreSQL is ready."

# ── Phase 3 schema (idempotent) ────────────────────────────────────────────────
log "Step 1: Applying Phase 3 base schema (if not exists) ..."
SQL_DIR="${BACKEND_DIR}/sql"
run_sql_file "${SQL_DIR}/001_schema.sql"         "Phase 3 base schema"
run_sql_file "${SQL_DIR}/002_phase3_schema.sql"  "Phase 3 extended schema"

# ── Phase 4 schema ─────────────────────────────────────────────────────────────
log "Step 2: Applying Phase 4 EVAP schema ..."
run_sql_file "${SQL_DIR}/010_phase4_evap.sql"    "Phase 4 EVAP schema"
run_sql_file "${SQL_DIR}/011_phase4_indexes.sql" "Phase 4 indexes"

# ── Alembic migrations ─────────────────────────────────────────────────────────
log "Step 3: Running Alembic migrations ..."
if ! command -v alembic &>/dev/null; then
  log "  alembic not found on PATH — trying from virtual environment ..."
  ALEMBIC_CMD="${BACKEND_DIR}/.venv/bin/alembic"
  if [[ ! -x "${ALEMBIC_CMD}" ]]; then
    error "alembic not found. Run: pip install alembic"
    exit 2
  fi
else
  ALEMBIC_CMD="alembic"
fi

if $DRY_RUN; then
  log "[DRY-RUN] Would run: cd ${BACKEND_DIR} && ${ALEMBIC_CMD} upgrade head"
else
  (cd "${BACKEND_DIR}" && "${ALEMBIC_CMD}" upgrade head)
  log "Alembic migrations complete."
fi

# ── Seed reference data ────────────────────────────────────────────────────────
if $RUN_SEED; then
  log "Step 4: Seeding reference data ..."
  run_sql_file "${SQL_DIR}/020_seed_roles.sql"       "Seed roles"
  run_sql_file "${SQL_DIR}/021_seed_alert_types.sql" "Seed alert types"
  run_sql_file "${SQL_DIR}/022_seed_zones.sql"       "Seed zones"

  SEED_SCRIPT="${BACKEND_DIR}/scripts/seed_data.py"
  if [[ -f "${SEED_SCRIPT}" ]]; then
    if $DRY_RUN; then
      log "[DRY-RUN] Would run: python ${SEED_SCRIPT}"
    else
      log "  Running Python seed script ..."
      (cd "${BACKEND_DIR}" && python "${SEED_SCRIPT}")
    fi
  fi
  log "Seed data complete."
fi

log "Migration run finished successfully."
exit 0
