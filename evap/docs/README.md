```
███████╗██╗   ██╗ █████╗ ██████╗
██╔════╝██║   ██║██╔══██╗██╔══██╗
█████╗  ██║   ██║███████║██████╔╝
██╔══╝  ╚██╗ ██╔╝██╔══██║██╔═══╝
███████╗ ╚████╔╝ ██║  ██║██║
╚══════╝  ╚═══╝  ╚═╝  ╚═╝╚═╝

  Enterprise Video Analytics Platform
  Phase 4 — AI-Powered Multi-Camera Intelligence
  ─────────────────────────────────────────────
  Real-time detection · Face recognition · ANPR
  Behavioral analytics · ERP integration · GIS
```

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)](https://reactjs.org)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docker.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7.2-DC382D?style=flat-square&logo=redis&logoColor=white)](https://redis.io)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

---

## Project Overview

**EVAP (Enterprise Video Analytics Platform)** is a production-grade, AI-driven video surveillance and analytics system built for large-scale enterprise deployments. It transforms passive CCTV infrastructure into an active intelligence layer — processing live streams from up to 500+ cameras simultaneously, extracting structured data from raw video, and surfacing actionable insights through a real-time web dashboard.

EVAP is architected around an event-driven pipeline: frames are ingested via RTSP/ONVIF, processed by a GPU-accelerated AI engine (YOLOv11 + ByteTrack + InsightFace), and routed through RabbitMQ to purpose-built Celery workers that handle alerting, ERP synchronization, attendance automation, and report generation. The frontend is a React 18 single-page application with live WebSocket feeds, GIS floor maps, and executive-grade reporting — designed to serve security teams, HR managers, operations directors, and C-suite executives from the same platform.

Key capabilities include automatic number plate recognition (ANPR), cross-camera person re-identification, behavioral heat maps, occupancy analytics, visitor lifecycle management, and bi-directional ERP integration with SAP, Oracle, and custom HR systems.

---

## Key Features

- **Real-Time Dashboard** — Live camera grid with per-camera detection overlays, occupancy counters, and system health indicators updated via WebSocket every 500 ms.
- **Floor Map / GIS Analytics** — Interactive Leaflet-based maps with zone polygons, live head-count overlays, and occupancy threshold alerts tied to physical floor plans.
- **Vehicle Analytics & ANPR** — LPRNet + WPOD-Net automatic number plate recognition with sub-200 ms latency; maintains whitelist/blacklist; syncs entries/exits to ERP.
- **Visitor Management** — Full visitor lifecycle: pre-registration, QR check-in, face capture, escort assignment, overstay detection, and digital audit trail.
- **Smart Alerts** — Rule-based and AI-classified alert engine covering intrusion, loitering, crowd formation, object abandonment, and blacklisted-person detection; routed via email, SMS, and push notification.
- **ERP Integration** — Webhook-based bi-directional sync with SAP S/4HANA, Oracle HCM, and generic REST targets; supports employee roster import and real-time attendance push.
- **Attendance Automation** — Face-recognition-driven check-in/check-out with shift mapping, overtime flagging, and exportable attendance registers; replaces legacy biometric terminals.
- **Heat Maps & Behavioral Analytics** — Temporal and spatial density heat maps, dwell-time distributions, path trajectory clustering, and conversion funnel analysis for retail or campus environments.
- **Multi-Camera Analytics** — Cross-camera person re-identification using InsightFace embeddings, global track stitching across camera handoff zones, and entity timeline reconstruction.
- **Executive Reporting** — Scheduled and on-demand PDF/Excel reports with KPI scorecards, trend charts, compliance summaries, and camera uptime statistics; delivered via email or S3.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DATA INGESTION LAYER                             │
│                                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐               │
│  │ Camera 1 │  │ Camera 2 │  │ Camera N │  │  ONVIF   │               │
│  │  (RTSP)  │  │  (RTSP)  │  │  (RTSP)  │  │ Discovery│               │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘               │
│       └─────────────┴──────────────┴─────────────┘                     │
│                              │ FFmpeg Frame Decode                      │
│                              ▼                                          │
│                    ┌─────────────────────┐                              │
│                    │   Frame Buffer      │  (Redis Stream per camera)   │
│                    │   Connection Pool   │                              │
│                    └──────────┬──────────┘                              │
└───────────────────────────────┼─────────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────────┐
│                         AI PROCESSING LAYER                             │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     GPU Batch Processor                          │   │
│  │  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐   │   │
│  │  │  YOLOv11    │  │  ByteTrack   │  │    InsightFace       │   │   │
│  │  │  Detection  │→ │  Tracking    │→ │    Recognition       │   │   │
│  │  │  (n/s/m/l)  │  │  Multi-Obj  │  │    ArcFace Embed.    │   │   │
│  │  └─────────────┘  └──────────────┘  └──────────────────────┘   │   │
│  │                                                                  │   │
│  │  ┌─────────────────────────────────────────────────────────┐   │   │
│  │  │   ANPR Pipeline: WPOD-Net (plate detect) → LPRNet OCR  │   │   │
│  │  └─────────────────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────┬──────────────────────────────┘   │
└─────────────────────────────────────┼───────────────────────────────────┘
                                      │ Structured Events (JSON)
┌─────────────────────────────────────▼───────────────────────────────────┐
│                        MESSAGE QUEUE LAYER                              │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                        RabbitMQ                                  │   │
│  │  Exchange: evap.events    Exchange: evap.alerts                  │   │
│  │  Exchange: evap.notifications   (DLQ for each)                  │   │
│  │                                                                  │   │
│  │  Queues: detections │ face_events │ vehicle_events │ alerts      │   │
│  └─────┬─────────────────────┬─────────────┬──────────┬────────────┘   │
└────────┼─────────────────────┼─────────────┼──────────┼────────────────┘
         │                     │             │          │
┌────────▼─────────────────────▼─────────────▼──────────▼────────────────┐
│                         APPLICATION LAYER                               │
│                                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  ┌────────────┐  │
│  │  detection_  │  │  alert_      │  │  report_    │  │  sync_     │  │
│  │  worker      │  │  worker      │  │  worker     │  │  worker    │  │
│  │  (Celery)    │  │  (Celery)    │  │  (Celery)   │  │  (Celery)  │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬──────┘  └─────┬──────┘  │
│         │                 │                  │               │          │
│  ┌──────▼─────────────────▼──────────────────▼───────────────▼──────┐  │
│  │                    FastAPI Backend (async)                         │  │
│  │           REST API v1  ·  WebSocket Manager  ·  Background Tasks  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
┌────────▼─────────┐  ┌──────────▼──────────┐  ┌────────▼──────────────┐
│   DATA LAYER     │  │  PRESENTATION LAYER │  │  MONITORING LAYER     │
│                  │  │                     │  │                       │
│  PostgreSQL 16   │  │  React 18 SPA       │  │  Prometheus           │
│  + TimescaleDB   │  │  Zustand · R-Query  │  │  ↓                    │
│                  │  │  Leaflet GIS        │  │  Grafana Dashboards   │
│  Redis 7.2       │  │  WebSocket Hooks    │  │  ↓                    │
│  (cache/sessions)│  │                     │  │  Alertmanager         │
│                  │  │  ← REST + WS →      │  │  (PagerDuty/Slack)    │
│  S3 / MinIO      │  │                     │  │                       │
│  (video archive) │  │                     │  │  Jaeger Tracing       │
└──────────────────┘  └─────────────────────┘  └───────────────────────┘
```

---

## Folder Structure

```
evap/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── endpoints/
│   │   │       │   ├── cameras.py
│   │   │       │   ├── alerts.py
│   │   │       │   ├── attendance.py
│   │   │       │   ├── vehicles.py
│   │   │       │   ├── visitors.py
│   │   │       │   ├── reports.py
│   │   │       │   ├── zones.py
│   │   │       │   └── erp.py
│   │   │       ├── deps.py
│   │   │       └── router.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   ├── logging.py
│   │   │   └── exceptions.py
│   │   ├── models/
│   │   │   ├── camera.py
│   │   │   ├── person.py
│   │   │   ├── vehicle.py
│   │   │   ├── event.py
│   │   │   ├── alert.py
│   │   │   ├── attendance.py
│   │   │   └── visitor.py
│   │   ├── schemas/
│   │   │   ├── camera.py
│   │   │   ├── alert.py
│   │   │   └── report.py
│   │   ├── services/
│   │   │   ├── camera_service.py
│   │   │   ├── face_service.py
│   │   │   ├── vehicle_service.py
│   │   │   ├── alert_service.py
│   │   │   ├── attendance_service.py
│   │   │   ├── erp_service.py
│   │   │   └── report_service.py
│   │   ├── workers/
│   │   │   ├── celery_app.py
│   │   │   ├── detection_worker.py
│   │   │   ├── alert_worker.py
│   │   │   ├── report_worker.py
│   │   │   └── sync_worker.py
│   │   ├── websocket/
│   │   │   ├── manager.py
│   │   │   ├── handlers.py
│   │   │   └── events.py
│   │   └── main.py
│   ├── migrations/
│   │   ├── env.py
│   │   └── versions/
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── conftest.py
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── CameraGrid/
│   │   │   ├── AlertPanel/
│   │   │   ├── FloorMap/
│   │   │   ├── HeatMap/
│   │   │   └── common/
│   │   ├── pages/
│   │   │   ├── Dashboard/
│   │   │   ├── Cameras/
│   │   │   ├── Attendance/
│   │   │   ├── Visitors/
│   │   │   ├── Vehicles/
│   │   │   ├── Reports/
│   │   │   └── Settings/
│   │   ├── services/
│   │   │   ├── api.ts
│   │   │   ├── websocket.ts
│   │   │   └── auth.ts
│   │   ├── store/
│   │   │   ├── cameraStore.ts
│   │   │   ├── alertStore.ts
│   │   │   └── authStore.ts
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts
│   │   │   ├── useCameraFeed.ts
│   │   │   └── useAlerts.ts
│   │   └── types/
│   ├── public/
│   ├── Dockerfile
│   └── package.json
├── ai_engine/
│   ├── detectors/
│   │   ├── yolo_detector.py
│   │   ├── anpr_detector.py
│   │   └── zone_detector.py
│   ├── trackers/
│   │   ├── bytetrack.py
│   │   ├── track_manager.py
│   │   └── reid_matcher.py
│   ├── recognizers/
│   │   ├── face_recognizer.py
│   │   ├── lpr_recognizer.py
│   │   └── embedding_store.py
│   ├── pipeline/
│   │   ├── frame_pipeline.py
│   │   ├── batch_processor.py
│   │   ├── stream_reader.py
│   │   └── event_publisher.py
│   ├── models/
│   │   └── weights/          ← model weight files (not in git)
│   ├── config/
│   │   └── pipeline.yaml
│   └── tests/
├── deploy/
│   ├── docker/
│   │   ├── docker-compose.yml
│   │   ├── docker-compose.prod.yml
│   │   └── docker-compose.monitoring.yml
│   ├── kubernetes/
│   │   ├── namespaces/
│   │   ├── deployments/
│   │   │   ├── backend-deployment.yaml
│   │   │   ├── ai-engine-deployment.yaml
│   │   │   └── frontend-deployment.yaml
│   │   ├── services/
│   │   ├── configmaps/
│   │   ├── secrets/
│   │   ├── hpa/
│   │   │   └── ai-engine-hpa.yaml
│   │   └── ingress/
│   ├── nginx/
│   │   ├── nginx.conf
│   │   └── ssl/
│   └── scripts/
│       ├── init_db.sh
│       ├── seed_models.sh
│       └── healthcheck.sh
└── docs/
    ├── README.md                  ← this file
    ├── SYSTEM_ARCHITECTURE.md
    ├── API_REFERENCE.md
    ├── DEPLOYMENT_GUIDE.md
    ├── CAMERA_INTEGRATION.md
    └── ERP_INTEGRATION.md
```

---

## Quick Start

```bash
# 1. Clone and configure environment
git clone https://github.com/your-org/evap.git && cd evap
cp .env.example .env          # edit DATABASE_URL, REDIS_URL, RABBITMQ_URL, SECRET_KEY

# 2. Pull model weights and start all services
bash deploy/scripts/seed_models.sh
docker compose -f deploy/docker/docker-compose.yml up -d

# 3. Open the dashboard (default credentials: admin / changeme)
open http://localhost:3000
```

> For production deployments, see [`docs/DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md). For Kubernetes, see `deploy/kubernetes/`.

