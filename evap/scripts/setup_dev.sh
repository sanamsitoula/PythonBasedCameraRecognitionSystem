#!/bin/bash
# ==============================================================================
# EVAP Developer Environment Setup
# Usage: ./setup_dev.sh [--no-frontend] [--no-seed]
# Tested on: Ubuntu 22.04, macOS 14+
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}/.."
LOG_PREFIX="[EVAP SETUP]"

log()     { echo "${LOG_PREFIX} $*"; }
success() { echo "${LOG_PREFIX} ✔ $*"; }
warn()    { echo "${LOG_PREFIX} ⚠ $*" >&2; }
error()   { echo "${LOG_PREFIX} ✖ $*" >&2; }
section() { echo ""; echo "${LOG_PREFIX} ── $* ──────────────────────────"; }

NO_FRONTEND=false
NO_SEED=false
for arg in "$@"; do
  case "$arg" in
    --no-frontend) NO_FRONTEND=true ;;
    --no-seed)     NO_SEED=true ;;
  esac
done

# ── 1. Check prerequisites ─────────────────────────────────────────────────────
section "Checking Prerequisites"

check_cmd() {
  local cmd="$1" desc="${2:-$1}" min_ver="${3:-}"
  if ! command -v "$cmd" &>/dev/null; then
    error "Required tool not found: ${desc}. Please install it and re-run."
    exit 1
  fi
  if [[ -n "$min_ver" ]]; then
    local ver
    ver=$("$cmd" --version 2>&1 | head -1 || true)
    log "  ${desc}: ${ver}"
  else
    success "${desc} found: $(command -v "$cmd")"
  fi
}

check_cmd docker     "Docker"           "20"
check_cmd "docker"   "Docker Compose"
# Verify compose is v2 (docker compose) or v1 (docker-compose)
if docker compose version &>/dev/null 2>&1; then
  COMPOSE_CMD="docker compose"
elif command -v docker-compose &>/dev/null; then
  COMPOSE_CMD="docker-compose"
else
  error "docker compose (v2) or docker-compose (v1) not found."
  exit 1
fi
success "Docker Compose: ${COMPOSE_CMD}"

check_cmd python3 "Python 3" "3.11"
PYTHON_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"; then
  success "Python ${PYTHON_VER}"
else
  warn "Python ${PYTHON_VER} detected; recommend 3.11+."
fi

if ! $NO_FRONTEND; then
  check_cmd node "Node.js"
  NODE_VER=$(node --version)
  success "Node.js ${NODE_VER}"
  check_cmd npm "npm"
fi

# ── 2. Copy .env ───────────────────────────────────────────────────────────────
section "Environment Configuration"

ENV_EXAMPLE="${ROOT_DIR}/.env.example"
ENV_FILE="${ROOT_DIR}/.env"

if [[ ! -f "${ENV_EXAMPLE}" ]]; then
  error ".env.example not found at ${ENV_EXAMPLE}"
  exit 1
fi

if [[ -f "${ENV_FILE}" ]]; then
  warn ".env already exists — skipping copy. Review and update manually if needed."
else
  cp "${ENV_EXAMPLE}" "${ENV_FILE}"
  success "Copied .env.example → .env"
  log "  Review ${ENV_FILE} and update credentials before starting services."
fi

# Load env
set -a; source "${ENV_FILE}"; set +a

# ── 3. Create Python virtual environment and install deps ──────────────────────
section "Python Backend Dependencies"

BACKEND_DIR="${ROOT_DIR}/backend"
VENV_DIR="${BACKEND_DIR}/.venv"

if [[ ! -d "${VENV_DIR}" ]]; then
  log "Creating Python virtual environment at ${VENV_DIR} ..."
  python3 -m venv "${VENV_DIR}"
  success "Virtual environment created."
else
  log "Virtual environment already exists at ${VENV_DIR}."
fi

log "Installing Python dependencies ..."
"${VENV_DIR}/bin/pip" install --upgrade pip --quiet
"${VENV_DIR}/bin/pip" install -r "${BACKEND_DIR}/requirements.txt" --quiet
success "Python dependencies installed."

# ── 4. Start Docker Compose services (infra only) ─────────────────────────────
section "Starting Docker Compose Infrastructure Services"

