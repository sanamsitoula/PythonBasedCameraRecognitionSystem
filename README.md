# CCTV Analytics – Phase 1, 2 & 3

A complete video analytics system for RTSP cameras. Detects and tracks people and vehicles, classifies gender, counts entries and exits, recognises employees by face, manages attendance and visitors, and stores everything in PostgreSQL — all on a single Windows machine.

---

## Quick Navigation

| Section | Link |
|---------|------|
| Feature traceability (CLI → UI → API → DB) | [Section 14](#14-feature-traceability-cli--ui--api--db) |
| Running the full UI application | [Section 15](#15-running-the-full-ui-application) |
| Database setup | [Section 5](#5-database-setup) |
| Installation | [Section 4](#4-installation--step-by-step) |

---

## Table of Contents

1. [What the system does](#1-what-the-system-does)
2. [Folder structure](#2-folder-structure)
3. [Requirements](#3-requirements)
4. [Installation — step by step](#4-installation--step-by-step)
5. [Database setup](#5-database-setup)
6. [Configuration](#6-configuration)
7. [Running the system](#7-running-the-system)
8. [Reading the dashboard](#8-reading-the-dashboard)
9. [Where data is saved](#9-where-data-is-saved)
10. [Enrolling employees (Phase 3)](#10-enrolling-employees-phase-3)
11. [Running the tests](#11-running-the-tests)
12. [Troubleshooting](#12-troubleshooting)
13. [Flow diagram](#13-flow-diagram)

---

## 1. What the system does

### Phase 1 — Detection & monitoring
- Connects to an IP camera over RTSP.
- Detects people and vehicles in every frame using YOLOv11.
- Shows a live console dashboard with counts, system health, and camera status.
- Saves snapshot images on detection.
- Sends periodic scene summaries to an AI (Gemini / Claude / OpenRouter / DeepSeek).

### Phase 2 — Tracking & analytics
- Tracks each person and vehicle with a unique persistent ID (P-0001, V-0001).
- Classifies gender (Male / Female) once per person using DeepFace.
- Determines movement direction per track.
- Counts entries and exits through a configurable virtual line.
- Detects which named zone a person or vehicle is currently inside.
- Calculates live occupancy (current / peak / rolling average).
- Saves all events to PostgreSQL for reporting.

### Phase 3 — Face recognition & enterprise features
- Recognises named employees from enrolled face photos ("Alice entered at 09:02").
- Records attendance automatically — entry time, exit time, lateness.
- Manages visitors — logs first appearance, tracks movement, stores face snapshot.
- Canteen analytics — tracks meal-period visits per person.
- Department analytics — who is in the office / canteen / absent per department.
- Cross-camera re-identification — follows a person across multiple camera feeds.
- Smart alerts — restricted zone, after-hours, loitering, crowd threshold.
- Audit logging for all identity and attendance events.

---

## 2. Folder structure

```
cctv_phase1/
├── config/
│   ├── config.ini              ← All settings (camera, DB, zones, etc.)
│   └── config.ini.example      ← Safe template — copy this to create config.ini
│
├── sql/
│   ├── schema.sql              ← Phase 2 tables (run once)
│   └── schema_p3.sql           ← Phase 3 tables (run once after schema.sql)
│
├── models/
│   └── yolo11n.pt              ← YOLO model (auto-downloaded on first run)
│
├── snapshots/
│   ├── people/                 ← Cropped person images
│   ├── vehicles/               ← Cropped vehicle images
│   ├── entry/                  ← Frames at entry crossing
│   ├── exit/                   ← Frames at exit crossing
│   └── gender/                 ← Cropped images with gender label
│
├── logs/
│   ├── application.log
│   ├── camera.log
│   ├── tracking.log
│   ├── analytics.log
│   ├── database.log
│   ├── gender.log
│   ├── vehicle.log
│   ├── recognition.log         ← Phase 3: face recognition events
│   ├── attendance.log          ← Phase 3: clock-in / clock-out
│   ├── alerts.log              ← Phase 3: smart alert events
│   └── error.log
│
├── tests/
│   ├── unit/                   ← Fast tests, no camera or DB needed
│   └── integration/            ← Requires running PostgreSQL
│
├── main.py                     ← Phase 1 entry point
├── phase2_main.py              ← Phase 2 entry point
├── phase3_main.py              ← Phase 3 entry point  ← USE THIS
├── enrollment_cli.py           ← Enrol employee faces into DB
├── requirements.txt
├── INSTALLATION_GUIDE.md
└── TESTING_GUIDE.md
```

---

## 3. Requirements

### Hardware

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | Intel i5 (8th gen+) | Intel i7 / Ryzen 7 |
| RAM | 16 GB | 32 GB |
| GPU | None (CPU mode) | NVIDIA RTX 4060 (CUDA 12.x) |
| Storage | 20 GB free | 100 GB+ (snapshots + DB) |

### Software

- Windows 10 / 11 (64-bit) or Windows Server 2022
- Python 3.13
- FFmpeg (RTSP decoding)
- PostgreSQL 15
- An IP camera with RTSP support

---

## 4. Installation — step by step

### Step 1 — Install Python 3.13

Download from https://www.python.org/downloads/ — tick **"Add Python to PATH"** during setup.

Verify:
```
python --version
```

### Step 2 — Install FFmpeg

1. Download from https://www.gyan.dev/ffmpeg/builds/ → `ffmpeg-release-essentials.zip`
2. Extract to `C:\ffmpeg`
3. Add `C:\ffmpeg\bin` to your System PATH (Win + R → `sysdm.cpl` → Advanced → Environment Variables)

Verify:
```
ffmpeg -version
```

### Step 3 — Create virtual environment

```powershell
cd C:\Users\user\Downloads\cctv_phase1
python -m venv .venv
.\.venv\Scripts\activate
```

### Step 4 — Install Python packages

```powershell
pip install -r requirements.txt
```

#### CPU-only (no GPU)
```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

#### NVIDIA GPU (CUDA 12.x)
```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

Verify GPU:
```powershell
python -c "import torch; print(torch.cuda.is_available())"
```

### Step 5 — Install PostgreSQL 15

Download from https://www.postgresql.org/download/windows/ and install with defaults.
The installer sets a password for the `postgres` superuser — remember it.

---

## 5. Database setup

### Step 1 — Create user and database

Open pgAdmin or run these in psql as the `postgres` superuser:

```sql
CREATE ROLE cctv_user LOGIN PASSWORD 'YOUR_DB_PASSWORD';
CREATE DATABASE cctv_analytics OWNER cctv_user;

\c cctv_analytics

GRANT CONNECT ON DATABASE cctv_analytics TO cctv_user;
GRANT USAGE ON SCHEMA public TO cctv_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO cctv_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO cctv_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO cctv_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO cctv_user;
```

Or using the command line:
```powershell
$env:PGPASSWORD = "your_postgres_password"
& "C:\Program Files\PostgreSQL\15\bin\psql.exe" -h localhost -U postgres -c "CREATE ROLE cctv_user LOGIN PASSWORD 'YOUR_DB_PASSWORD';"
& "C:\Program Files\PostgreSQL\15\bin\psql.exe" -h localhost -U postgres -c "CREATE DATABASE cctv_analytics OWNER cctv_user;"
```

### Step 2 — Run schema migrations

Run all three migration files in order:

```powershell
$env:PGPASSWORD = "YOUR_DB_PASSWORD"
$psql = "C:\Program Files\PostgreSQL\15\bin\psql.exe"

# Phase 2 — 11 tables
& $psql -h localhost -U cctv_user -d cctv_analytics -f sql\schema.sql

# Phase 3 — 14 additional tables
& $psql -h localhost -U cctv_user -d cctv_analytics -f sql\schema_p3.sql

# EVAP web platform — extends existing tables + adds 29 new tables
& $psql -h localhost -U cctv_user -d cctv_analytics -f sql\005_evap_web_tables.sql
```

All scripts use `CREATE TABLE IF NOT EXISTS` / `ALTER TABLE … ADD COLUMN IF NOT EXISTS` — safe to re-run, will never delete data.

### Step 3 — Verify (54 tables total)

```powershell
& $psql -h localhost -U cctv_user -d cctv_analytics -c "\dt"
```

Expected tables:

| Phase 2 (11) | Phase 3 (14) | EVAP Web (29) |
|---|---|---|
| cameras | employee_master | roles |
| sessions | employee_face_master | users |
| tracked_objects | face_embeddings | api_keys |
| gender_classifications | recognized_persons | site_master |
| direction_events | visitor_master | building_master |
| line_crossings | visitor_tracking | floor_master |
| zone_events | attendance_log | zone_master |
| occupancy_snapshots | employee_zone_history | camera_master |
| vehicle_counts | canteen_visits | camera_streams |
| error_events | movement_history | face_master |
| system_health_snapshots | department_analytics | alert_log |
| | cross_camera_tracking | notification_log |
| | smart_alerts | watchlist |
| | audit_log | occupancy_log |
| | | zone_history |
| | | analytics_daily |
| | | analytics_monthly |
| | | behavior_events |
| | | system_health |
| | | api_log |
| | | evap_audit_log |
| | | erp_sync_log |
| | | reports |
| | | vehicle_master |
| | | license_plate_log |
| | | detections |
| | | heatmap_data |
| | | notification_settings |
| | | erp_config |

### DB credentials (current setup)

| Setting | Value |
|---------|-------|
| Host | localhost |
| Port | 5432 |
| Database | cctv_analytics |
| User | cctv_user |
| Password | *(set in `evap/backend/.env` — not committed to git)* |

> Real credentials live in `evap/backend/.env` (gitignored). Copy `evap/backend/.env.example` and fill in your values.

### Unified database architecture

All three layers — CCTV engine, FastAPI backend, and React frontend — share one database: **`cctv_analytics`**.

```
cctv_analytics (PostgreSQL 15)
├── Phase 2 tables (schema.sql)          — cameras, sessions, tracking, occupancy …
├── Phase 3 tables (schema_p3.sql)       — employees, visitors, attendance, alerts …
└── EVAP tables (005_evap_web_tables.sql)
    ├── Extended columns on Phase 3 tables (email, phone, is_active …)
    └── New EVAP-only tables             — users, roles, site/floor/zone/camera hierarchy,
                                           alert_log, analytics, vehicle_master …
```

There is **no separate EVAP database**. The `evap/backend/.env` file points to `cctv_analytics`:
```
DATABASE_URL=postgresql+asyncpg://cctv_user:YOUR_PASSWORD_URL_ENCODED@localhost:5432/cctv_analytics
```

---

## 6. Configuration

Copy the example and edit your settings:

```powershell
Copy-Item config\config.ini.example config\config.ini
```

Key sections in `config/config.ini`:

### Camera
```ini
[CAMERA]
ip       = 10.30.0.161
username = admin
password = nepal@123
rtsp_url = rtsp://admin:nepal@123@10.30.0.161:554/cam/realmonitor?channel=1&subtype=0
```

### Database
```ini
[DATABASE]
enabled  = true
host     = localhost
port     = 5432
dbname   = cctv_analytics
user     = cctv_user
password = YOUR_DB_PASSWORD
```

### Virtual counting line
```ini
[LINE_COUNTER]
line_1           = 0,180 640,180
line_1_label     = MainEntrance
line_1_entry_direction = TOP_TO_BOTTOM
```

### Zones
```ini
[ZONES]
zone_1       = 0,0 320,0 320,360 0,360
zone_1_label = Zone A
zone_2       = 320,0 640,0 640,360 320,360
zone_2_label = Zone B
```

### AI providers (optional — any one key is enough)
```ini
[AI]
enabled           = true
gemini_api_key    = YOUR_GEMINI_KEY
anthropic_api_key = YOUR_CLAUDE_KEY
openrouter_api_key = YOUR_OPENROUTER_KEY
deepseek_api_key  = YOUR_DEEPSEEK_KEY
```

---

## 7. Running the system

Always activate the virtual environment first:

```powershell
.\.venv\Scripts\activate
```

### Phase 3 — full feature set (recommended)
```powershell
python phase3_main.py
```

### Phase 2 — tracking + gender + DB (no face recognition)
```powershell
python phase2_main.py
```

### Phase 1 — detection only
```powershell
python main.py
```

Press **Ctrl + C** to stop. The system drains pending DB writes and shuts down cleanly.

---

## 8. Reading the dashboard

### Phase 3 dashboard panels

```
┌──────────────────────┬────────────────────────┬──────────────────────┐
│ CAMERAS              │ ATTENDANCE TODAY        │ SYSTEM HEALTH        │
│ 10.30.0.161 OK       │ Present: 12             │ CPU: 38% ████░░      │
│ 640×360 @ 20 FPS     │ Late: 2                 │ RAM: 6.1 GB          │
│                      │ Absent: 3               │ Device: CPU          │
├──────────────────────┼────────────────────────┼──────────────────────┤
│ ACTIVE EMPLOYEES     │ ACTIVE VISITORS         │ AI ANALYSIS          │
│ EMP-001 Alice  LobbyA│ VIS-0001  Zone B        │ Normal foot traffic, │
│ EMP-002 Bob    Zone B│ VIS-0002  Canteen        │ 2 employees in lobby │
│                      │                         │ 14:25 [gemini]       │
├──────────────────────┼────────────────────────┼──────────────────────┤
│ DEPARTMENTS          │ CANTEEN                 │ RECENT ALERTS        │
│ Engineering  8/10    │ Current: 4              │ [WARN] Loitering...  │
│ HR           3/5     │ Today:  23 visits       │ [INFO] Entry: Alice  │
└──────────────────────┴────────────────────────┴──────────────────────┘
┌──────────────────────────────────────────────────────────────────────┐
│ RECENT EVENTS                                                        │
│ [14:25:10] ENTRY: EMP-001 Alice (Engineering)                       │
│ [14:24:55] VISITOR: VIS-0002 entered Zone B                         │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 9. Where data is saved

### Database tables

| Table | What it stores |
|-------|----------------|
| `cameras` | Camera details |
| `sessions` | One row per system run |
| `tracked_objects` | Position of every track, every 5 frames |
| `gender_classifications` | Gender result per track |
| `direction_events` | Movement direction per track |
| `line_crossings` | Every entry / exit event |
| `zone_events` | Every zone entry and exit |
| `occupancy_snapshots` | Occupancy numbers every 60 s |
| `vehicle_counts` | Vehicle counts per hour |
| `error_events` | Errors with tracebacks |
| `system_health_snapshots` | CPU / RAM / FPS every 30 s |
| `employee_master` | Employee name, department, designation |
| `employee_face_master` | Enrollment metadata |
| `face_embeddings` | Stored face vectors for recognition |
| `recognized_persons` | Every recognition event |
| `visitor_master` | Visitor profile (first seen, snapshot) |
| `visitor_tracking` | Visitor location history |
| `attendance_log` | Daily attendance per employee |
| `employee_zone_history` | Zone visit history per employee |
| `canteen_visits` | Canteen entry / exit per person |
| `movement_history` | Full cross-zone movement log |
| `department_analytics` | Periodic headcount snapshot per department |
| `cross_camera_tracking` | Same person tracked across cameras |
| `smart_alerts` | All fired security alerts |
| `audit_log` | Immutable event audit trail |

### Snapshot folders

| Folder | Content |
|--------|---------|
| `snapshots/people/` | Cropped person image per track |
| `snapshots/vehicles/` | Cropped vehicle image per track |
| `snapshots/entry/` | Full frame at entry crossing |
| `snapshots/exit/` | Full frame at exit crossing |
| `snapshots/gender/` | Person crop with gender label |

### Log files (`logs/`)

| File | Content |
|------|---------|
| `application.log` | All system events |
| `camera.log` | Connection / reconnection events |
| `tracking.log` | Track open / close |
| `analytics.log` | Entry / exit / zone transitions |
| `database.log` | DB write activity |
| `gender.log` | Classification results |
| `vehicle.log` | Vehicle events |
| `recognition.log` | Face recognition results |
| `attendance.log` | Clock-in / clock-out records |
| `alerts.log` | Fired smart alerts |
| `error.log` | Warnings and errors |

---

## 10. Enrolling employees (Phase 3)

Before face recognition works, you must enrol each employee's face photos.

### Using the CLI

```powershell
.\.venv\Scripts\activate
python enrollment_cli.py
```

The CLI will prompt you for:
- Employee ID (e.g. `EMP-001`)
- Employee name
- Department
- Designation
- Path to a folder of face photos (JPEG / PNG, front-facing, clear lighting)

At least 3–5 photos per person improve accuracy. The face embeddings are stored in the `face_embeddings` table and loaded into memory at startup.

### After enrolment

Restart `phase3_main.py`. It loads all embeddings from the DB at startup (step 19 in the boot sequence).

---

## 11. Running the tests

Unit tests (no camera / DB / GPU needed):
```powershell
.\.venv\Scripts\activate
pytest tests/unit/ -v
```

Integration tests (requires PostgreSQL running with `cctv_analytics` DB):
```powershell
$env:CCTV_TEST_PASSWORD = "YOUR_DB_PASSWORD"
pytest tests/integration/ -v
```

Run everything:
```powershell
pytest tests/ -v
```

---

## 12. Troubleshooting

### Camera verification failed
- Confirm the RTSP URL works in VLC (Media → Open Network Stream).
- Check camera IP, username, and password in `config.ini`.
- Ping the camera: `ping 10.30.0.161`.

### YOLO model not found
- Run: `python -c "from ultralytics import YOLO; YOLO('yolo11n.pt')"` then move the downloaded `.pt` file to `models/`.

### Database connection failed
- Check PostgreSQL is running: Win + R → `services.msc` → find `postgresql-x64-15`.
- Test connection: `psql -h localhost -U cctv_user -d cctv_analytics`
- Verify credentials in `config.ini` match what was set during DB creation.

### Face recognition not working
- Ensure employees are enrolled via `enrollment_cli.py`.
- Check `recognition.log` for error details.
- `min_confidence` in `[FACE_RECOGNITION]` controls sensitivity (lower = more matches but less accurate).

### Gender classification slow
- Increase `max_workers` in `[GENDER]` section.
- Switch to InsightFace backend (`backend = insightface`) — faster but requires an ONNX model download.

### High CPU usage
- Use sub-stream RTSP URL (`subtype=1` instead of `subtype=0`) for lower resolution.
- Install GPU support (CUDA torch packages).
- Set `device = cpu` in `[YOLO]` if GPU detection is failing.

### Dashboard looks garbled
- Use **Windows Terminal** or PowerShell — avoid legacy `cmd.exe`.
- Set terminal font to Consolas 12pt or any Nerd Font.

---

## 13. Flow diagram

```
START
  │
  ├─ Load config.ini
  ├─ Verify camera (pre-flight)
  ├─ Load ByteTrack + YOLO model
  ├─ Connect to PostgreSQL (if enabled)
  ├─ Load face embeddings from DB
  ├─ Start RTSP capture
  ├─ Start dashboard
  │
  └─ MAIN LOOP ─────────────────────────────────────────────────────┐
       │                                                             │
       ├─ Read video frame from camera                               │
       ├─ ByteTrack → tracked persons + vehicles                    │
       │                                                             │
       ├─ For each PERSON:                                            │
       │   ├─ Gender classification (cached per track)              │
       │   ├─ Face recognition → employee or visitor                │
       │   │   ├─ Employee → record attendance / canteen / dept     │
       │   │   └─ Visitor  → create/update visitor record           │
       │   ├─ Direction detection                                    │
       │   ├─ Line crossing → occupancy IN/OUT                      │
       │   ├─ Zone detection → zone enter/exit events               │
       │   └─ Smart alerts (restricted zone, after-hours, loitering)│
       │                                                             │
       ├─ For each VEHICLE:                                           │
       │   ├─ Direction detection                                    │
       │   └─ Per-type count update                                  │
       │                                                             │
       ├─ Every 60 s → occupancy snapshot to DB                     │
       ├─ Every 30 s → system health snapshot to DB                 │
       ├─ Every 30 s → AI scene analysis                            │
       │                                                             │
       ├─ Update Phase 3 dashboard                                   │
       └─ Repeat ────────────────────────────────────────────────────┘
  │
  ├─ Ctrl+C
  ├─ Drain DB write queue
  ├─ Close DB session
  └─ STOP
```

---

*Built on: Python 3.13 · YOLOv11 (ultralytics) · ByteTrack · DeepFace · InsightFace · Rich · psycopg2 · PostgreSQL 15*

---

## 14. Feature Traceability — CLI → UI → API → DB

This section maps every panel in `phase3_dashboard.py` (the terminal CLI dashboard) to its equivalent Web UI page, REST API endpoint, and PostgreSQL table so you can trace any feature end-to-end.

### Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Fully implemented |
| ⚠️ | Partially implemented / mock data only |
| ❌ | Not yet implemented |

---

### 14.1 SYSTEM STATUS panel — `_system_panel()`

**What the CLI shows:** Camera IP · connection status · live FPS · frame counter · uptime · RAM · CPU % · DB online/offline · error count

| Layer | Location | Detail | Status |
|-------|----------|--------|--------|
| **CLI function** | `phase3_dashboard.py` → `_system_panel()` | Reads `phase3_state.Phase3State` fields: `actual_fps`, `frame_number`, `cpu_pct`, `ram_gb`, `db_available`, `error_count`, camera list via `set_cameras()` | — |
| **UI page** | `evap/frontend/src/pages/Dashboard.jsx` | `getMockCameras()` — currently **mock data**; `system_health` card renders CPU/RAM | ⚠️ |
| **UI component** | `evap/frontend/src/components/Dashboard/StatsCard.jsx` | Health stats card | ⚠️ |
| **API endpoint** | `GET /api/v1/dashboard/system-health` | Returns CPU %, RAM, FPS, uptime | ✅ |
| **API endpoint** | `GET /api/v1/dashboard/cameras-status` | Returns per-camera IP, status, FPS | ✅ |
| **DB tables** | `cctv_analytics.system_health_snapshots` | CPU, RAM, FPS written every 30 s by `db_writer.py` | ✅ |
| **DB tables** | `cctv_analytics.cameras`, `cctv_analytics.sessions` | Camera and session records | ✅ |

> **Gap:** Dashboard.jsx still calls `getMockCameras()`. Wire `GET /api/v1/dashboard/cameras-status` to replace mock.

---

### 14.2 PEOPLE OVERVIEW panel — `_people_panel()`

**What the CLI shows:** Live employee count · visitor count · male/female split for each · total occupancy

| Layer | Location | Detail | Status |
|-------|----------|--------|--------|
| **CLI function** | `phase3_dashboard.py` → `_people_panel()` | Reads `employees_present`, `visitors_present`, `male_employees`, `female_employees`, `male_visitors`, `female_visitors` from `phase3_state` | — |
| **UI page** | `evap/frontend/src/pages/Dashboard.jsx` | `getMockStats()` — currently **mock data** for people count | ⚠️ |
| **UI component** | `evap/frontend/src/components/Dashboard/StatsCard.jsx` | Occupancy / people count cards | ⚠️ |
| **API endpoint** | `GET /api/v1/dashboard/stats` | Returns live employee count, visitor count, gender breakdown, total occupancy | ✅ |
| **API endpoint** | `GET /api/v1/analytics/occupancy` | Time-series occupancy data | ✅ |
| **DB tables** | `cctv_analytics.occupancy_snapshots` | Occupancy written every 60 s | ✅ |
| **DB tables** | `cctv_analytics.recognized_persons` | Source of employee vs visitor split | ✅ |
| **DB tables** | `cctv_analytics.gender_classifications` | Male/female counts | ✅ |

> **Gap:** Dashboard.jsx uses `getMockStats()`. Replace with `GET /api/v1/dashboard/stats`.

---

### 14.3 ATTENDANCE TODAY panel — `_attendance_panel()`

**What the CLI shows:** Present count · Late count · Absent count · progress bars per category

| Layer | Location | Detail | Status |
|-------|----------|--------|--------|
| **CLI function** | `phase3_dashboard.py` → `_attendance_panel()` | Reads `present_today`, `late_today`, `absent_today` from `phase3_state` | — |
| **UI page** | `evap/frontend/src/pages/Attendance.jsx` | `load()` fetches real data; `SummaryCard` shows Present/Late/Absent | ✅ |
| **UI component** | `evap/frontend/src/components/Dashboard/StatsCard.jsx` | Summary cards on dashboard | ⚠️ (mock on dashboard) |
| **API endpoint** | `GET /api/v1/attendance/today` | Returns today's present / late / absent counts | ✅ |
| **API endpoint** | `GET /api/v1/attendance` | Full attendance log with filters | ✅ |
| **API endpoint** | `GET /api/v1/attendance/monthly-report` | Monthly attendance export | ✅ |
| **API endpoint** | `GET /api/v1/attendance/exceptions` | Late arrivals and absences | ✅ |
| **API endpoint** | `POST /api/v1/attendance/manual-correction` | HR manual override | ✅ |
| **DB table** | `cctv_analytics.attendance_log` | `employee_id`, `attendance_date`, `first_entry`, `last_exit`, `status`, `is_late` | ✅ |

---

### 14.4 ACTIVE EMPLOYEES panel — `_active_employees_panel()`

**What the CLI shows:** Table of currently-visible employees — EMP_ID · Name · Department · Zone · Entry time (up to 8 rows)

| Layer | Location | Detail | Status |
|-------|----------|--------|--------|
| **CLI function** | `phase3_dashboard.py` → `_active_employees_panel()` | Reads `active_employees` list of `EmployeeSummary` objects from `phase3_state` | — |
| **UI page** | `evap/frontend/src/pages/Employees.jsx` | `load()` calls API; lists all employees with CRUD + face enrol | ✅ |
| **API endpoint** | `GET /api/v1/employees` | Paginated employee list | ✅ |
| **API endpoint** | `GET /api/v1/employees/search` | Search by name / dept | ✅ |
| **API endpoint** | `GET /api/v1/employees/{id}` | Single employee detail | ✅ |
| **API endpoint** | `GET /api/v1/employees/{id}/movement` | Live zone / movement history | ✅ |
| **API endpoint** | `GET /api/v1/employees/{id}/zone-history` | Historical zone dwell times | ✅ |
| **API endpoint** | `POST /api/v1/employees/{id}/enroll-face` | Upload face photos for recognition | ✅ |
| **API endpoint** | `PUT /api/v1/employees/{id}` | Update employee record | ✅ |
| **API endpoint** | `DELETE /api/v1/employees/{id}` | Deactivate employee | ✅ |
| **DB tables** | `cctv_analytics.employee_master` | Name, dept, designation, status | ✅ |
| **DB tables** | `cctv_analytics.employee_zone_history` | Per-employee zone visits | ✅ |
| **DB tables** | `cctv_analytics.face_embeddings` | Face vectors for recognition | ✅ |
| **DB tables** | `cctv_analytics.recognized_persons` | Recognition events per frame | ✅ |

> **Gap:** Employees.jsx shows full employee list but **not live/active-right-now** view. A real-time "who is on camera now" widget is missing in the UI.

---

### 14.5 ACTIVE VISITORS panel — `_active_visitors_panel()`

**What the CLI shows:** Table of current visitors — Visitor-ID · Zone · First Seen · Duration (up to 6 rows)

| Layer | Location | Detail | Status |
|-------|----------|--------|--------|
| **CLI function** | `phase3_dashboard.py` → `_active_visitors_panel()` | Reads `active_visitors` list of `VisitorSummaryP3` from `phase3_state` | — |
| **UI page** | `evap/frontend/src/pages/Visitors.jsx` | `load()` + `active_visitors` endpoint; shows visitor list, detail modal, watchlist | ✅ |
| **API endpoint** | `GET /api/v1/visitors/active` | Currently-present visitors | ✅ |
| **API endpoint** | `GET /api/v1/visitors` | Full visitor log | ✅ |
| **API endpoint** | `GET /api/v1/visitors/{id}` | Visitor profile + snapshot | ✅ |
| **API endpoint** | `GET /api/v1/visitors/{id}/journey` | Zone-by-zone movement journey | ✅ |
| **API endpoint** | `POST /api/v1/visitors/{id}/watchlist` | Flag visitor on watchlist | ✅ |
| **DB tables** | `cctv_analytics.visitor_master` | Visitor ID, first/last seen, snapshot path | ✅ |
| **DB tables** | `cctv_analytics.visitor_tracking` | Per-visitor zone entry/exit | ✅ |
| **DB tables** | `cctv_analytics.movement_history` | Full cross-zone movement log | ✅ |

---

### 14.6 CANTEEN panel — `_canteen_panel()`

**What the CLI shows:** Current occupancy in the canteen zone · total visits today

| Layer | Location | Detail | Status |
|-------|----------|--------|--------|
| **CLI function** | `phase3_dashboard.py` → `_canteen_panel()` | Reads `canteen_current`, `canteen_today_visits` from `phase3_state` | — |
| **UI page** | — | **No canteen page exists in UI** | ❌ |
| **UI component** | — | **No canteen widget on Dashboard** | ❌ |
| **API endpoint** | — | **No `/api/v1/canteen` endpoint exists** | ❌ |
| **DB table** | `cctv_analytics.canteen_visits` | `person_id`, `person_type`, `entry_time`, `exit_time`, `meal_period`, `visit_date` — table exists, written by `phase3_main.py` | ✅ |

> **Action required:** Create `GET /api/v1/canteen/stats` API endpoint and a Canteen widget in Dashboard.jsx to surface canteen data from the DB.

---

### 14.7 DEPARTMENT STATUS panel — `_department_panel()`

**What the CLI shows:** Department · Present count · In Office · In Canteen (up to 8 departments)

| Layer | Location | Detail | Status |
|-------|----------|--------|--------|
| **CLI function** | `phase3_dashboard.py` → `_department_panel()` | Reads `department_summaries` list of `DeptSummaryEntry` from `phase3_state` | — |
| **UI page** | `evap/frontend/src/pages/Dashboard.jsx` | `generateMockDept()` — **mock data only** | ⚠️ |
| **API endpoint** | `GET /api/v1/analytics/daily` | Includes department breakdown | ⚠️ |
| **API endpoint** | `GET /api/v1/attendance/department/{dept_id}` | Per-department attendance | ✅ |
| **DB table** | `cctv_analytics.department_analytics` | `department`, `snapshot_time`, `employees_present`, `in_office`, `in_canteen` | ✅ |

> **Gap:** No dedicated `GET /api/v1/analytics/departments` endpoint. Dashboard.jsx still uses `generateMockDept()`.

---

### 14.8 SMART ALERTS panel — `_alerts_panel()`

**What the CLI shows:** Last 5 alerts with severity colour · timestamp · message (restricted zone / after-hours / loitering / crowd)

| Layer | Location | Detail | Status |
|-------|----------|--------|--------|
| **CLI function** | `phase3_dashboard.py` → `_alerts_panel()` | Reads `recent_alerts` from `phase3_state`; parses `Alert` objects or plain strings | — |
| **UI page** | `evap/frontend/src/pages/Alerts.jsx` | `load()`, `acknowledge()`, `acknowledgeAll()` — fully wired to API | ✅ |
| **UI component** | `evap/frontend/src/components/Dashboard/AlertsPanel.jsx` | Mini alerts panel on dashboard | ✅ |
| **API endpoint** | `GET /api/v1/alerts` | Full alert list with filters | ✅ |
| **API endpoint** | `GET /api/v1/alerts/active` | Unacknowledged alerts only | ✅ |
| **API endpoint** | `GET /api/v1/alerts/stats` | Counts by severity/type | ✅ |
| **API endpoint** | `GET /api/v1/dashboard/recent-alerts` | Last N alerts for dashboard widget | ✅ |
| **API endpoint** | `PUT /api/v1/alerts/{id}/acknowledge` | Mark alert as acknowledged | ✅ |
| **API endpoint** | `DELETE /api/v1/alerts/{id}` | Delete alert | ✅ |
| **API endpoint** | `POST /api/v1/alerts/rules` | Create alert rule | ✅ |
| **API endpoint** | `GET /api/v1/alerts/rules` | List alert rules | ✅ |
| **DB table** | `cctv_analytics.smart_alerts` | `alert_type`, `person_id`, `camera_id`, `zone_id`, `severity`, `message`, `acknowledged` | ✅ |

---

### 14.9 AI ANALYSIS panel — `_ai_panel()`

**What the CLI shows:** One-sentence AI scene description · provider name · timestamp of last analysis

| Layer | Location | Detail | Status |
|-------|----------|--------|--------|
| **CLI function** | `phase3_dashboard.py` → `_ai_panel()` | Reads `ai_text`, `ai_timestamp` from `phase3_state`; populated by `AiAnalyst` thread | — |
| **UI page** | `evap/frontend/src/pages/Dashboard.jsx` | AI text shown as a mock static string | ⚠️ |
| **API endpoint** | `GET /api/v1/dashboard/stats` | Includes latest AI insight in response | ⚠️ |
| **DB table** | — | AI insights are **not persisted** — in-memory only in `AiAnalyst` | ❌ |

> **Gap:** AI analysis text is never written to the database. Consider adding an `ai_insights` table and persisting each cycle's result. The UI should poll `GET /api/v1/dashboard/stats` instead of showing a mock string.

---

### 14.10 MOVEMENT LOG panel — `_log_panel()`

**What the CLI shows:** Last 8 movement events (line-IN / line-OUT / ENTRY / EXIT) as plain text strings

| Layer | Location | Detail | Status |
|-------|----------|--------|--------|
| **CLI function** | `phase3_dashboard.py` → `_log_panel()` | Reads `log_tail` deque from `phase3_state` (max 200 entries) | — |
| **UI page** | — | **No dedicated movement log page in UI** | ❌ |
| **UI component** | — | No live event feed component exists | ❌ |
| **API endpoint** | `GET /api/v1/employees/{id}/movement` | Movement for one employee | ⚠️ |
| **API endpoint** | `GET /api/v1/analytics/cross-camera` | Cross-camera journey | ✅ |
| **DB tables** | `cctv_analytics.movement_history` | Full cross-zone movement log | ✅ |
| **DB tables** | `cctv_analytics.line_crossings` | Entry/exit line-crossing events | ✅ |
| **DB tables** | `cctv_analytics.zone_events` | Zone enter/exit events | ✅ |

> **Action required:** Add a live event feed WebSocket endpoint (`WS /api/v1/dashboard/realtime` already exists in dashboard.py) and a real-time event ticker component in Dashboard.jsx.

---

### 14.11 CAMERA LIST — `set_cameras()` / `print_preflight_p3()`

**What the CLI shows:** Pre-flight verification table at startup; live camera IP · status · FPS in the System Status panel

| Layer | Location | Detail | Status |
|-------|----------|--------|--------|
| **CLI function** | `phase3_dashboard.py` → `set_cameras()`, `print_preflight_p3()` | Startup-only; sets `_CAMERAS` module variable | — |
| **UI page** | `evap/frontend/src/pages/Cameras.jsx` | `load()`, `handleSave()`, `handleDelete()`, `handleRestart()` — full CRUD | ✅ |
| **API endpoint** | `GET /api/v1/cameras` | Camera list | ✅ |
| **API endpoint** | `GET /api/v1/dashboard/cameras-status` | Live camera health per camera | ✅ |
| **DB table** | `cctv_analytics.camera_master` | EVAP structured camera registry (added by 005_evap_web_tables.sql) | ✅ |
| **DB table** | `cctv_analytics.cameras` | Camera record written by phase3_main.py | ✅ |

---

### 14.12 Summary — Implementation Status

| CLI Panel | UI Page | UI Status | API Status | DB Status |
|-----------|---------|-----------|------------|-----------|
| SYSTEM STATUS | Dashboard.jsx | ⚠️ Mock data | ✅ `/dashboard/system-health` | ✅ `system_health_snapshots` |
| PEOPLE OVERVIEW | Dashboard.jsx | ⚠️ Mock data | ✅ `/dashboard/stats` | ✅ `occupancy_snapshots` |
| ATTENDANCE TODAY | Attendance.jsx | ✅ Live data | ✅ `/attendance/today` | ✅ `attendance_log` |
| ACTIVE EMPLOYEES | Employees.jsx | ⚠️ List only, no live zone | ✅ `/employees` + `/movement` | ✅ `employee_master` |
| ACTIVE VISITORS | Visitors.jsx | ✅ Live data | ✅ `/visitors/active` | ✅ `visitor_master` |
| CANTEEN | — | ❌ Missing | ❌ Missing | ✅ `canteen_visits` |
| DEPARTMENT STATUS | Dashboard.jsx | ⚠️ Mock data | ⚠️ Partial via `/attendance/department` | ✅ `department_analytics` |
| SMART ALERTS | Alerts.jsx | ✅ Live data | ✅ `/alerts` + `/alerts/active` | ✅ `smart_alerts` |
| AI ANALYSIS | Dashboard.jsx | ⚠️ Mock string | ⚠️ In `/dashboard/stats` | ❌ Not persisted |
| MOVEMENT LOG | — | ❌ Missing | ⚠️ Partial via `/employees/{id}/movement` | ✅ `movement_history` |
| CAMERA STATUS | Cameras.jsx | ✅ Live data | ✅ `/cameras` + `/cameras-status` | ✅ `cameras` |

---

### 14.13 Data Flow Architecture

```
CAMERA (RTSP)
    │
    ▼
phase3_main.py  ──writes──►  cctv_analytics (PostgreSQL)
    │                              │
    │ updates                      │ reads
    ▼                              ▼
phase3_state.py           evap/backend (FastAPI)
    │                        /api/v1/*
    │ renders                      │
    ▼                              │ serves
phase3_dashboard.py (CLI)          ▼
  Terminal Rich UI          evap/frontend (React)
                              http://localhost:3000
```

**Two separate UIs exist for the same data:**
- `phase3_dashboard.py` — terminal CLI, reads `phase3_state` in real-time (zero latency)
- `evap/frontend` — web browser UI, reads `cctv_analytics` via FastAPI REST API

---

## 15. Running the Full UI Application

The web UI requires three services running simultaneously: **PostgreSQL** (already set up), **FastAPI backend**, and **React frontend**.

### Step 1 — Run the EVAP migration against cctv_analytics (run once)

The EVAP web platform uses the **same** `cctv_analytics` database as the CCTV engine.
`sql/005_evap_web_tables.sql` extends existing Phase 3 tables and adds 29 new EVAP-specific tables.

```powershell
$env:PGPASSWORD = "YOUR_DB_PASSWORD"
$psql = "C:\Program Files\PostgreSQL\15\bin\psql.exe"

# Extend cctv_analytics with EVAP tables (idempotent — safe to re-run)
& $psql -h localhost -U cctv_user -d cctv_analytics -f sql\005_evap_web_tables.sql
```

This script:
- Adds EVAP extension columns to `employee_master`, `visitor_master`, `attendance_log`, etc.
- Creates 29 new tables (auth, site hierarchy, camera registry, alerts, analytics, …)
- Seeds the default `admin` role and `admin` user (password: `admin123` — **change it after first login**)
- Creates all necessary indexes

> **Note:** If you already ran the full schema from Section 5 Step 2 (which includes `005_evap_web_tables.sql`),
> you can skip this step.

### Step 2 — Start the FastAPI backend

Open a **new PowerShell window** in `c:\Users\user\Downloads\cctv_phase1`:

```powershell
$env:PYTHONPATH = "c:\Users\user\Downloads\cctv_phase1\evap\backend"
& "c:\Users\user\Downloads\cctv_phase1\.venv\Scripts\uvicorn.exe" `
    app.main:app `
    --host 0.0.0.0 `
    --port 8000 `
    --reload `
    --app-dir "c:\Users\user\Downloads\cctv_phase1\evap\backend"
```

Verify it's running:
- Swagger UI → http://localhost:8000/docs
- Health check → http://localhost:8000/health
- ReDoc → http://localhost:8000/redoc

### Step 3 — Start the React frontend

Open another **new PowerShell window**:

```powershell
cd "c:\Users\user\Downloads\cctv_phase1\evap\frontend"
npm start
```

The browser will open automatically at **http://localhost:3000**

### Step 4 — (Optional) Run the CCTV analytics engine simultaneously

In a **third PowerShell window** (for live data):

```powershell
cd "c:\Users\user\Downloads\cctv_phase1"
.\.venv\Scripts\python.exe phase3_main.py
```

This writes live data into `cctv_analytics` which the API serves to the frontend.

### All services at a glance

| Service | Command | URL |
|---------|---------|-----|
| FastAPI backend | `uvicorn app.main:app --port 8000` | http://localhost:8000/docs |
| React frontend | `npm start` (in evap/frontend) | http://localhost:3000 |
| CCTV analytics engine | `python phase3_main.py` | Terminal dashboard |
| pgAdmin (DB GUI) | Open pgAdmin app | localhost:5050 |

### Default login (after seed data runs)

| Field | Value |
|-------|-------|
| Username | `admin` |
| Password | `admin123` |

> Change these immediately after first login via the Settings page.

---

*Built on: Python 3.13 · YOLOv11 (ultralytics) · ByteTrack · DeepFace · InsightFace · Rich · psycopg2 · PostgreSQL 15 · FastAPI · React 18 · Bootstrap 5*
