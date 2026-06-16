# CCTV Analytics Phase 1 – Testing Guide

---

## Test 1 – Camera Connectivity Verification

**What it tests:** Ping, RTSP port 554 reachability, authentication, stream availability.

**Expected output:**

```
Running camera pre-flight verification…

══════════ CAMERA PRE-FLIGHT VERIFICATION ══════════
  Camera IP     10.30.0.161
  Status        Connected
  RTSP Port     Open
  Stream        Available
  Resolution    2560x1440
  FPS           25
  Codec         H264
```

**Failure simulation:**
- Unplug camera network cable → expect ping fail message and clean exit
- Enter wrong password in config.ini → expect "RTSP Authentication Failed" message

---

## Test 2 – Dashboard Rendering

**What it tests:** Rich dashboard renders without error; all panels visible.

**Steps:**
1. Run `python main.py`
2. After verification passes, the dashboard should appear
3. Confirm three panels: CAMERA STATUS / DETECTION STATS / SYSTEM HEALTH
4. Confirm FPS is updating every ~0.5 seconds

---

## Test 3 – Person Detection

**What it tests:** YOLO detects people correctly.

**Steps:**
1. Walk in front of the camera
2. Observe "People" count increment in DETECTION STATS panel
3. Check `snapshots/detection/` folder for saved JPEG

---

## Test 4 – Vehicle Detection

**What it tests:** YOLO detects cars, motorcycles, buses, trucks, bicycles.

**Steps:**
1. Point camera at a road / parking area
2. Observe vehicle counts in DETECTION STATS
3. Verify only the 6 target classes appear (no chairs, animals, etc.)

---

## Test 5 – Network Failure Recovery

**What it tests:** Automatic reconnection after camera goes offline.

**Steps:**
1. Start the application and confirm it's running
2. Disconnect the camera's network cable (or disable the switch port)
3. Observe dashboard: Status → "Reconnecting…", log panel shows attempts
4. Reconnect the cable
5. Confirm dashboard returns to "Connected" and detection resumes
6. Check `logs/camera.log` for reconnect events
7. Check `snapshots/reconnect/` for a snapshot

**Expected log output:**

```
2026-06-15 10:18:24
ERROR
Camera connection lost

2026-06-15 10:18:29
WARNING
Reconnect attempt 1/10

2026-06-15 10:18:34
WARNING
Reconnect attempt 2/10

2026-06-15 10:18:34
INFO
Camera Reconnected
```

---

## Test 6 – Frame Failure Handling

**What it tests:** The system skips corrupt/empty frames and recovers.

**Simulation:** Temporarily set `frame_failure_threshold = 1` in config.ini  
This forces reconnect after a single bad frame (only for testing; set back to 30 after).

---

## Test 7 – Log File Verification

**What it tests:** All three log files are created and populated correctly.

**Steps:**
1. Run the application for 1–2 minutes
2. Check:

```
logs/application.log  – should contain INFO-level events
logs/error.log        – should be empty if no errors
logs/camera.log       – should contain connection and detection events
```

3. Simulate a network disconnection; check `logs/error.log` is updated.

---

## Test 8 – GPU vs CPU Mode

**What it tests:** Correct device selection and CPU fallback.

**Steps:**

GPU available:
1. Confirm `device = auto` in config.ini
2. Run application
3. Dashboard → SYSTEM HEALTH → YOLO Device should show **GPU**

Force CPU:
1. Set `device = cpu` in config.ini
2. Run application
3. Dashboard → YOLO Device should show **CPU**
4. Verify inference still works (slower but functional)

---

## Test 9 – Snapshot Folders

After running with detections:

```
snapshots/
├── detection/    ← JPEG per detection event (max 1 per 10 seconds)
├── error/        ← JPEG on errors / placeholder if no frame available
└── reconnect/    ← First frame after reconnection
```

---

## Test 10 – Graceful Shutdown

**Steps:**
1. Run the application
2. Press **Ctrl+C**
3. Confirm:
   - Dashboard closes cleanly
   - "Shutdown complete" message is printed
   - No Python traceback
   - Log files are flushed and closed
