# CCTV Analytics Phase 1 – Installation & Testing Guide

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | Intel i5 (8th gen+) | Intel i7 / Ryzen 7 |
| RAM | 16 GB | 32 GB |
| GPU | None (CPU mode) | NVIDIA RTX 4060 (CUDA 12.x) |
| OS | Windows 11 | Windows 11 / Server 2022 |
| Python | 3.13+ | 3.13 |
| Storage | 10 GB free | 50 GB+ for snapshots/logs |

---

## Step 1 – Install Python 3.13

1. Download from https://www.python.org/downloads/
2. During setup: tick **"Add Python to PATH"**
3. Verify: `python --version`

---

## Step 2 – Install FFmpeg

FFmpeg is required for RTSP stream decoding via OpenCV.

1. Download the latest Windows build from https://ffmpeg.org/download.html  
   (choose *Windows builds from gyan.dev* → `ffmpeg-release-essentials.zip`)
2. Extract to `C:\ffmpeg\`
3. Add `C:\ffmpeg\bin` to your **System PATH**:
   - Win + S → "Environment Variables" → System Variables → Path → Edit → New
4. Verify: open a new cmd and run `ffmpeg -version`

---

## Step 3 – Create Virtual Environment

```cmd
cd C:\cctv_phase1
python -m venv venv
venv\Scripts\activate
```

---

## Step 4 – Install Python Dependencies

### CPU-only mode (no GPU)

```cmd
pip install -r requirements.txt
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

### NVIDIA GPU mode (CUDA 12.x – RTX 4060 recommended)

```cmd
pip install -r requirements.txt
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

Verify GPU is detected:

```cmd
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

---

## Step 5 – Configure the Camera

Edit `config/config.ini`:

```ini
[CAMERA]
ip       = 10.30.0.161
username = admin
password = YOUR_ACTUAL_PASSWORD
rtsp_url = rtsp://admin:YOUR_ACTUAL_PASSWORD@10.30.0.161:554/unicast/c1/s0/live
```

### Finding the Correct RTSP URL for Uniview IPC-P213-AF40KC

The camera supports several stream paths. Try in order:

| Stream | RTSP URL |
|--------|----------|
| Main stream (2560×1440) | `rtsp://admin:PASS@10.30.0.161:554/unicast/c1/s0/live` |
| Sub stream (640×480) | `rtsp://admin:PASS@10.30.0.161:554/unicast/c1/s1/live` |
| ONVIF profile | `rtsp://admin:PASS@10.30.0.161:554/profile1/media.smp` |

You can verify the URL with VLC Media Player:
  **Media → Open Network Stream → paste the RTSP URL**

---

## Step 6 – Download YOLO Model

The model is downloaded automatically on first run. To pre-download:

```cmd
python -c "from ultralytics import YOLO; YOLO('yolo11n.pt')"
```

Then move the downloaded file to the `models/` folder:

```cmd
move %USERPROFILE%\.cache\ultralytics\yolo11n.pt models\yolo11n.pt
```

---

## Step 7 – Run the Application

```cmd
venv\Scripts\activate
python main.py
```

Press **Ctrl+C** to stop gracefully.

---

## Project Structure

```
cctv_phase1/
├── main.py                  ← Entry point
├── config_manager.py        ← Config loader
├── camera_verifier.py       ← Pre-flight verification
├── rtsp_capture.py          ← Threaded RTSP capture + reconnect
├── detection.py             ← YOLOv11 inference
├── snapshot_manager.py      ← JPEG snapshot saves
├── health_monitor.py        ← CPU / RAM monitoring
├── dashboard.py             ← Rich console dashboard
├── logger.py                ← Logging configuration
├── requirements.txt
├── INSTALLATION_GUIDE.md
├── TESTING_GUIDE.md
├── config/
│   └── config.ini
├── models/
│   └── yolo11n.pt           ← Downloaded on first run
├── snapshots/
│   ├── detection/
│   ├── error/
│   └── reconnect/
└── logs/
    ├── application.log
    ├── error.log
    └── camera.log
```

---

## Troubleshooting

### Camera not reachable (ping fails)

- Verify the camera IP on ODM Device Manager
- Check the network cable and switch port
- Ensure your PC and camera are on the same subnet

### RTSP 401 Unauthorized

- Double-check `username` and `password` in `config.ini`
- Log into the camera web interface and verify the RTSP credentials
- Try the RTSP URL in VLC first

### RTSP 404 / Stream Not Found

- Try the alternative stream paths listed in Step 5
- Confirm RTSP is enabled in the camera web UI under **Network → RTSP**

### YOLO model not found

- Run the pre-download command in Step 6
- Ensure the file is placed in `models/yolo11n.pt`

### Low FPS / high CPU

- Switch to the sub-stream URL (640×480) for faster processing
- Enable GPU mode (Step 4 – CUDA)
- Reduce `confidence` in `config.ini` (e.g. 0.30)

### Rich dashboard appears garbled

- Use **Windows Terminal** or **PowerShell** – avoid legacy `cmd.exe`
- Set the console font to a Nerd Font or at least Consolas 12pt
