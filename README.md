# CCTV Analytics – Phase 1 & Phase 2

A complete video analytics system for RTSP cameras. It detects and tracks
people and vehicles, classifies gender, counts entries and exits, monitors
zones, and stores everything in a database — all running on a single Windows
machine with a standard i7 CPU or an RTX 4060 GPU.

---

## Table of Contents

1. [What the system does](#1-what-the-system-does)
2. [Folder structure](#2-folder-structure)
3. [How every file fits together](#3-how-every-file-fits-together)
4. [Requirements](#4-requirements)
5. [Installation — step by step](#5-installation--step-by-step)
6. [Configuration — step by step](#6-configuration--step-by-step)
7. [Running the system](#7-running-the-system)
8. [Reading the dashboard](#8-reading-the-dashboard)
9. [Where data is saved](#9-where-data-is-saved)
10. [Setting up the database](#10-setting-up-the-database)
11. [Running the tests](#11-running-the-tests)
12. [Troubleshooting](#12-troubleshooting)
13. [Flow diagram](#13-flow-diagram)

---

## 1. What the system does

**Phase 1** (already built)

- Connects to an IP camera over RTSP (the standard video streaming protocol
  used by almost every security camera brand).
- Detects people and vehicles in every frame using YOLO, a fast AI detection
  model.
- Shows a live console dashboard with counts, system health, and camera status.
- Saves snapshot images when something is detected.
- Sends periodic scene summaries to an AI (OpenRouter) for analysis.

**Phase 2** (this document)

- Tracks each detected person and vehicle with a unique ID across many frames
  (e.g. P-0001 stays P-0001 even if the person walks behind a pillar briefly).
- Classifies gender (Male / Female) once per person using DeepFace AI.
- Determines movement direction (e.g. LEFT → RIGHT).
- Counts how many people walk IN or OUT through a virtual line you draw on the
  camera view.
- Detects which named zone (e.g. "Lobby", "Warehouse") a person or vehicle is
  currently inside.
- Calculates live occupancy (how many people are inside right now, the daily
  peak, and the rolling average).
- Saves all events to a PostgreSQL database for later reporting.
- Saves snapshot photos to organised subfolders.

---

## 2. Folder structure

```
cctv_phase1/
│
├── config/
│   └── config.ini              ← All settings live here (camera IP, zones, etc.)
│
├── logs/
│   ├── application.log         ← General system messages
│   ├── camera.log              ← Camera connection events
│   ├── tracking.log            ← Track open/close events (Phase 2)
│   ├── analytics.log           ← Entry/exit/zone events (Phase 2)
│   ├── database.log            ← Database write activity (Phase 2)
│   ├── gender.log              ← Gender classification results (Phase 2)
│   ├── vehicle.log             ← Vehicle detection events (Phase 2)
│   └── error.log               ← Warnings and errors (all phases)
│
├── models/
│   └── yolo11n.pt              ← YOLO model (auto-downloaded on first run)
│
├── snapshots/
│   ├── people/                 ← Cropped person images
│   ├── vehicles/               ← Cropped vehicle images
│   ├── entry/                  ← Frames captured at entry crossing
│   ├── exit/                   ← Frames captured at exit crossing
│   └── gender/                 ← Cropped face images with gender label
│
├── sql/
│   └── schema.sql              ← Run this once to create the database tables
│
├── tests/
│   ├── unit/                   ← Fast tests, no camera or DB needed
│   │   ├── test_direction_detector.py
│   │   ├── test_line_counter.py
│   │   ├── test_zone_manager.py
│   │   ├── test_occupancy_engine.py
│   │   ├── test_vehicle_analytics.py
│   │   └── test_gender_classifier.py
│   └── integration/            ← Tests that need a running PostgreSQL
│       ├── test_db_manager.py
│       └── test_full_pipeline.py
│
│── Phase 1 files (already existed)
├── main.py                     ← Phase 1 entry point
├── config_manager.py           ← Reads config.ini into Python objects
├── detection.py                ← YOLO object detection
├── rtsp_capture.py             ← Connects to camera and reads frames
├── camera_verifier.py          ← Checks camera before starting
├── health_monitor.py           ← Tracks CPU and RAM usage
├── snapshot_manager.py         ← Saves detection snapshots (Phase 1)
├── dashboard.py                ← Phase 1 console dashboard
├── logger.py                   ← Sets up all log files
├── ai_analyst.py               ← Sends scene summaries to OpenRouter AI
│
│── Phase 2 files (new)
├── phase2_main.py              ← Phase 2 entry point  ← RUN THIS
├── analytics_state.py          ← Shared live data read by the dashboard
├── tracker.py                  ← ByteTrack wrapper (assigns P-0001 / V-0001 IDs)
├── gender_classifier.py        ← DeepFace / InsightFace gender detection
├── direction_detector.py       ← Determines movement direction per track
├── line_counter.py             ← Counts entries and exits at a virtual line
├── zone_manager.py             ← Detects which zone a person/vehicle is in
├── occupancy_engine.py         ← Tracks current/peak/average occupancy
├── vehicle_analytics.py        ← Per-type vehicle counting
├── db_manager.py               ← PostgreSQL connection and table management
├── db_writer.py                ← Background thread that writes to the DB
├── snapshot_manager_v2.py      ← Extended snapshots with subfolders
├── phase2_dashboard.py         ← Phase 2 console dashboard
│
└── requirements.txt            ← Python package list
```

---

## 3. How every file fits together

Think of the system as an assembly line:

```
Camera → rtsp_capture.py
              ↓ raw video frames
         tracker.py  (ByteTrack)
              ↓ List of tracked objects with IDs
         ┌────────────────────────────────────┐
         │  For each tracked person:           │
         │    gender_classifier.py            │
         │    direction_detector.py           │
         │    line_counter.py     → occupancy_engine.py
         │    zone_manager.py                 │
         └────────────────────────────────────┘
         ┌────────────────────────────────────┐
         │  For each tracked vehicle:          │
         │    direction_detector.py           │
         │    vehicle_analytics.py            │
         └────────────────────────────────────┘
              ↓ events
         db_writer.py  (background thread)
              ↓ batched SQL inserts
         db_manager.py → PostgreSQL database
              ↓
         analytics_state.py  (shared live numbers)
              ↓
         phase2_dashboard.py  (Rich console UI)
```

Every module has one job:

| File | Job |
|------|-----|
| `rtsp_capture.py` | Grabs video frames from the camera |
| `tracker.py` | Gives every person/vehicle a unique ID that persists across frames |
| `gender_classifier.py` | Looks at each person once and decides Male/Female |
| `direction_detector.py` | Watches where a track moves and labels the direction |
| `line_counter.py` | Fires an event when a track crosses a virtual line |
| `zone_manager.py` | Tells you which named area a track is currently inside |
| `occupancy_engine.py` | Counts how many people are inside right now |
| `vehicle_analytics.py` | Counts cars, motorcycles, buses, trucks, bicycles |
| `db_manager.py` | Opens a connection pool to PostgreSQL and creates the tables |
| `db_writer.py` | Receives events from a queue and writes them to the DB in the background |
| `analytics_state.py` | A shared memory space the dashboard reads from |
| `phase2_dashboard.py` | Draws the terminal UI with all live numbers |
| `phase2_main.py` | Starts everything up, runs the main loop, shuts down cleanly |

---

## 4. Requirements

**Hardware**

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | Intel i5 | Intel i7 / i9 |
| RAM | 16 GB | 32 GB |
| GPU | None (CPU mode) | NVIDIA RTX 4060 or higher |
| Storage | 20 GB free | 100 GB+ (for snapshots and DB) |

**Software**

- Windows 10 / 11 (64-bit) or Windows Server 2022
- Python 3.11 or 3.13
- FFmpeg (for RTSP decoding)
- PostgreSQL 14+ (only if you want database storage)
- An IP camera that supports RTSP streaming

---

## 5. Installation — step by step

### Step 1 — Install Python

Download Python 3.11 or 3.13 from https://www.python.org/downloads/
During installation, tick **"Add Python to PATH"**.

Verify it works by opening a Command Prompt and typing:
```
python --version
```

### Step 2 — Install FFmpeg

1. Download the Windows build from https://www.gyan.dev/ffmpeg/builds/
   (choose "ffmpeg-release-essentials.zip")
2. Extract the zip to `C:\ffmpeg`
3. Add `C:\ffmpeg\bin` to your Windows PATH:
   - Press Win + R, type `sysdm.cpl`, press Enter
   - Click Advanced → Environment Variables
   - Under System Variables, find `Path`, click Edit
   - Click New, type `C:\ffmpeg\bin`, click OK

Verify:
```
ffmpeg -version
```

### Step 3 — Create a virtual environment (recommended)

Open a Command Prompt inside the `cctv_phase1` folder and run:
```
python -m venv venv
venv\Scripts\activate
```

You will see `(venv)` appear before the prompt. Always activate this before
running the system.

### Step 4 — Install Python packages

With the virtual environment active:
```
pip install -r requirements.txt
```

This installs all required packages including OpenCV, ultralytics (YOLO),
Rich (dashboard), DeepFace (gender), and psycopg2 (database).

> **Note:** DeepFace will download additional AI model files (~300 MB) the
> first time gender classification runs. This is normal.

### Step 5 — Install GPU support (optional but recommended)

If you have an NVIDIA GPU (RTX 4060 or newer), uncomment the GPU lines in
`requirements.txt` and run:
```
pip install torch>=2.3.0+cu121 torchvision>=0.18.0+cu121 --index-url https://download.pytorch.org/whl/cu121
```

### Step 6 — Install PostgreSQL (optional)

Only needed if you want data saved permanently to a database.

1. Download from https://www.postgresql.org/download/windows/
2. Install with the default options. Remember the password you set for the
   `postgres` user.
3. After installation, open pgAdmin or the PostgreSQL shell and create the
   database and user:

```sql
CREATE USER cctv_user WITH PASSWORD 'cctv_pass';
CREATE DATABASE cctv_analytics OWNER cctv_user;
```

4. Run the schema file to create all tables:
```
psql -U cctv_user -d cctv_analytics -f sql/schema.sql
```

---

## 6. Configuration — step by step

Open `config/config.ini` in any text editor (Notepad works fine).

### Camera settings

```ini
[CAMERA]
ip = 10.30.0.161          ← Change to your camera's IP address
username = admin           ← Camera login username
password = nepal@123       ← Camera login password
rtsp_url = rtsp://admin:nepal@123@10.30.0.161:554/cam/realmonitor?channel=1&subtype=0
```

The RTSP URL format varies by camera brand. Common formats:
- **Dahua/HikVision:** `rtsp://user:pass@ip:554/cam/realmonitor?channel=1&subtype=0`
- **Generic:** `rtsp://user:pass@ip:554/stream1`

### Virtual counting line

This is an invisible line across the camera view. When a person crosses it,
the system counts them as entering or exiting.

```ini
[LINE_COUNTER]
line_1 = 0,540 1920,540      ← Start point (x,y) and end point (x,y)
line_1_label = MainEntrance  ← A name for this line
line_1_entry_direction = TOP_TO_BOTTOM  ← People moving downward = entering
```

To figure out good coordinates: look at your camera's resolution (e.g.
1920×1080). A horizontal line halfway down would be `0,540 1920,540`.

Entry direction options:
- `TOP_TO_BOTTOM` — people moving from top to bottom of screen = entry
- `BOTTOM_TO_TOP` — people moving from bottom to top = entry
- `LEFT_TO_RIGHT` — for vertical lines
- `RIGHT_TO_LEFT` — for vertical lines

### Zone definitions

Zones are areas on the camera view defined by corner points.

```ini
[ZONES]
zone_1 = 0,0 640,0 640,540 0,540   ← Four corners of a rectangle (x,y pairs)
zone_1_label = Zone A               ← Name shown on the dashboard
zone_2 = 640,0 1280,0 1280,540 640,540
zone_2_label = Zone B
```

For a 1920×1080 camera, the full frame would be:
`0,0 1920,0 1920,1080 0,1080`

### Gender classification

```ini
[GENDER]
enabled = true
backend = deepface          ← Use deepface (easier) or insightface (faster)
confidence_threshold = 0.65 ← Only accept results with 65%+ confidence
```

### Database

```ini
[DATABASE]
enabled = false             ← Change to true to save data to PostgreSQL
host = localhost
port = 5432
dbname = cctv_analytics
user = cctv_user
password = cctv_pass        ← Or set CCTV_DB_PASSWORD environment variable
```

### AI analysis (OpenRouter)

```ini
[AI]
enabled = true
api_key = YOUR_KEY_HERE     ← Your OpenRouter API key
model = openai/gpt-4o
interval_seconds = 30       ← Send a scene summary every 30 seconds
```

---

## 7. Running the system

### Phase 2 (full analytics)

```
venv\Scripts\activate
python phase2_main.py
```

### Phase 1 (detection only, no tracking)

```
venv\Scripts\activate
python main.py
```

### Stopping the system

Press **Ctrl + C** in the terminal. The system will save any pending database
writes and shut down cleanly.

---

## 8. Reading the dashboard

The Phase 2 dashboard has six panels:

```
┌─────────────────┬──────────────────┬──────────────────┐
│ CAMERA STATUS   │ DETECTION STATS  │ SYSTEM HEALTH    │
│                 │                  │                  │
│ Camera IP       │ People: 3        │ CPU: 45% ████░░  │
│ Status: Connected│ Cars: 2          │ RAM: 4.2 GB      │
│ RTSP: Active    │ Motorcycles: 0   │ YOLO: GPU        │
│ Resolution      │ Gender ♂: 2      │                  │
│ Uptime          │ Gender ♀: 1      │                  │
├─────────────────┼──────────────────┼──────────────────┤
│ ACTIVE TRACKS   │ ENTRY/EXIT &     │ AI ANALYSIS      │
│                 │ OCCUPANCY        │                  │
│ People:         │ IN:  42          │ Moderate foot    │
│ ♂ P-0001 →     │ OUT: 39          │ traffic, 2 cars  │
│ ♀ P-0002 Lobby │ Current: 18      │ parked near gate │
│ ♂ P-0003 →     │ Today's Peak: 38 │                  │
│                 │ Average: 21.4    │ Last: 14:25:10   │
└─────────────────┴──────────────────┴──────────────────┘
┌─────────────────────────────────────────────────────────┐
│ RECENT EVENTS                                           │
│ [14:25:10] ENTRY: P-0041                               │
│ [14:25:08] AI analyst started                          │
└─────────────────────────────────────────────────────────┘
```

**CAMERA STATUS** — Shows whether the camera is connected, the video
resolution, and how long the system has been running.

**DETECTION STATS** — Live counts of every person and vehicle in the current
frame, plus the gender breakdown of all currently tracked people.

**SYSTEM HEALTH** — CPU and RAM usage. If the CPU bar turns red, consider
lowering the camera resolution in config.ini.

**ACTIVE TRACKS** — Each currently visible person with their gender, movement
direction, and zone. Vehicles are shown below.

**ENTRY/EXIT & OCCUPANCY** — Cumulative counts of people who have entered and
exited through the virtual line, the current number of people inside, and the
daily peak.

**AI ANALYSIS** — A one-sentence description of the scene generated by the AI
every 30 seconds.

---

## 9. Where data is saved

### Snapshots (image files)

| Folder | What is saved there |
|--------|---------------------|
| `snapshots/people/` | Cropped image of each person, labelled with their track ID |
| `snapshots/vehicles/` | Cropped image of each vehicle |
| `snapshots/entry/` | Full frame at the moment someone crosses the entry line |
| `snapshots/exit/` | Full frame at the moment someone crosses the exit line |
| `snapshots/gender/` | Cropped person image with their gender label printed on it |

Filenames include the track ID and a timestamp, e.g.:
`P-0001_entry_20260615_143022.jpg`

### Log files

All logs are in the `logs/` folder. Each file covers a specific topic:

| File | What it records |
|------|-----------------|
| `application.log` | Everything the system does |
| `tracking.log` | When tracks are created and closed |
| `analytics.log` | Every entry, exit, and zone transition |
| `gender.log` | Gender classification results |
| `vehicle.log` | Vehicle detection events |
| `database.log` | Database write activity |
| `error.log` | Warnings and errors only |

Logs rotate automatically when they reach 10 MB (up to 5 backup files kept).

### Database tables

When `DATABASE.enabled = true`, the following tables are written to:

| Table | What it stores |
|-------|----------------|
| `cameras` | Camera details (IP, RTSP URL) |
| `sessions` | One row per system run |
| `tracked_objects` | Position of every track, every few frames |
| `gender_classifications` | Gender result for each track |
| `direction_events` | Direction determined for each track |
| `line_crossings` | Every entry and exit event |
| `zone_events` | Every zone entry and zone exit |
| `occupancy_snapshots` | Occupancy numbers every 60 seconds |
| `vehicle_counts` | Vehicle counts per hour |
| `error_events` | Errors logged to the database |
| `system_health_snapshots` | CPU/RAM/FPS every 30 seconds |

---

## 10. Setting up the database

### Step 1 — Create the PostgreSQL database

```sql
-- Run this in psql or pgAdmin:
CREATE USER cctv_user WITH PASSWORD 'cctv_pass';
CREATE DATABASE cctv_analytics OWNER cctv_user;
```

### Step 2 — Create the tables

```
psql -U cctv_user -d cctv_analytics -f sql/schema.sql
```

This is safe to run multiple times — it uses `CREATE TABLE IF NOT EXISTS` so
it will never delete existing data.

### Step 3 — Enable the database in config.ini

```ini
[DATABASE]
enabled = true
host = localhost
port = 5432
dbname = cctv_analytics
user = cctv_user
password = cctv_pass
```

For security, you can store the password as an environment variable instead:
```
set CCTV_DB_PASSWORD=cctv_pass
```
Then leave `password =` empty in config.ini — the system will read the
environment variable automatically.

---

## 11. Running the tests

Unit tests run without a camera, database, or GPU:

```
venv\Scripts\activate
pytest tests/unit/ -v
```

Integration tests for the database (requires PostgreSQL running):
```
set CCTV_TEST_PASSWORD=cctv_pass
pytest tests/integration/test_db_manager.py -v
```

Full pipeline integration tests (no camera needed):
```
pytest tests/integration/test_full_pipeline.py -v
```

Run all tests at once:
```
pytest tests/ -v
```

---

## 12. Troubleshooting

### "Camera verification failed"

- Check the camera IP in `config.ini` is correct.
- Make sure the camera and computer are on the same network.
- Try pasting the RTSP URL into VLC (Media → Open Network Stream) to
  confirm it works.

### "YOLO model could not be loaded"

- Run `pip install ultralytics --upgrade`.
- If using GPU, make sure the CUDA version matches your GPU driver.
  Run `nvidia-smi` to check your CUDA version.

### Gender classification not working

- Run `pip install deepface --upgrade`.
- The first run downloads ~300 MB of models — wait for it to complete.
- If DeepFace fails, try `backend = insightface` in config.ini and run
  `pip install insightface onnxruntime`.

### Database connection failed

- Check PostgreSQL is running: open Services (Win + R → `services.msc`) and
  find `postgresql-x64-xx`.
- Verify the username/password/database name in config.ini.
- Make sure PostgreSQL is listening on the configured port (default 5432).

### System using too much CPU

- In `config.ini`, lower the model: `model = models/yolo11n.pt` (the `n`
  variant is the fastest).
- Reduce the camera resolution by changing the RTSP subtype in the URL
  (subtype=1 for sub-stream instead of main stream).
- Enable GPU acceleration by installing the CUDA torch packages.

### Dashboard not refreshing

- Increase `dashboard_refresh_rate` in config.ini (e.g. `0.5` = twice per
  second, `1.0` = once per second).

---

## 13. Flow diagram

```
START
  │
  ├─ Read config.ini
  ├─ Verify camera (pre-flight check)
  ├─ Load YOLO model (ByteTrack)
  ├─ Start database connection (if enabled)
  ├─ Start RTSP video capture
  ├─ Start dashboard
  │
  └─ MAIN LOOP ──────────────────────────────────────────────┐
       │                                                      │
       ├─ Grab one video frame from camera                    │
       │                                                      │
       ├─ Run ByteTrack → get list of tracked people/vehicles │
       │     Each has: ID (P-0001), bounding box, confidence  │
       │                                                      │
       ├─ For each PERSON:                                     │
       │   ├─ Classify gender (once per person, cached)       │
       │   ├─ Update movement direction history               │
       │   ├─ Check if person crossed the counting line       │
       │   │   └─ If yes: update occupancy (IN or OUT)        │
       │   │             save entry/exit snapshot             │
       │   │             write crossing to database           │
       │   └─ Check which zone person is in                   │
       │       └─ If zone changed: write zone event to DB     │
       │                                                      │
       ├─ For each VEHICLE:                                    │
       │   ├─ Update direction history                        │
       │   └─ Increment per-type counter                      │
       │                                                      │
       ├─ Every 60 seconds: save occupancy snapshot to DB     │
       ├─ Every 30 seconds: save system health snapshot to DB │
       ├─ Every 30 seconds: send AI scene summary             │
       │                                                      │
       ├─ Update dashboard with latest numbers                │
       │                                                      │
       └─ Repeat ─────────────────────────────────────────────┘
  │
  ├─ Ctrl+C pressed
  ├─ Close database session
  ├─ Drain pending DB writes
  └─ STOP
```

---

## Phase 3 (coming next)

Phase 3 will add:
- Named employee face recognition ("Alice entered at 09:02")
- Cross-camera re-identification (track the same person across cameras)
- Canteen attendance analysis
- Visitor management with entry logs
- Enterprise reporting dashboard

---

*Built on: Python 3.13 · ultralytics (ByteTrack + YOLO) · DeepFace · Rich · psycopg2 · OpenRouter AI*
