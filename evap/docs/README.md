```
███████╗██╗   ██╗ █████╗ ██████╗
██╔════╝██║   ██║██╔══██╗██╔══██╗
█████╗  ██║   ██║███████║██████╔╝
██╔══╝  ╚██╗ ██╔╝██╔══██║██╔═══╝
███████╗ ╚████╔╝ ██║  ██║██║
╚══════╝  ╚═══╝  ╚═╝  ╚═╝╚═╝

  Enterprise Video Analytics Platform
  ─────────────────────────────────────────────
  Real-time detection · Face recognition · ANPR
  Employee management · Attendance automation
```

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)](https://reactjs.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7.2-DC382D?style=flat-square&logo=redis&logoColor=white)](https://redis.io)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

---

## Project Overview

**EVAP (Enterprise Video Analytics Platform)** is a production-grade, AI-driven video surveillance and analytics system. It transforms passive CCTV infrastructure into an active intelligence layer — processing live RTSP streams, identifying employees via face recognition, automating attendance, and surfacing real-time insights through a React web dashboard.

The stack is a FastAPI async backend with SQLAlchemy + PostgreSQL, a Celery/RabbitMQ worker layer for async jobs, Redis for caching and WebSocket state, and a React 18 SPA frontend. The AI pipeline (YOLOv11 + ByteTrack + InsightFace) runs as a separate engine and publishes structured events into the backend.

---

## Quick Start (Windows)

The easiest way to run EVAP locally on Windows is the included launcher script.

```bat
:: From the project root
start_evap.bat
```

This will:
1. Clear stale Python `__pycache__` bytecode (prevents 405/500 errors after edits).
2. Free ports 8000 and 3000 if occupied.
3. Start the FastAPI backend in a new window on `http://localhost:8000`.
4. Wait 3 seconds, then start the React frontend on `http://localhost:3000`.
5. Write logs to `logs\backend.log` and `logs\frontend.log`.
6. Press any key in the launcher window to stop both services.

**Watch logs live:**
```powershell
# Backend
powershell Get-Content -Wait logs\backend.log

# Frontend
powershell Get-Content -Wait logs\frontend.log
```

**Key URLs after startup:**

| URL | Purpose |
|---|---|
| `http://localhost:3000` | Web dashboard |
| `http://localhost:8000/docs` | Interactive API docs (Swagger UI) |
| `http://localhost:8000/redoc` | ReDoc API reference |
| `http://localhost:8000/health` | Health check endpoint |
| `http://localhost:8000/metrics` | Prometheus metrics |

---

## Manual Setup

### Prerequisites

- Python 3.13+
- Node.js 20+ with npm
- PostgreSQL 16
- Redis 7.x

### Backend

```bash
cd evap/backend

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux/macOS

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env: set DATABASE_URL, REDIS_URL, SECRET_KEY, etc.

# Run database migrations
alembic upgrade head

# Start backend (reload mode for development)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --app-dir .
```

### Frontend

```bash
cd evap/frontend
npm install
npm start       # development server on http://localhost:3000
npm run build   # production build → build/
```

### Face Enrollment (CLI)

```bash
# Enroll an employee from the command line
python enrollment_cli.py --employee-id EMP001 --photos-dir ./photos/EMP001/

# Or use the face enrollment module directly
python face_enrollment.py
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      DATA INGESTION LAYER                        │
│  RTSP cameras → FFmpeg decode → Frame Buffer (Redis per camera)  │
└─────────────────────────────┬────────────────────────────────────┘
                              │
┌─────────────────────────────▼────────────────────────────────────┐
│                      AI PROCESSING LAYER                         │
│  YOLOv11 detection → ByteTrack multi-object tracking             │
│  InsightFace ArcFace embeddings → person re-identification       │
│  ANPR pipeline (plate detect → LPRNet OCR)                       │
└─────────────────────────────┬────────────────────────────────────┘
                              │ Structured Events (JSON)
┌─────────────────────────────▼────────────────────────────────────┐
│                     MESSAGE QUEUE LAYER                          │
│  RabbitMQ: evap.events · evap.alerts · evap.notifications        │
│  Celery workers: AI tasks · notifications · reports              │
└──────┬──────────────────────┬────────────────────────────────────┘
       │                      │
┌──────▼──────────────────────▼────────────────────────────────────┐
│                    APPLICATION LAYER                             │
│  FastAPI async REST API v1 · WebSocket manager                   │
│  SQLAlchemy ORM · Alembic migrations                             │
│  Prometheus metrics middleware · JWT auth                        │
└──────┬──────────────────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER                           │
│  React 18 SPA — Dashboard · Cameras · Employees · Attendance    │
│  Alerts · Visitors · Vehicles · Reports · Floor Map · Settings  │
│  Live WebSocket feeds · Recharts · Leaflet GIS                  │
└─────────────────────────────────────────────────────────────────┘
       │                    │                    │
  PostgreSQL 16          Redis 7.2           S3 / MinIO
  (primary store)    (cache/sessions)      (video/snapshots)
```

---

## Folder Structure

```
cctv_phase1/
├── start_evap.bat                ← one-click Windows launcher
├── logs/                         ← runtime logs (backend.log, frontend.log)
│
├── evap/
│   ├── backend/
│   │   ├── app/
│   │   │   ├── api/v1/           ← REST endpoints
│   │   │   │   ├── alerts.py
│   │   │   │   ├── analytics.py
│   │   │   │   ├── attendance.py
│   │   │   │   ├── auth.py
│   │   │   │   ├── cameras.py
│   │   │   │   ├── dashboard.py
│   │   │   │   ├── employees.py
│   │   │   │   ├── erp.py
│   │   │   │   ├── maps.py
│   │   │   │   ├── notifications.py
│   │   │   │   ├── reports.py
│   │   │   │   ├── sites.py
│   │   │   │   ├── vehicles.py
│   │   │   │   └── visitors.py
│   │   │   ├── core/             ← config, database, security, redis, rabbitmq
│   │   │   ├── models/           ← SQLAlchemy ORM models
│   │   │   ├── schemas/          ← Pydantic request/response schemas
│   │   │   ├── services/         ← business logic layer
│   │   │   ├── websocket/        ← WebSocket manager and event handlers
│   │   │   ├── workers/          ← Celery tasks (AI, notifications, reports)
│   │   │   └── main.py           ← FastAPI app entry point
│   │   ├── alembic/              ← DB migrations
│   │   └── requirements.txt
│   │
│   ├── frontend/
│   │   └── src/
│   │       ├── pages/            ← full-page views
│   │       │   ├── Dashboard.jsx
│   │       │   ├── Cameras.jsx
│   │       │   ├── Employees.jsx
│   │       │   ├── EmployeeDetail.jsx
│   │       │   ├── Attendance.jsx
│   │       │   ├── Alerts.jsx
│   │       │   ├── Analytics.jsx
│   │       │   ├── Vehicles.jsx
│   │       │   ├── Visitors.jsx
│   │       │   ├── FloorMap.jsx
│   │       │   ├── Reports.jsx
│   │       │   ├── Settings.jsx
│   │       │   └── Login.jsx
│   │       ├── components/       ← reusable UI components
│   │       │   ├── Dashboard/    ← CameraMonitor, StatsCard, AlertsPanel, OccupancyChart
│   │       │   ├── Layout/       ← Layout, Navbar, Sidebar
│   │       │   └── common/       ← DataTable, Modal, StatusBadge, DateRangePicker
│   │       ├── services/
│   │       │   ├── api.js        ← Axios API client for all endpoints
│   │       │   └── websocket.js  ← WebSocket client
│   │       ├── hooks/            ← useAuth, useWebSocket
│   │       └── context/          ← AuthContext
│   │
│   ├── ai_engine/                ← AI pipeline (ANPR, detection)
│   └── docs/
│       └── README.md             ← this file
│
├── enrollment_cli.py             ← CLI face enrollment tool
├── face_enrollment.py            ← face enrollment module
├── face_recognition_engine.py    ← InsightFace recognition engine
├── attendance_engine.py          ← attendance calculation logic
├── cross_camera_reid.py          ← cross-camera re-identification
├── detection.py                  ← YOLO detection wrapper
├── tracker.py                    ← ByteTrack wrapper
│
└── tests/
    ├── unit/
    └── integration/
```

---

## Implemented Modules

| Module | Backend Endpoint | Frontend Page | Status |
|---|---|---|---|
| **Authentication** | `POST /api/v1/auth/login` | `Login.jsx` | Done |
| **Dashboard** | `GET /api/v1/dashboard/stats` + WebSocket | `Dashboard.jsx` | Done |
| **Camera Management** | `GET/POST/PUT/DELETE /api/v1/cameras` | `Cameras.jsx` | Done |
| **Live MJPEG Streaming** | `GET /api/v1/cameras/{id}/stream` | `CameraMonitor`, `Cameras.jsx` | Done |
| **RTSP Diagnostics** | `GET /api/v1/cameras/{id}/rtsp-test` | toast on stream error | Done |
| **Camera Health Check** | `GET /api/v1/cameras/{id}/health`, `POST /health-check-all` | `Cameras.jsx` | Done |
| **Employee Management** | `GET/POST/PUT/DELETE /api/v1/employees` | `Employees.jsx` | Done |
| **Employee Detail + Photos** | `GET /api/v1/employees/{id}`, photo upload/delete | `EmployeeDetail.jsx` | Done |
| **Face Enrollment** | `POST /api/v1/employees/{id}/enroll` | `EmployeeDetail.jsx` | Done |
| **Attendance** | `GET /api/v1/attendance` | `Attendance.jsx` | Done |
| **Alerts** | `GET /api/v1/alerts`, unread count, acknowledge | `Alerts.jsx` | Done |
| **Analytics** | `GET /api/v1/analytics` | `Analytics.jsx` | Done |
| **Vehicles / ANPR** | `GET /api/v1/vehicles` | `Vehicles.jsx` | Done |
| **Visitors** | `GET /api/v1/visitors` | `Visitors.jsx` | Done |
| **Floor Map / GIS** | `GET /api/v1/maps` | `FloorMap.jsx` | Done |
| **Reports** | `GET /api/v1/reports` | `Reports.jsx` | Done |
| **ERP Integration** | `GET/POST /api/v1/erp` | — | Backend done |
| **Notifications** | `GET /api/v1/notifications` | — | Backend done |
| **Sites** | `GET/POST /api/v1/sites` | — | Backend done |

---

## Key Dependencies

### Backend (`requirements.txt`)

| Package | Purpose |
|---|---|
| `fastapi 0.115` | Async REST API framework |
| `uvicorn[standard]` | ASGI server |
| `sqlalchemy 2.x` | ORM (async) |
| `alembic` | Database migrations |
| `asyncpg` / `psycopg2-binary` | PostgreSQL drivers |
| `redis` | Cache and session store |
| `celery` | Async task queue |
| `aio-pika` / `pika` | RabbitMQ client |
| `python-jose` | JWT authentication |
| `bcrypt` | Password hashing |
| `pydantic 2.x` | Schema validation |
| `reportlab` / `openpyxl` | PDF / Excel report generation |
| `prometheus-client` | Metrics exposure |
| `pillow` | Image processing |
| `qrcode` / `pyotp` | QR code and OTP support |

### Frontend

| Package | Purpose |
|---|---|
| `react 18` | UI framework |
| `react-router-dom` | Client-side routing |
| `axios` | HTTP client |
| `react-hot-toast` | Notification toasts |
| `react-icons` | Icon library (Remix Icons) |
| `recharts` | Charts and occupancy graphs |
| `date-fns` | Date formatting |

---

## Environment Variables

Create `evap/backend/.env` (copy from `.env.example`):

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/evap

# Redis
REDIS_URL=redis://localhost:6379/0

# RabbitMQ
RABBITMQ_URL=amqp://guest:guest@localhost:5672/

# Auth
SECRET_KEY=change-me-to-a-random-secret
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Snapshots / static files
SNAPSHOT_DIR=./snapshots

# Optional: S3 for video archive
# S3_BUCKET=evap-archive
# AWS_ACCESS_KEY_ID=...
# AWS_SECRET_ACCESS_KEY=...
```

---

## API Reference

Interactive docs are available at `http://localhost:8000/docs` once the backend is running.

Notable endpoints:

```
GET  /health                                      — service health
GET  /metrics                                     — Prometheus metrics

POST /api/v1/auth/login                           — obtain JWT token
GET  /api/v1/auth/me                              — current user

GET  /api/v1/cameras                              — list cameras (paginated)
POST /api/v1/cameras                              — register camera (RTSP URL encrypted at rest)
PUT  /api/v1/cameras/{id}                         — update camera / credentials
DELETE /api/v1/cameras/{id}                       — delete camera
GET  /api/v1/cameras/{id}/stream                  — live MJPEG proxy (RTSP → browser)
GET  /api/v1/cameras/{id}/health                  — TCP ping to port 554
GET  /api/v1/cameras/{id}/rtsp-test               — diagnostic: attempt RTSP open, return error details
POST /api/v1/cameras/{id}/restart                 — force stream reconnect
POST /api/v1/cameras/health-check-all             — ping all registered cameras

GET  /api/v1/employees                            — list employees
POST /api/v1/employees                            — create employee
GET  /api/v1/employees/{id}                       — get employee + photos
PUT  /api/v1/employees/{id}                       — update employee
POST /api/v1/employees/{id}/photos                — upload face photos (multipart)
DELETE /api/v1/employees/{id}/photos/{filename}   — delete face photo
POST /api/v1/employees/{id}/enroll                — trigger face enrollment
GET  /api/v1/employees/{id}/enrollment-status     — poll enrollment status

GET  /api/v1/alerts                               — list alerts (filterable)
GET  /api/v1/alerts/unread-count                  — badge count for navbar
GET  /api/v1/alerts/stats                         — severity / type breakdown
POST /api/v1/alerts/acknowledge-all               — bulk acknowledge
POST /api/v1/alerts/{id}/acknowledge              — acknowledge single alert

GET  /api/v1/attendance                           — list attendance records
GET  /api/v1/dashboard/stats                      — live KPIs (people, vehicles, alerts, cameras)
GET  /api/v1/dashboard/occupancy-history          — time-series occupancy for chart
GET  /api/v1/dashboard/recent-detections          — latest detection events
GET  /api/v1/analytics                            — analytics data

WS   /ws/{client_id}                             — per-client WebSocket (alerts, occupancy updates)
WS   /ws/live-tracking                            — live Phase 2 tracking broadcast (unauthenticated)
```

---

## WebSocket Events

Two WebSocket endpoints are available:

**Per-client channel** — `ws://localhost:8000/ws/{client_id}`  
The frontend generates a random `client_id` at login and reconnects automatically. The server pushes JSON events:

```json
{ "type": "alert",             "data": { "alert_id": 42, "severity": "critical" } }
{ "type": "occupancy_update",  "data": { "zone_id": "lobby", "count": 17 } }
{ "type": "attendance_event",  "data": { "employee_id": "EMP001", "action": "check_in" } }
{ "type": "camera_status",     "data": { "camera_id": 1, "status": "offline" } }
{ "type": "pong",              "client_id": "...", "echo": "..." }
```

**Live tracking broadcast** — `ws://localhost:8000/ws/live-tracking`  
Unauthenticated. Pushes Phase 2 detection stats every 2 seconds:

```json
{
  "type": "live_tracking",
  "people_present": 12,
  "vehicles_present": 3,
  "live_counts": { "person": 12, "car": 2, "motorcycle": 1 },
  "recent_crossings": [{ "track_id": 7, "class": "person", "direction": "in", "line": "Gate A" }]
}
```

> **Note:** The frontend uses the **native browser WebSocket API** — not Socket.IO. Connecting a Socket.IO client to these endpoints will fail with a 403 handshake error.

---

## Camera Streaming Notes

The backend proxies RTSP → MJPEG via OpenCV + FFmpeg. Key points:

- **RTSP URL format** — Passwords containing `@` must be percent-encoded: `nepal@123` → `nepal%40123`.  
  Full example: `rtsp://admin:nepal%40123@10.30.0.161:554/Streaming/Channels/102`
- **Hikvision paths** — channel 101 = H.265 main stream, channel 102 = H.265 sub-stream. Use `/Streaming/Channels/102` for lower bandwidth.
- **H.265 / HEVC** — The first 3–20 frames may fail while the decoder initialises VPS/SPS/PPS headers. The stream endpoint tolerates up to 20 consecutive decode failures before giving up.
- **Connection timeout** — Set via `OPENCV_FFMPEG_CAPTURE_OPTIONS=rtsp_transport;tcp|stimeout;5000000` (5 seconds). `CAP_PROP_OPEN_TIMEOUT_MSEC` is silently ignored by the FFmpeg backend on Windows.
- **Stream errors** — If the RTSP URL is wrong or the camera rejects the connection, the backend returns **HTTP 503** with a plain-English error. The camera card in the browser shows a toast popup with the `rtsp-test` diagnostic result.
- **RTSP credentials are encrypted at rest** — Fernet symmetric encryption via `SECRET_KEY`. The raw URL is never stored in the database.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `405 Method Not Allowed` on `/alerts/unread-count` | Stale `__pycache__` bytecode from old route ordering | Always start via `start_evap.bat` — it clears `__pycache__` first |
| Camera stream shows "Stream unavailable" | Wrong RTSP URL, wrong credentials, or firewall | Click Edit Camera → enter the full RTSP URL; watch backend terminal for `[STREAM] cam=N` log lines |
| `422 Unprocessable Entity` on photo upload | Multipart field name mismatch | Frontend sends `photos` field; backend expects `photos: List[UploadFile]` |
| WebSocket 403 | Connecting a Socket.IO client to a native FastAPI WebSocket | Use the browser native `WebSocket` API, not socket.io-client |
| `GET /dashboard/stats` 500 | Model attribute mismatch (e.g., `Camera.id` vs `camera_id`) | The field name in the SQLAlchemy model is `camera_id` — check dashboard.py imports |

---

## Hardware Requirements

| Tier | Cameras | CPU | RAM | GPU | Storage |
|---|---|---|---|---|---|
| **Dev / Pilot** | 1 – 20 | 8-core | 16 GB | GTX 1080 / RTX 3070 | 500 GB SSD |
| **Mid-range** | 21 – 100 | 32-core | 64 GB | NVIDIA A10 (24 GB VRAM) | 4 TB NVMe |
| **Enterprise** | 100+ | Kubernetes cluster | 128 GB per node | NVIDIA A100 80 GB | Distributed (Ceph) |

> CUDA 12.4+ and cuDNN 9.x required on GPU nodes. Ubuntu 22.04 LTS recommended for production.

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](../LICENSE) file for details.

---

## Contributing

1. Fork and create a feature branch: `git checkout -b feature/your-feature`.
2. Follow coding standards: Black + Ruff for Python, ESLint for JavaScript/JSX.
3. Write or update tests — minimum 80% coverage for new services.
4. Open a pull request against `main` with a description and linked issue.
5. All PRs require one approval and a passing CI run before merge.
