# EVAP Deployment Guide

**Enterprise Video Analytics Platform — Deployment & Operations Reference**
Version 1.0 | Last Updated: June 2026 | Stack: Python 3.13 · FastAPI · PostgreSQL 16 · Redis · RabbitMQ · YOLOv11 · ByteTrack · InsightFace · React 18 · Docker · Kubernetes · Nginx

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Development Setup (Local, No Docker)](#2-development-setup-local-no-docker)
3. [Docker Compose Deployment (Recommended)](#3-docker-compose-deployment-recommended)
4. [Production Docker Setup](#4-production-docker-setup)
5. [Kubernetes Deployment](#5-kubernetes-deployment)
6. [Camera Configuration](#6-camera-configuration)
7. [AI Model Setup](#7-ai-model-setup)
8. [Post-Deployment Checklist](#8-post-deployment-checklist)

---

## 1. Prerequisites

### 1.1 Hardware Requirements

| Tier | Cameras | CPU | RAM | GPU | Storage | Network |
|------|---------|-----|-----|-----|---------|---------|
| **Small** | Up to 20 | 8 cores (e.g., Intel Xeon E-2300) | 32 GB DDR4 | Optional — NVIDIA GTX 1080 (8 GB VRAM) | 2 TB SSD (NVMe recommended) | 1 Gbps |
| **Medium** | 21–100 | 32 cores (e.g., AMD EPYC 7313) | 128 GB DDR4 ECC | 2× NVIDIA RTX 3090 (24 GB VRAM each) | 10 TB SSD RAID-10 | 10 Gbps |
| **Large** | 100+ | Kubernetes cluster (3+ nodes, 64+ cores total) | 256 GB+ DDR5 ECC | 4× NVIDIA A100 80 GB (NVLink) | 50 TB NVMe + object storage (S3/MinIO) | 25 Gbps |

> **Note:** GPU is required for real-time AI inference above 20 cameras. CPU-only mode is supported for development and small deployments with reduced frame rates.

### 1.2 Software Requirements

| Component | Minimum Version | Notes |
|-----------|----------------|-------|
| Ubuntu | 22.04 LTS or 24.04 LTS | Other distros unsupported in production |
| Docker | 24.0+ | `docker --version` to verify |
| Docker Compose | 2.20+ | `docker compose version` to verify |
| NVIDIA Drivers | 535+ | Required for GPU inference |
| CUDA | 12.2+ | Must match driver version |
| Python | 3.13.x | Use `pyenv` or `deadsnakes` PPA |
| Node.js | 20 LTS | `nvm install 20` recommended |
| kubectl | 1.28+ | For Kubernetes deployments only |
| Helm | 3.12+ | For Kubernetes deployments only |

#### Install Docker on Ubuntu 22.04/24.04

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker
docker --version
# Docker version 24.0.x, build ...
```

#### Install NVIDIA Container Toolkit (GPU hosts only)

```bash
distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
# Verify
docker run --rm --gpus all nvidia/cuda:12.2-base-ubuntu22.04 nvidia-smi
```

---

## 2. Development Setup (Local, No Docker)

This setup runs all services natively for rapid development iteration. Use Docker Compose for anything closer to production.

### 2.1 Clone Repository

```bash
git clone https://github.com/beamlab/evap.git
cd evap
```

### 2.2 Python Environment

```bash
# Install Python 3.13 via deadsnakes (Ubuntu)
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt-get update
sudo apt-get install -y python3.13 python3.13-venv python3.13-dev

# Create virtualenv
python3.13 -m venv .venv
source .venv/bin/activate

# Verify
python --version
# Python 3.13.x

# Install backend dependencies
pip install --upgrade pip
pip install -r backend/requirements.txt
```

### 2.3 PostgreSQL Setup

```bash
# Install PostgreSQL 16
sudo apt-get install -y postgresql-16 postgresql-client-16

# Create database and user
sudo -u postgres psql <<EOF
CREATE USER evap_user WITH PASSWORD 'evap_dev_password';
CREATE DATABASE evap_dev OWNER evap_user;
GRANT ALL PRIVILEGES ON DATABASE evap_dev TO evap_user;
\q
EOF

# Verify connection
psql -U evap_user -d evap_dev -h localhost -c "SELECT version();"
```

### 2.4 Redis (Local)

```bash
sudo apt-get install -y redis-server
redis-server --daemonize yes --loglevel notice
redis-cli ping
# PONG
```

### 2.5 RabbitMQ (via Docker)

```bash
docker run -d \
  --name rabbitmq \
  -p 5672:5672 \
  -p 15672:15672 \
  -e RABBITMQ_DEFAULT_USER=evap \
  -e RABBITMQ_DEFAULT_PASS=evap_dev_pass \
  rabbitmq:3.13-management

# Wait ~10 seconds, then verify
curl -s http://localhost:15672 | grep -o "RabbitMQ"
# Open http://localhost:15672 in browser (evap / evap_dev_pass)
```

### 2.6 Environment Configuration

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env`. Each variable is explained below:

```dotenv
# ─── Database ────────────────────────────────────────────────────────────────
# Full SQLAlchemy async DSN for PostgreSQL 16
DATABASE_URL=postgresql+asyncpg://evap_user:evap_dev_password@localhost:5432/evap_dev

# ─── Redis ───────────────────────────────────────────────────────────────────
# Used for caching, session tokens, rate limiting, and Celery result backend
REDIS_URL=redis://localhost:6379/0

# ─── RabbitMQ ────────────────────────────────────────────────────────────────
# Celery broker — routes detection and alert tasks to separate queues
RABBITMQ_URL=amqp://evap:evap_dev_pass@localhost:5672/

# ─── Authentication ──────────────────────────────────────────────────────────
# Secret used to sign JWT tokens — generate with: openssl rand -hex 32
JWT_SECRET_KEY=dev_replace_this_with_64_char_random_hex_string
# Algorithm used for JWT signing — HS256 for single-node, RS256 for multi-tenant
JWT_ALGORITHM=HS256
# Token TTL in minutes
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30

# ─── AI Model Paths ──────────────────────────────────────────────────────────
# Path to YOLOv11 ONNX/PT weights for person + vehicle detection
YOLO_MODEL_PATH=/opt/evap/models/yolo11x.pt
# Path to InsightFace model directory (buffalo_l recommended for prod)
FACE_MODEL_PATH=/opt/evap/models/insightface/buffalo_l
# Path to ANPR (Automatic Number Plate Recognition) model weights
ANPR_MODEL_PATH=/opt/evap/models/anpr/lp_detector_v2.pt

# ─── Object Storage (S3 / MinIO) ─────────────────────────────────────────────
# Stores snapshots, face enrollment images, and exported reports
AWS_S3_BUCKET=evap-media-dev
AWS_S3_REGION=ap-southeast-1
AWS_ACCESS_KEY_ID=your_access_key_id
AWS_SECRET_ACCESS_KEY=your_secret_access_key
# Leave empty to use AWS; set to MinIO endpoint for self-hosted
AWS_S3_ENDPOINT_URL=

# ─── Email (SMTP) ────────────────────────────────────────────────────────────
# Used for alert notifications, password resets, and user invites
SMTP_HOST=smtp.mailgun.org
SMTP_PORT=587
SMTP_USERNAME=postmaster@mg.yourdomain.com
SMTP_PASSWORD=your_smtp_password
SMTP_FROM_EMAIL=evap@yourdomain.com
SMTP_TLS=true

# ─── SMS Alerts (Twilio) ─────────────────────────────────────────────────────
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_FROM_NUMBER=+15551234567

# ─── Push Notifications (Firebase FCM) ──────────────────────────────────────
FCM_SERVER_KEY=your_fcm_server_key_from_firebase_console

# ─── Application ─────────────────────────────────────────────────────────────
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=DEBUG
# Comma-separated list of allowed CORS origins
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
# Base URL used in email links and API docs
BASE_URL=http://localhost:8000

# ─── GPU Configuration ───────────────────────────────────────────────────────
# Comma-separated GPU device IDs. Use "cpu" for CPU-only mode.
GPU_DEVICE_IDS=0
# Maximum GPU memory fraction to allocate (0.0–1.0)
GPU_MEMORY_FRACTION=0.8

# ─── Celery ──────────────────────────────────────────────────────────────────
CELERY_RESULT_BACKEND=redis://localhost:6379/1
# Max number of simultaneous detection tasks per worker
CELERY_DETECTION_CONCURRENCY=4

# ─── ERP Integration ─────────────────────────────────────────────────────────
# Odoo 17 base URL (leave blank to disable)
ODOO_URL=
ODOO_DATABASE=
ODOO_CLIENT_ID=
ODOO_CLIENT_SECRET=
```

### 2.7 Database Migrations

```bash
cd backend
alembic upgrade head
# INFO  [alembic.runtime.migration] Running upgrade ... -> a1b2c3d4e5f6, initial schema
# INFO  [alembic.runtime.migration] Running upgrade a1b2c3d4e5f6 -> ..., add face_embeddings
# ...
```

### 2.8 Seed Development Data

```bash
python -m scripts.seed_data
# Created 3 sites, 15 cameras, 50 employees (dev fixtures)
```

### 2.9 Start Backend Services

Open 4 separate terminal windows:

**Terminal 1 — FastAPI**
```bash
source .venv/bin/activate
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# INFO: Uvicorn running on http://0.0.0.0:8000
# INFO: Application startup complete.
```

**Terminal 2 — Celery Detection Worker**
```bash
source .venv/bin/activate
cd backend
celery -A app.workers worker -Q detection -c 4 --loglevel=info -n detection@%h
```

**Terminal 3 — Celery Alerts Worker**
```bash
source .venv/bin/activate
cd backend
celery -A app.workers worker -Q alerts -c 2 --loglevel=info -n alerts@%h
```

**Terminal 4 — Celery Beat Scheduler**
```bash
source .venv/bin/activate
cd backend
celery -A app.workers beat --loglevel=info --scheduler=django_celery_beat.schedulers:DatabaseScheduler
```

### 2.10 Start Frontend

```bash
cd frontend
npm install
npm run dev
# VITE v5.x  ready in 432 ms
# ➜  Local:   http://localhost:5173/
```

API docs available at: `http://localhost:8000/docs` (Swagger UI) and `http://localhost:8000/redoc`

---

## 3. Docker Compose Deployment (Recommended)

### 3.1 docker-compose.yml

```yaml
# docker-compose.yml
version: "3.9"

x-backend-common: &backend-common
  image: beamlab/evap-backend:latest
  env_file: .env
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy
    rabbitmq:
      condition: service_healthy
  volumes:
    - models_data:/opt/evap/models:ro
    - media_data:/opt/evap/media

services:
  # ── Infrastructure ──────────────────────────────────────────────────────────
  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-evap}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB:-evap}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-evap} -d ${POSTGRES_DB:-evap}"]
      interval: 10s
      timeout: 5s
      retries: 5
    ports:
      - "127.0.0.1:5432:5432"

  redis:
    image: redis:7.2-alpine
    restart: unless-stopped
    command: redis-server --maxmemory 2gb --maxmemory-policy allkeys-lru --save 60 1000
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    ports:
      - "127.0.0.1:6379:6379"

  rabbitmq:
    image: rabbitmq:3.13-management-alpine
    restart: unless-stopped
    environment:
      RABBITMQ_DEFAULT_USER: ${RABBITMQ_USER:-evap}
      RABBITMQ_DEFAULT_PASS: ${RABBITMQ_PASS}
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "ping"]
      interval: 15s
      timeout: 10s
      retries: 5
    ports:
      - "127.0.0.1:5672:5672"
      - "127.0.0.1:15672:15672"

  # ── Application ─────────────────────────────────────────────────────────────
  backend:
    <<: *backend-common
    restart: unless-stopped
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4 --loop uvloop
    ports:
      - "127.0.0.1:8000:8000"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  celery-detection:
    <<: *backend-common
    restart: unless-stopped
    command: celery -A app.workers worker -Q detection -c 4 --loglevel=info -n detection@%h
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  celery-alerts:
    <<: *backend-common
    restart: unless-stopped
    command: celery -A app.workers worker -Q alerts -c 2 --loglevel=info -n alerts@%h

  celery-beat:
    <<: *backend-common
    restart: unless-stopped
    command: celery -A app.workers beat --loglevel=info

  # ── Frontend ─────────────────────────────────────────────────────────────────
  frontend:
    image: beamlab/evap-frontend:latest
    restart: unless-stopped
    environment:
      VITE_API_BASE_URL: ${BASE_URL:-http://localhost}
    ports:
      - "127.0.0.1:3000:80"

  # ── Reverse Proxy ────────────────────────────────────────────────────────────
  nginx:
    image: nginx:1.25-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./deploy/nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./deploy/nginx/conf.d:/etc/nginx/conf.d:ro
      - certbot_certs:/etc/letsencrypt:ro
      - certbot_www:/var/www/certbot:ro
    depends_on:
      - backend
      - frontend

volumes:
  postgres_data:
  redis_data:
  rabbitmq_data:
  models_data:
  media_data:
  certbot_certs:
  certbot_www:
```

### 3.2 Initial Startup

```bash
# 1. Copy and configure environment
cp .env.example .env
nano .env   # Set POSTGRES_PASSWORD, RABBITMQ_PASS, JWT_SECRET_KEY at minimum

# 2. Pull all images
docker compose pull

# 3. Start infrastructure first, wait for health checks
docker compose up -d postgres redis rabbitmq
docker compose ps   # All three should show "healthy" within 30 seconds

# 4. Start application services
docker compose up -d

# 5. Apply database migrations
docker compose exec backend alembic upgrade head

# 6. Create superuser
docker compose exec backend python -m scripts.create_superuser
# Enter email: admin@yourdomain.com
# Enter password:
# Superuser created successfully.

# 7. Verify all services are running
docker compose ps
```

Expected `docker compose ps` output:

```
NAME                    IMAGE                           STATUS          PORTS
evap-postgres-1         postgres:16-alpine              Up (healthy)    127.0.0.1:5432->5432/tcp
evap-redis-1            redis:7.2-alpine                Up (healthy)    127.0.0.1:6379->6379/tcp
evap-rabbitmq-1         rabbitmq:3.13-management-alpine Up (healthy)    127.0.0.1:5672->5672/tcp
evap-backend-1          beamlab/evap-backend:latest     Up              127.0.0.1:8000->8000/tcp
evap-celery-detection-1 beamlab/evap-backend:latest     Up
evap-celery-alerts-1    beamlab/evap-backend:latest     Up
evap-celery-beat-1      beamlab/evap-backend:latest     Up
evap-frontend-1         beamlab/evap-frontend:latest    Up              127.0.0.1:3000->80/tcp
evap-nginx-1            nginx:1.25-alpine               Up              0.0.0.0:80->80/tcp
```

### 3.3 Health Verification

```bash
# Backend API health
curl -s http://localhost:8000/health | python3 -m json.tool
# {
#   "status": "healthy",
#   "database": "connected",
#   "redis": "connected",
#   "rabbitmq": "connected",
#   "ai_engine": "ready",
#   "version": "1.0.0"
# }

# Frontend
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
# 200

# RabbitMQ management
curl -s -u evap:$RABBITMQ_PASS http://localhost:15672/api/overview | python3 -c "import sys,json; d=json.load(sys.stdin); print('RabbitMQ', d['rabbitmq_version'], 'OK')"

# PostgreSQL
docker compose exec postgres psql -U evap -d evap -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';"
# count
# -------
#    42
```

---

## 4. Production Docker Setup

### 4.1 SSL with Let's Encrypt

```bash
# Install certbot
sudo apt-get install -y certbot

# Obtain certificates (port 80 must be open and DNS pointing to this server)
sudo certbot certonly --standalone \
  -d evap.yourdomain.com \
  -d api.evap.yourdomain.com \
  --email admin@yourdomain.com \
  --agree-tos \
  --non-interactive

# Certs are placed at:
# /etc/letsencrypt/live/evap.yourdomain.com/fullchain.pem
# /etc/letsencrypt/live/evap.yourdomain.com/privkey.pem

# Auto-renew (certbot installs a systemd timer automatically; verify it)
sudo systemctl status certbot.timer
```

### 4.2 Nginx Production Configuration

```nginx
# deploy/nginx/nginx.conf
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 4096;
    use epoll;
    multi_accept on;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # Logging
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for" '
                    'rt=$request_time uct=$upstream_connect_time uht=$upstream_header_time urt=$upstream_response_time';
    access_log /var/log/nginx/access.log main;

    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    client_max_body_size 50M;

    # Gzip
    gzip on;
    gzip_comp_level 5;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;

    # Upstreams
    upstream backend {
        least_conn;
        server backend:8000 max_fails=3 fail_timeout=30s;
        keepalive 32;
    }

    upstream frontend {
        server frontend:80;
    }

    # HTTP → HTTPS redirect
    server {
        listen 80;
        server_name evap.yourdomain.com api.evap.yourdomain.com;

        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }

        location / {
            return 301 https://$host$request_uri;
        }
    }

    # HTTPS — Frontend
    server {
        listen 443 ssl http2;
        server_name evap.yourdomain.com;

        ssl_certificate /etc/letsencrypt/live/evap.yourdomain.com/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/evap.yourdomain.com/privkey.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
        ssl_prefer_server_ciphers off;
        ssl_session_cache shared:SSL:10m;
        ssl_session_timeout 1d;

        add_header Strict-Transport-Security "max-age=63072000" always;
        add_header X-Frame-Options DENY;
        add_header X-Content-Type-Options nosniff;

        location / {
            proxy_pass http://frontend;
            proxy_set_header Host $host;
            proxy_cache_bypass $http_upgrade;
        }
    }

    # HTTPS — API
    server {
        listen 443 ssl http2;
        server_name api.evap.yourdomain.com;

        ssl_certificate /etc/letsencrypt/live/evap.yourdomain.com/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/evap.yourdomain.com/privkey.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
        ssl_prefer_server_ciphers off;

        # REST API
        location / {
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_http_version 1.1;
            proxy_read_timeout 120s;
        }

        # WebSocket (live feed, real-time alerts)
        location /ws/ {
            proxy_pass http://backend;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_read_timeout 3600s;
            proxy_send_timeout 3600s;
        }
    }
}
```

### 4.3 docker-compose.prod.yml

```yaml
# docker-compose.prod.yml — overlay on top of docker-compose.yml
version: "3.9"

services:
  postgres:
    restart: always
    deploy:
      resources:
        limits:
          memory: 8G
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
    secrets:
      - postgres_password

  redis:
    restart: always
    deploy:
      resources:
        limits:
          memory: 4G

  backend:
    restart: always
    image: beamlab/evap-backend:${EVAP_VERSION:-latest}
    environment:
      ENVIRONMENT: production
      DEBUG: "false"
      LOG_LEVEL: WARNING
    deploy:
      resources:
        limits:
          memory: 16G
        reservations:
          devices:
            - driver: nvidia
              device_ids: ["0"]
              capabilities: [gpu]
    secrets:
      - jwt_secret_key
      - aws_secret_access_key

  celery-detection:
    restart: always
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 12G
        reservations:
          devices:
            - driver: nvidia
              device_ids: ["1"]
              capabilities: [gpu]

  celery-alerts:
    restart: always
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 2G

  nginx:
    restart: always
    volumes:
      - /etc/letsencrypt:/etc/letsencrypt:ro

secrets:
  postgres_password:
    file: ./secrets/postgres_password.txt
  jwt_secret_key:
    file: ./secrets/jwt_secret_key.txt
  aws_secret_access_key:
    file: ./secrets/aws_secret_access_key.txt
```

**Deploying with production overlay:**

```bash
# Start production stack
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Verify
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
```

---

## 5. Kubernetes Deployment

### 5.1 Prerequisites

```bash
# Verify tools
kubectl version --client
# Client Version: v1.28.x

helm version
# version.BuildInfo{Version:"v3.12.x", ...}

# Verify cluster connectivity
kubectl cluster-info
kubectl get nodes
# NAME           STATUS   ROLES           AGE   VERSION
# node-1         Ready    control-plane   10d   v1.28.x
# node-2         Ready    worker          10d   v1.28.x
# node-3         Ready    worker          10d   v1.28.x
```

### 5.2 Namespace and Secrets

```bash
# Create namespace
kubectl create namespace evap

# Create application secrets from .env file
kubectl create secret generic evap-secrets \
  --from-env-file=.env \
  -n evap

# Verify
kubectl get secret evap-secrets -n evap
```

### 5.3 Install PostgreSQL via Helm

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

helm install evap-postgres bitnami/postgresql \
  -n evap \
  -f deploy/kubernetes/postgres-values.yaml \
  --version 13.4.4

# postgres-values.yaml contents:
# auth:
#   username: evap
#   password: "your-strong-password"
#   database: evap
# primary:
#   resources:
#     limits:
#       memory: 8Gi
#       cpu: 4000m
#   persistence:
#     size: 100Gi
#     storageClass: fast-ssd
# metrics:
#   enabled: true

# Wait for PostgreSQL pod to be ready
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=postgresql -n evap --timeout=120s
```

### 5.4 Install Redis via Helm

```bash
helm install evap-redis bitnami/redis \
  -n evap \
  -f deploy/kubernetes/redis-values.yaml \
  --version 18.6.1

# redis-values.yaml contents:
# auth:
#   enabled: true
#   password: "your-redis-password"
# master:
#   resources:
#     limits:
#       memory: 4Gi
#       cpu: 2000m
#   persistence:
#     size: 20Gi
# replica:
#   replicaCount: 2

kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=redis -n evap --timeout=120s
```

### 5.5 Deploy Application Manifests

```bash
# Deploy backend API
kubectl apply -f deploy/kubernetes/backend-deployment.yaml

# Deploy Celery workers
kubectl apply -f deploy/kubernetes/celery-deployment.yaml

# Deploy frontend
kubectl apply -f deploy/kubernetes/frontend-deployment.yaml

# Apply Ingress (requires nginx-ingress-controller installed in cluster)
kubectl apply -f deploy/kubernetes/ingress.yaml

# Apply Horizontal Pod Autoscaler
kubectl apply -f deploy/kubernetes/hpa.yaml

# Verify all pods are running
kubectl get pods -n evap -w
```

### 5.6 backend-deployment.yaml

```yaml
# deploy/kubernetes/backend-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: evap-backend
  namespace: evap
  labels:
    app: evap-backend
    version: "1.0"
spec:
  replicas: 2
  selector:
    matchLabels:
      app: evap-backend
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: evap-backend
        version: "1.0"
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: backend
          image: beamlab/evap-backend:1.0.0
          imagePullPolicy: Always
          command:
            - uvicorn
            - app.main:app
            - --host
            - "0.0.0.0"
            - --port
            - "8000"
            - --workers
            - "4"
            - --loop
            - uvloop
          ports:
            - containerPort: 8000
              name: http
          env:
            - name: ENVIRONMENT
              value: production
          envFrom:
            - secretRef:
                name: evap-secrets
          resources:
            requests:
              memory: "2Gi"
              cpu: "1000m"
            limits:
              memory: "8Gi"
              cpu: "4000m"
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 15
            timeoutSeconds: 5
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8000
            initialDelaySeconds: 20
            periodSeconds: 10
            timeoutSeconds: 3
            failureThreshold: 3
          volumeMounts:
            - name: models-volume
              mountPath: /opt/evap/models
              readOnly: true
            - name: media-volume
              mountPath: /opt/evap/media
      volumes:
        - name: models-volume
          persistentVolumeClaim:
            claimName: evap-models-pvc
        - name: media-volume
          persistentVolumeClaim:
            claimName: evap-media-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: evap-backend-svc
  namespace: evap
spec:
  selector:
    app: evap-backend
  ports:
    - name: http
      protocol: TCP
      port: 80
      targetPort: 8000
  type: ClusterIP
```

### 5.7 hpa.yaml

```yaml
# deploy/kubernetes/hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: evap-backend-hpa
  namespace: evap
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: evap-backend
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Replicas
          value: 1
          periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
        - type: Replicas
          value: 2
          periodSeconds: 60
```

### 5.8 Run Post-Deploy Migrations

```bash
# Run as a one-off job
kubectl run evap-migrate \
  --image=beamlab/evap-backend:1.0.0 \
  --restart=Never \
  --rm -it \
  --env-from=evap-secrets \
  -n evap \
  -- alembic upgrade head
```

---

## 6. Camera Configuration

### 6.1 RTSP URL Formats by Brand

| Brand | RTSP URL Format |
|-------|----------------|
| **Hikvision** | `rtsp://admin:password@192.168.1.100:554/Streaming/Channels/101` (main stream) |
| **Dahua** | `rtsp://admin:password@192.168.1.101:554/cam/realmonitor?channel=1&subtype=0` |
| **Axis** | `rtsp://root:password@192.168.1.102:554/axis-media/media.amp` |
| **Hanwha (Samsung)** | `rtsp://admin:password@192.168.1.103:554/profile1/media.smp` |
| **Uniview** | `rtsp://admin:password@192.168.1.104:554/unicast/c1/s0/live` |
| **Generic ONVIF** | `rtsp://user:pass@192.168.1.105:554/onvif1` |

> **Sub-stream tip:** Use the secondary/sub stream (e.g., `/Streaming/Channels/102` for Hikvision) for the live dashboard feed and reserve the main stream for recording and AI processing.

### 6.2 Register Camera via API

```bash
# Authenticate first
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@yourdomain.com","password":"your_password"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Register a new camera
curl -s -X POST http://localhost:8000/api/v1/cameras/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Main Entrance",
    "rtsp_url": "rtsp://admin:password@192.168.1.100:554/Streaming/Channels/101",
    "site_id": "site-uuid-here",
    "location_description": "Building A - Ground Floor - Main Door",
    "resolution": "1920x1080",
    "fps": 25,
    "is_ptz": false,
    "enabled": true
  }' | python3 -m json.tool

# Expected response:
# {
#   "id": "cam-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
#   "name": "Main Entrance",
#   "status": "connecting",
#   "stream_health": null,
#   ...
# }
```

### 6.3 Activate AI Pipeline for a Camera

```bash
CAMERA_ID="cam-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

curl -s -X PATCH "http://localhost:8000/api/v1/cameras/$CAMERA_ID/ai-config" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "person_detection": true,
    "face_recognition": true,
    "vehicle_detection": true,
    "anpr": false,
    "crowd_detection": true,
    "loitering_threshold_seconds": 120,
    "zone_intrusion": true
  }' | python3 -m json.tool
```

---

## 7. AI Model Setup

### 7.1 YOLOv11 Weights

```bash
mkdir -p /opt/evap/models

# Install Ultralytics
pip install ultralytics==8.3.x

# Download YOLOv11x (largest, highest accuracy — use for production)
python3 -c "from ultralytics import YOLO; YOLO('yolo11x.pt')"
# Model downloads to ~/.config/Ultralytics/

# Move to EVAP model directory
cp ~/.config/Ultralytics/yolo11x.pt /opt/evap/models/

# For lower-resource deployments use yolo11m.pt or yolo11s.pt
python3 -c "from ultralytics import YOLO; YOLO('yolo11m.pt')"
cp ~/.config/Ultralytics/yolo11m.pt /opt/evap/models/
```

### 7.2 InsightFace Models

```bash
pip install insightface==0.7.3 onnxruntime-gpu==1.17.x

# Create model directory
mkdir -p /opt/evap/models/insightface

# buffalo_l: highest accuracy (recommended for production)
python3 -c "
import insightface
from insightface.app import FaceAnalysis
app = FaceAnalysis(name='buffalo_l', root='/opt/evap/models/insightface')
app.prepare(ctx_id=0, det_size=(640, 640))
print('buffalo_l downloaded and ready')
"

# buffalo_sc: small/CPU-friendly (use for development or edge nodes)
python3 -c "
import insightface
from insightface.app import FaceAnalysis
app = FaceAnalysis(name='buffalo_sc', root='/opt/evap/models/insightface')
app.prepare(ctx_id=-1, det_size=(320, 320))
print('buffalo_sc downloaded and ready')
"
```

### 7.3 ANPR Model Setup

```bash
mkdir -p /opt/evap/models/anpr

# Download license plate detector weights
# (Replace URL with your actual model hosting location)
wget -O /opt/evap/models/anpr/lp_detector_v2.pt \
  https://storage.beamlab.dev/models/evap/lp_detector_v2.pt

# Verify integrity
sha256sum /opt/evap/models/anpr/lp_detector_v2.pt
# Expected: <hash provided in release notes>
```

### 7.4 GPU Memory Allocation Strategy

For a server with multiple GPUs, assign models to specific devices to prevent memory contention:

| GPU | Model | VRAM Usage |
|-----|-------|-----------|
| GPU 0 | YOLOv11x (detection + tracking) | ~8 GB |
| GPU 0 | ByteTrack (tracking state) | ~0.5 GB |
| GPU 1 | InsightFace buffalo_l (face recognition) | ~4 GB |
| GPU 1 | ANPR model | ~2 GB |

```python
# In app/config.py — GPU assignment
AI_CONFIG = {
    "yolo": {"device": "cuda:0", "half_precision": True},
    "bytetrack": {"device": "cuda:0"},
    "insightface": {"device": "cuda:1", "ctx_id": 1},
    "anpr": {"device": "cuda:1"},
}
```

### 7.5 Model Warm-Up on Startup

EVAP warms up all models at application startup to eliminate cold-start latency on the first detection request. Warm-up is triggered automatically from `app/main.py` lifespan handler. To trigger manually:

```bash
curl -s -X POST http://localhost:8000/api/v1/system/ai/warmup \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
# {
#   "status": "warmed_up",
#   "models": ["yolo11x", "insightface_buffalo_l", "anpr"],
#   "warmup_time_seconds": 8.3
# }
```

---

## 8. Post-Deployment Checklist

Complete these steps after every fresh deployment or major upgrade.

```
[ ] All containers/pods show healthy status (docker compose ps / kubectl get pods -n evap)
[ ] Database migrations applied with no errors (alembic upgrade head)
[ ] Superuser account created and login verified via browser
[ ] At least one camera connected and showing "streaming" status in dashboard
[ ] AI pipeline activated on camera and detections appearing in event feed
[ ] Test alert fires correctly:
      — Create an "Occupancy > 0" alert rule on the test camera
      — Walk in front of camera
      — Confirm alert appears in Alerts panel within 10 seconds
[ ] SMTP verified: send test email from Admin > Notifications > Test Email
[ ] Automated database backup configured and first backup completed (check S3)
[ ] SSL certificate valid: curl -vI https://evap.yourdomain.com 2>&1 | grep "SSL certificate verify"
[ ] Monitoring dashboards accessible at http://monitoring.evap.local:3000
[ ] RabbitMQ queues empty (no stuck messages): http://localhost:15672/#/queues
[ ] Celery workers registered and consuming: celery -A app.workers inspect active
[ ] Review /var/log/nginx/error.log — no 5xx errors
[ ] GPU utilization normal under test load: watch -n1 nvidia-smi
```

---

*For questions, open an issue at https://github.com/beamlab/evap or contact support@beamlab.dev*