---

## Module Descriptions

| Module | Description | Key Technologies |
|---|---|---|
| **Dashboard** | Real-time camera grid, system health KPIs, live event feed, and per-zone occupancy counters refreshed via WebSocket | React 18, Zustand, WebSocket, Recharts |
| **Floor Map / GIS** | Interactive floor plan overlays with polygon-defined zones, live head-count labels, and occupancy threshold heat coloring | Leaflet.js, GeoJSON, PostGIS, WebSocket |
| **Vehicle Analytics / ANPR** | Automatic number plate recognition with entry/exit logging, whitelist/blacklist enforcement, and parking duration tracking | WPOD-Net, LPRNet, PostgreSQL, Redis |
| **Visitor Management** | Pre-registration portal, QR-code check-in, face capture on arrival, escort workflow, overstay alerts, and digital sign-out | InsightFace, FastAPI, PostgreSQL, SMTP |
| **Smart Alerts** | Configurable rule engine covering 20+ alert types; classifies, deduplicates, and escalates via email/SMS/webhook with SLA tracking | RabbitMQ, Celery, Twilio, SendGrid |
| **ERP Integration** | Bi-directional sync with SAP S/4HANA, Oracle HCM, and REST-based HR systems; pushes attendance, visitors, and vehicle events in real time | Celery sync_worker, OAuth2, Webhooks |
| **Attendance Automation** | Face-recognition-based clock-in/clock-out replacing physical terminals; maps to shifts, flags late arrivals, early exits, and overtime | InsightFace, TimescaleDB, Celery |
| **Heat Maps / Behavioral Analytics** | Temporal density overlays, dwell-time histograms, movement trajectories, crowd flow vectors, and zone-transition matrices | OpenCV, NumPy, TimescaleDB, D3.js |
| **Multi-Camera Analytics** | Cross-camera re-identification, entity timeline reconstruction across handoff zones, global track graph, and entry-exit pair matching | InsightFace ReID, ByteTrack, Redis |
| **Executive Reporting** | Scheduled and ad-hoc PDF/Excel reports with KPI scorecards, trend analysis, camera uptime logs, and compliance audit exports | ReportLab, OpenPyXL, Celery, S3/MinIO |