COMPOSE_FILE="${ROOT_DIR}/deploy/docker-compose.yml"
cd "${ROOT_DIR}"

log "Pulling latest images ..."
${COMPOSE_CMD} -f "${COMPOSE_FILE}" pull postgres redis rabbitmq --quiet 2>/dev/null || true

log "Starting postgres, redis, rabbitmq ..."
${COMPOSE_CMD} -f "${COMPOSE_FILE}" up -d postgres redis rabbitmq

log "Waiting for services to become healthy (up to 60s) ..."
RETRIES=30
until ${COMPOSE_CMD} -f "${COMPOSE_FILE}" exec -T postgres \
    pg_isready -U "${POSTGRES_USER:-evap}" -d "${POSTGRES_DB:-evap}" -q 2>/dev/null; do
  RETRIES=$(( RETRIES - 1 ))
  [[ $RETRIES -le 0 ]] && { error "PostgreSQL did not become ready."; exit 1; }
  sleep 2
done
success "PostgreSQL is ready."

until ${COMPOSE_CMD} -f "${COMPOSE_FILE}" exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; do
  RETRIES=$(( RETRIES - 1 ))
  [[ $RETRIES -le 0 ]] && { error "Redis did not become ready."; exit 1; }
  sleep 2
done
success "Redis is ready."

# ── 5. Run database migrations ─────────────────────────────────────────────────
section "Running Database Migrations"

SEED_ARG=""
$NO_SEED || SEED_ARG="--seed"

bash "${SCRIPT_DIR}/migrate.sh" ${SEED_ARG}
success "Migrations complete."

# ── 6. Install frontend dependencies ──────────────────────────────────────────
if ! $NO_FRONTEND; then
  section "Installing Frontend Dependencies"
  FRONTEND_DIR="${ROOT_DIR}/frontend"
  if [[ ! -d "${FRONTEND_DIR}" ]]; then
    warn "Frontend directory not found at ${FRONTEND_DIR} — skipping."
  else
    (cd "${FRONTEND_DIR}" && npm install --legacy-peer-deps)
    success "Frontend dependencies installed."
  fi
fi

# ── 7. Start backend dev server ────────────────────────────────────────────────
section "Starting Backend Dev Server"

BACKEND_PID_FILE="/tmp/evap_backend_dev.pid"
log "Starting FastAPI backend with uvicorn (hot-reload) ..."
(
  cd "${BACKEND_DIR}"
  "${VENV_DIR}/bin/uvicorn" app.main:app \
    --host 0.0.0.0 --port 8000 \
    --reload \
    --log-level debug &
  echo $! > "${BACKEND_PID_FILE}"
)
sleep 2
if kill -0 "$(cat "${BACKEND_PID_FILE}")" 2>/dev/null; then
  success "Backend running at http://localhost:8000 (PID $(cat "${BACKEND_PID_FILE}"))"
  log "  API docs: http://localhost:8000/docs"
else
  warn "Backend may have failed to start. Check logs above."
fi

# ── 8. Start frontend dev server ───────────────────────────────────────────────
if ! $NO_FRONTEND; then
  section "Starting Frontend Dev Server"
  FRONTEND_DIR="${ROOT_DIR}/frontend"
  if [[ -d "${FRONTEND_DIR}" ]]; then
    FRONTEND_PID_FILE="/tmp/evap_frontend_dev.pid"
    (cd "${FRONTEND_DIR}" && npm start &)
    echo $! > "${FRONTEND_PID_FILE}" 2>/dev/null || true
    success "Frontend dev server starting at http://localhost:3000"
  fi
fi

# ── Summary ────────────────────────────────────────────────────────────────────
section "Setup Complete"
echo ""
echo "  Backend API:  http://localhost:8000"
echo "  API Docs:     http://localhost:8000/docs"
if ! $NO_FRONTEND; then
  echo "  Frontend:     http://localhost:3000"
fi
echo "  RabbitMQ UI:  http://localhost:15672 (${RABBITMQ_USER:-evap} / ...)"
echo ""
echo "  To stop infrastructure: ${COMPOSE_CMD} -f ${COMPOSE_FILE} down"
echo "  Logs: ${COMPOSE_CMD} -f ${COMPOSE_FILE} logs -f"
echo ""