---

## Camera Scale

EVAP supports deployments ranging from single-site pilots to multi-site enterprise rollouts:

| Scale | Camera Count | Deployment Model |
|---|---|---|
| Pilot | 1 – 20 | Single server, Docker Compose |
| Mid-range | 21 – 100 | Multi-worker, Docker Compose with GPU nodes |
| Enterprise | 101 – 500 | Kubernetes cluster, HPA-managed AI workers |
| Large Enterprise | 500+ | Multi-region Kubernetes, federated DB, edge nodes |

---

## Hardware Requirements

| Tier | Cameras | CPU | RAM | GPU | Storage |
|---|---|---|---|---|---|
| **Small** | Up to 20 | 16-core (Intel Xeon / AMD EPYC) | 32 GB DDR4 | NVIDIA RTX 3080 (10 GB VRAM) | 2 TB NVMe SSD |
| **Medium** | 21 – 100 | 32-core dual-socket | 128 GB DDR4 | 2× NVIDIA A10 (24 GB VRAM each) | 10 TB NVMe RAID-10 |
| **Large** | 100+ | Kubernetes node pool (≥ 8 nodes, 32 cores each) | 256 GB per node | NVIDIA A100 80 GB per AI node | Distributed storage (Ceph / NetApp) |

> **OS**: Ubuntu 22.04 LTS recommended. CUDA 12.4+, cuDNN 9.x required on all GPU nodes.

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](../LICENSE) file for details.

---

## Contributing

1. Fork the repository and create a feature branch: `git checkout -b feature/your-feature`.
2. Follow the coding standards defined in `.editorconfig` and `pyproject.toml` (Black + Ruff for Python, ESLint + Prettier for TypeScript).
3. Write or update tests — minimum 80% coverage required for new services.
4. Open a pull request against `main` with a clear description of the change and link to any related issue.
5. All PRs require at least one approval and a passing CI pipeline before merge.

---

## Documentation Index

| Document | Purpose |
|---|---|
| [`SYSTEM_ARCHITECTURE.md`](SYSTEM_ARCHITECTURE.md) | Deep-dive into component design, data flows, scalability, HA, and security |
| [`API_REFERENCE.md`](API_REFERENCE.md) | Full REST + WebSocket API reference with request/response schemas |
| [`DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) | Step-by-step Docker and Kubernetes deployment instructions |
| [`CAMERA_INTEGRATION.md`](CAMERA_INTEGRATION.md) | RTSP/ONVIF camera onboarding, credential management, and troubleshooting |
| [`ERP_INTEGRATION.md`](ERP_INTEGRATION.md) | SAP, Oracle, and custom ERP connector setup and webhook reference |
