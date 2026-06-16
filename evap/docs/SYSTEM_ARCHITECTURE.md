# EVAP System Architecture

**Enterprise Video Analytics Platform — Phase 4**
*Revision: 1.0 | June 2026*

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture Layers](#architecture-layers)
   - [Camera / Data Ingestion Layer](#camera--data-ingestion-layer)
   - [AI Processing Layer](#ai-processing-layer)
   - [Message Queue Layer](#message-queue-layer)
   - [Application Layer](#application-layer)
   - [Data Layer](#data-layer)
   - [Presentation Layer](#presentation-layer)
   - [Monitoring Layer](#monitoring-layer)
3. [Component Interaction Diagram](#component-interaction-diagram)
4. [Data Flows](#data-flows)
5. [Scalability Design](#scalability-design)
6. [High Availability](#high-availability)
7. [Security Architecture](#security-architecture)
8. [Integration Points](#integration-points)

---

## Overview

EVAP is designed around three architectural principles:

**Event-Driven Processing.** Every meaningful action — a person entering a zone, a vehicle being recognized, an alert being triggered — becomes a discrete, durable event published to RabbitMQ. Consumers (Celery workers, WebSocket broadcaster, ERP sync) subscribe independently, enabling loose coupling and horizontal fan-out without blocking the critical video processing path.

**Real-Time First.** Camera streams are decoded at native frame rate (configurable, typically 5–15 FPS for analytics), processed through the AI pipeline with GPU batch inference, and results pushed to connected dashboards via WebSocket within approximately 1–2 seconds of the physical event. TimescaleDB provides sub-second queries over time-series detection data even at multi-year retention scales.

**Microservices-Ready Monolith.** The backend is a single FastAPI application that can be deployed as one container for small sites, or split into independently scaled services (API, workers, AI engine) for enterprise deployments via Docker Compose profiles or Kubernetes. Shared boundaries are enforced by the message queue and a well-defined internal service layer — not HTTP calls between services — making the split straightforward when scale demands it.

---

## Architecture Layers

### Camera / Data Ingestion Layer

The ingestion layer is responsible for establishing and maintaining stable video streams from IP cameras, decoding frames, and delivering them reliably to the AI pipeline.

**Protocols supported:**
- **RTSP** (primary) — H.264 and H.265 streams via FFmpeg subprocess with automatic reconnect on disconnect (exponential backoff, max 60 s).
- **ONVIF** (WS-Discovery) — used for camera discovery, PTZ control, and metadata retrieval. Implemented via the `onvif-zeep` library.
- **MJPEG over HTTP** — legacy camera fallback; lower efficiency but broad compatibility.

**Frame pipeline per camera:**

```
RTSP Stream
    │
    ▼
FFmpegReader (subprocess with stdout pipe)
    │  reads raw frames at target FPS (configurable 1–30)
    ▼
FrameBuffer (bounded asyncio.Queue, maxsize=30)
    │  drops oldest frame if AI engine is backlogged
    ▼
FramePublisher → Redis Stream: camera:{id}:frames
```

**Connection management** is handled by `CameraConnectionPool` in `ai_engine/pipeline/stream_reader.py`. Each camera runs an independent async task. A watchdog coroutine checks stream health every 10 seconds and emits a `camera.offline` event if a camera fails to produce a frame within the configured timeout. Camera status is written to Redis with a 30-second TTL so the dashboard reflects outages within one polling cycle.

**Frame rate adaptation:** Under GPU load, the pipeline dynamically reduces frame capture rate (via FFmpeg `-r` flag adjustment) before dropping frames, preserving temporal coverage at the cost of reduced inference frequency. Minimum guaranteed rate is 1 FPS per camera regardless of load.

---

### AI Processing Layer

All inference runs in `ai_engine/` and is fully decoupled from the FastAPI application process. The pipeline is designed for GPU batch processing — frames from multiple cameras are batched together before each inference call to maximize GPU utilization.

#### Object Detection — YOLOv11

EVAP ships with all four YOLOv11 variants. Model selection is configured per deployment tier in `ai_engine/config/pipeline.yaml`:

| Model | Parameters | Inference Speed* | Use Case |
|---|---|---|---|
| `yolov11n` | 2.6 M | ~3 ms/frame | Edge / pilot deployments, CPU fallback |
| `yolov11s` | 9.4 M | ~5 ms/frame | Small sites (< 20 cameras) |
| `yolov11m` | 20.1 M | ~9 ms/frame | Mid-range deployments (default) |
| `yolov11l` | 43.7 M | ~16 ms/frame | Enterprise, accuracy-critical zones |

*On NVIDIA A10, batch size 8, FP16, 640×640 input.*

Detection classes used by EVAP: `person`, `car`, `motorcycle`, `bus`, `truck`, `bicycle`. Other COCO classes are filtered at the pipeline level to reduce downstream event volume.

**Batch processing strategy:** The `BatchProcessor` in `ai_engine/pipeline/batch_processor.py` collects frames from all active cameras into a batch of configurable size (default: 8). If the batch is not full within 50 ms, it is dispatched anyway to bound latency. Batch results are demultiplexed back to per-camera result queues by frame ID.

#### Multi-Object Tracking — ByteTrack

ByteTrack is applied per-camera after detection. It maintains track IDs across frames, handles occlusion by keeping low-confidence detections alive for up to 30 frames, and re-associates them when they reappear. This produces stable `track_id` values used as the primary identity anchor before face recognition resolves a named identity.

Key parameters (tunable per zone):
- `track_thresh`: 0.5 (minimum detection score to start a track)
- `track_buffer`: 30 frames (how long a lost track is held before deletion)
- `match_thresh`: 0.8 (IOU threshold for track-detection association)

#### Face Recognition — InsightFace

The recognition pipeline runs asynchronously relative to tracking. Not every frame is submitted for recognition — only frames where:
1. A track has been active for at least 10 frames (stable track).
2. The face bounding box area exceeds 64×64 pixels.
3. The track has not been successfully identified in the last 30 seconds.

Recognition steps:
1. **Detection:** `RetinaFace` model locates face bounding boxes and 5-point landmarks within the person crop.
2. **Alignment:** Affine transform aligns face to 112×112 canonical pose.
3. **Embedding:** `ArcFace` (ResNet-100 backbone) produces a 512-dimensional L2-normalized embedding.
4. **Search:** Embedding is compared against the employee/visitor index via approximate nearest-neighbor search (FAISS IndexFlatIP). Threshold: cosine similarity ≥ 0.65 → confirmed match.

The embedding index is loaded into GPU memory at startup and refreshed every 60 seconds from Redis (which is populated by the backend when new employees or visitors are enrolled).

#### ANPR Pipeline

Vehicle frames flagged by the YOLO detector are routed to the ANPR sub-pipeline:

1. **Plate Detection:** WPOD-Net localizes the license plate region and applies a perspective correction transform.
2. **OCR:** LPRNet reads the plate characters. Post-processing applies country-specific regex validation (configurable: Indian RTO format, UAE, EU).
3. **Confidence threshold:** Minimum 0.80 combined score (detection × OCR) to emit a plate event.
4. **Lookup:** Plate string is checked against `vehicles` table (whitelist/blacklist) via a Redis-cached lookup with 5-minute TTL.

---

### Message Queue Layer

RabbitMQ is the backbone of EVAP's event-driven architecture. All inter-service communication flows through it, providing durability, backpressure, and independent consumer scaling.

#### Exchanges

| Exchange | Type | Purpose |
|---|---|---|
| `evap.events` | topic | All detection and tracking events from the AI engine |
| `evap.alerts` | direct | Triggered alert notifications requiring immediate action |
| `evap.notifications` | fanout | Broadcast notifications (dashboard push, email, SMS) |
| `evap.erp` | direct | ERP synchronization jobs (attendance, visitor, vehicle) |
| `evap.dlx` | direct | Dead-letter exchange; receives messages that fail processing |

#### Queue Bindings

```
evap.events (topic exchange)
  ├── routing key: "detection.person.*"  → queue: person_detections
  ├── routing key: "detection.vehicle.*" → queue: vehicle_detections
  ├── routing key: "face.recognized"     → queue: face_events
  ├── routing key: "face.unknown"        → queue: unknown_faces
  └── routing key: "zone.#"             → queue: zone_events

evap.alerts (direct exchange)
  ├── routing key: "intrusion"           → queue: intrusion_alerts
  ├── routing key: "loitering"           → queue: loitering_alerts
  ├── routing key: "crowd"               → queue: crowd_alerts
  └── routing key: "blacklist"           → queue: blacklist_alerts

evap.notifications (fanout exchange)
  ├── → queue: dashboard_push
  ├── → queue: email_notifications
  └── → queue: sms_notifications
```

#### Message Schema

All messages follow a common envelope:

```json
{
  "event_id": "uuid4",
  "event_type": "face.recognized",
  "camera_id": "cam_042",
  "timestamp": "2026-06-15T09:14:32.411Z",
  "track_id": 1847,
  "payload": { ... },
  "schema_version": "1.0"
}
```

#### Dead Letter Queues

Each processing queue has a corresponding DLQ configured with `x-dead-letter-exchange: evap.dlx`. Messages are routed to DLQ after 3 failed delivery attempts (configured via `x-delivery-limit` with the RabbitMQ Quorum Queues plugin). A monitoring task polls DLQ depth every 5 minutes and raises a Prometheus alert if depth exceeds 100 messages.

---

### Application Layer

#### FastAPI Backend

The backend (`backend/app/main.py`) is an async FastAPI application running under Uvicorn with multiple workers managed by Gunicorn. Key architectural decisions:

- **Dependency injection** for database sessions (`AsyncSession`), Redis client, and authenticated user context — never passed through global state.
- **Lifespan context manager** handles startup (DB connection pool warm-up, Redis ping, RabbitMQ connection) and shutdown (graceful drain of in-flight WebSocket messages).
- **Background tasks** via `fastapi.BackgroundTasks` for lightweight fire-and-forget operations (e.g., writing audit log entries). Long-running work is always delegated to Celery.

```python
# backend/app/main.py — lifespan pattern
@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    await redis_client.ping()
    await rabbitmq.connect()
    yield
    await websocket_manager.broadcast_shutdown()
    await db.disconnect()
```

#### Celery Workers

Four dedicated worker types, each consuming specific RabbitMQ queues:

| Worker | Queues Consumed | Concurrency | Purpose |
|---|---|---|---|
| `detection_worker` | `person_detections`, `vehicle_detections`, `zone_events` | 8 | Persist detection events; update occupancy counters in Redis |
| `alert_worker` | `intrusion_alerts`, `loitering_alerts`, `crowd_alerts`, `blacklist_alerts` | 4 | Classify, deduplicate (5 min window), persist, and publish to `evap.notifications` |
| `report_worker` | `report_jobs` | 2 | Generate PDF/Excel reports; upload to S3; send email |
| `sync_worker` | `erp_sync_jobs` | 4 | Push attendance/visitor/vehicle records to ERP endpoints |

Workers are configured with `acks_late=True` and `reject_on_worker_lost=True` to prevent message loss on worker crashes. Task results are stored in Redis with a 24-hour TTL for status polling.

#### WebSocket Manager

`backend/app/websocket/manager.py` manages authenticated WebSocket connections with room-based subscriptions:

- Connections are grouped by subscription type: `camera:{id}`, `zone:{id}`, `alerts:global`, `dashboard:global`.
- The manager consumes from RabbitMQ `dashboard_push` queue and broadcasts to all connections subscribed to the relevant room.
- Heartbeat: server sends `{"type": "ping"}` every 30 seconds; clients must respond with `{"type": "pong"}` within 5 seconds or the connection is closed.
- Maximum 500 concurrent WebSocket connections per backend instance (configurable via `WS_MAX_CONNECTIONS`).

---

### Data Layer

#### PostgreSQL 16 Schema Overview

Core tables and their primary relationships:

```sql
cameras (id, name, rtsp_url_encrypted, location_id, status, config_json)
    ↓ 1:N
detection_events (id, camera_id, track_id, class, bbox, confidence, timestamp)
    ↓ N:1
persons (id, employee_id, name, face_embedding_id, department, status)

attendance_records (id, person_id, camera_id, event_type, timestamp, shift_id)
vehicles (id, plate_number, owner_name, category, status [whitelist/blacklist])
vehicle_events (id, vehicle_id, camera_id, event_type, confidence, timestamp)
visitors (id, name, host_employee_id, face_embedding_id, status, check_in, check_out)
alerts (id, alert_type, camera_id, severity, status, created_at, resolved_at)
zones (id, name, camera_id, polygon_coords, max_occupancy, floor_id)
floors (id, name, building_id, map_image_url, geojson)
```

**TimescaleDB hypertables** are used for time-series tables (`detection_events`, `attendance_records`, `vehicle_events`). These are partitioned by `timestamp` with 1-day chunks. Continuous aggregates pre-compute hourly and daily rollups for dashboard queries, keeping OLAP-style queries under 100 ms even at 90-day retention with 500 cameras.

#### Redis Caching Strategy

| Key Pattern | TTL | Content |
|---|---|---|
| `camera:{id}:status` | 30 s | `online` / `offline` / `degraded` + last frame timestamp |
| `camera:{id}:occupancy` | 5 s | Current person count in camera's primary zone |
| `employee:{id}:profile` | 300 s | Name, department, face embedding ID (avoids DB hit on recognition) |
| `plate:{plate}:lookup` | 300 s | Whitelist/blacklist status + owner info |
| `zone:{id}:count` | 5 s | Aggregated occupancy count for floor map rendering |
| `alert:dedup:{hash}` | 300 s | Deduplication key — prevents repeated alerts for same event |
| `session:{token_jti}` | 900 s | JWT JTI for access token invalidation (blacklist on logout) |
| `report:{job_id}:status` | 86400 s | Celery task status for report job polling |

#### Connection Pooling

- **SQLAlchemy async pool:** `pool_size=20`, `max_overflow=10`, `pool_timeout=30`, `pool_recycle=1800`. Shared across all FastAPI workers via `asyncpg` driver.
- **Redis:** `ConnectionPool` with `max_connections=50` per worker process. Separate pool for pub/sub to avoid blocking command-response connections.
- **RabbitMQ:** `aio-pika` with a single persistent connection per process; channel pool with `channel_pool_size=10`.

---

### Presentation Layer

The frontend is a React 18 SPA built with Vite, deployed as a static bundle served by Nginx.

#### State Management

**Zustand** stores handle client-side state with deliberate separation of concerns:

- `cameraStore` — list of cameras, their online status, and current frame metadata.
- `alertStore` — active alerts, unread count, and alert history for the sidebar panel.
- `authStore` — JWT access token (memory-only, never localStorage), user profile, and permissions.
- `zoneStore` — zone occupancy counts and threshold breach states for floor map coloring.

**React Query** (`@tanstack/react-query`) handles all REST API interactions with automatic background refetch, stale-while-revalidate, and optimistic updates for alert resolution.

#### WebSocket Integration

A custom `useWebSocket` hook manages the persistent WebSocket connection:

```typescript
// frontend/src/hooks/useWebSocket.ts (simplified)
export function useWebSocket(room: string) {
  const ws = useRef<WebSocket | null>(null);

  useEffect(() => {
    ws.current = new WebSocket(`${WS_BASE_URL}/ws/${room}`);
    ws.current.onmessage = (e) => {
      const event = JSON.parse(e.data);
      dispatchToStore(event);          // routes to correct Zustand store
    };
    const heartbeat = setInterval(() => {
      ws.current?.send(JSON.stringify({ type: "pong" }));
    }, 25000);
    return () => { clearInterval(heartbeat); ws.current?.close(); };
  }, [room]);
}
```

#### GIS / Floor Maps

Leaflet.js renders floor plan images as `L.imageOverlay` layers with pixel-coordinate CRS. Zone polygons are stored as GeoJSON in PostgreSQL and served via `/api/v1/zones/{floor_id}/geojson`. Occupancy counts and alert states are overlaid as Leaflet markers with React-managed popups, updated from the `zoneStore` via WebSocket without re-rendering the map layer.

---

### Monitoring Layer

#### Prometheus Metrics

Custom metrics exposed at `GET /metrics` (Prometheus scrape endpoint):

```python
# backend/app/core/metrics.py
frames_processed_total = Counter(
    "evap_frames_processed_total",
    "Total frames processed by the AI pipeline",
    ["camera_id", "model_variant"]
)
detections_per_camera = Gauge(
    "evap_detections_per_camera",
    "Current detection count in the last 60 seconds",
    ["camera_id", "class"]
)
api_request_duration_seconds = Histogram(
    "evap_api_request_duration_seconds",
    "API endpoint response time distribution",
    ["method", "endpoint", "status_code"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)
face_recognition_latency_seconds = Histogram(
    "evap_face_recognition_latency_seconds",
    "End-to-end face recognition pipeline latency",
    buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0]
)
rabbitmq_queue_depth = Gauge(
    "evap_rabbitmq_queue_depth",
    "Number of unprocessed messages per queue",
    ["queue_name"]
)
camera_offline_total = Counter(
    "evap_camera_offline_total",
    "Number of camera offline events",
    ["camera_id"]
)
```

#### Grafana Dashboards

Four pre-built dashboards shipped in `deploy/docker/grafana/dashboards/`:

| Dashboard | Key Panels |
|---|---|
| **System Overview** | Camera online ratio, frames/sec, GPU utilization, memory usage, API p95 latency |
| **Detection Analytics** | Detections per class per hour, per-camera detection heatmap, face recognition hit rate |
| **Alert Operations** | Alert rate by type, mean time to resolution, DLQ depth, worker queue backlog |
| **Infrastructure** | PostgreSQL query latency, connection pool saturation, Redis hit rate, RabbitMQ message rates |

#### Alertmanager Rules

Critical alerts defined in `deploy/docker/prometheus/alerts.yaml`:

```yaml
- alert: CameraOffline
  expr: increase(evap_camera_offline_total[5m]) > 0
  for: 2m
  labels:
    severity: warning
  annotations:
    summary: "Camera {{ $labels.camera_id }} is offline"

- alert: RabbitMQBacklog
  expr: evap_rabbitmq_queue_depth{queue_name="person_detections"} > 5000
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "Detection queue backlog exceeds 5000 messages — AI workers may be overloaded"

- alert: APIHighLatency
  expr: histogram_quantile(0.95, evap_api_request_duration_seconds_bucket) > 2.0
  for: 3m
  labels:
    severity: warning
```

---

## Component Interaction Diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  CAMERAS (RTSP/ONVIF)                                                        │
│  cam_001 ··· cam_500                                                         │
└──────────────────────┬───────────────────────────────────────────────────────┘
                       │ raw H264/H265 stream
                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  AI ENGINE PROCESS (ai_engine/)                                              │
│                                                                              │
│  StreamReader × N ──→ FrameBuffer (Redis Stream) ──→ BatchProcessor         │
│                                                           │                  │
│                                              ┌────────────┼─────────────┐   │
│                                              ▼            ▼             ▼   │
│                                          YOLOv11      ByteTrack     ANPR    │
│                                          detect        track         OCR    │
│                                              └────────────┼─────────────┘   │
│                                                           ▼                  │
│                                                    InsightFace ReID          │
│                                                           │                  │
│                                                    EventPublisher            │
└────────────────────────────────────────────────────────┬─────────────────────┘
                                                         │ AMQP publish
                                                         ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  RABBITMQ (amqp://rabbitmq:5672)                                             │
│                                                                              │
│  evap.events ────────────────────────────────────────────────────────────   │
│  ├── person_detections queue    ← detection_worker subscribes               │
│  ├── vehicle_detections queue   ← detection_worker subscribes               │
│  ├── face_events queue          ← detection_worker subscribes               │
│  └── zone_events queue          ← detection_worker subscribes               │
│                                                                              │
│  evap.alerts ────────────────────────────────────────────────────────────   │
│  ├── intrusion_alerts queue     ← alert_worker subscribes                   │
│  ├── blacklist_alerts queue     ← alert_worker subscribes                   │
│  └── crowd_alerts queue         ← alert_worker subscribes                   │
│                                                                              │
│  evap.notifications (fanout) ────────────────────────────────────────────   │
│  ├── dashboard_push queue       ← WebSocket manager subscribes              │
│  ├── email_notifications queue  ← alert_worker subscribes                   │
│  └── sms_notifications queue    ← alert_worker subscribes                   │
└──────────────────────────────────────────────────────────────────────────────┘
          │                   │                    │                 │
          ▼                   ▼                    ▼                 ▼
  ┌───────────────┐  ┌───────────────┐  ┌──────────────┐  ┌──────────────────┐
  │ detection_    │  │ alert_worker  │  │ report_      │  │ sync_worker      │
  │ worker        │  │ (Celery)      │  │ worker       │  │ (Celery)         │
  │ (Celery)      │  │               │  │ (Celery)     │  │                  │
  │ • persist evt │  │ • dedup       │  │ • PDF/Excel  │  │ • SAP push       │
  │ • update Redis│  │ • notify      │  │ • S3 upload  │  │ • Oracle push    │
  │ • occupancy   │  │ • escalate    │  │ • email      │  │ • webhook POST   │
  └──────┬────────┘  └──────┬────────┘  └──────┬───────┘  └──────┬───────────┘
         │                  │                   │                 │
         └──────────────────┼───────────────────┘                 │
                            │ reads/writes                         │
                            ▼                                      ▼
┌──────────────────────────────────────────┐  ┌───────────────────────────────┐
│  FASTAPI BACKEND (backend/)              │  │  EXTERNAL ERP SYSTEMS         │
│                                          │  │  SAP S/4HANA                  │
│  REST API v1 (/api/v1/*)                 │  │  Oracle HCM                   │
│  WebSocket (/ws/{room})                  │  │  Custom HR REST API           │
│  Background Tasks                        │  └───────────────────────────────┘
│  RBAC Middleware                         │
│  JWT Auth (RS256)                        │
└──────────────────────────────────────────┘
         │ reads/writes         │ WebSocket broadcast
         ▼                      ▼
┌─────────────────┐    ┌─────────────────────────────────────────────────────┐
│  PostgreSQL 16  │    │  REACT 18 FRONTEND                                   │
│  + TimescaleDB  │    │                                                      │
│                 │    │  Dashboard  ·  Floor Map  ·  Alerts  ·  Reports      │
│  Redis 7.2      │    │  Zustand stores ← WebSocket hooks                   │
│                 │    │  React Query ← REST API                              │
│  S3 / MinIO     │    │  Leaflet GIS · Recharts · PDF viewer                │
└─────────────────┘    └─────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│  MONITORING STACK                                    │
│                                                      │
│  Prometheus (/metrics scrape every 15s)              │
│      ↓                                               │
│  Grafana (dashboards on :3001)                       │
│      ↓                                               │
│  Alertmanager → PagerDuty / Slack / Email            │
│                                                      │
│  Jaeger (distributed tracing, sampled at 10%)        │
└─────────────────────────────────────────────────────┘
```

---

## Data Flows

### Flow 1: Person Enters Frame → Attendance Update → Dashboard Push

```
1.  Camera streams frame to FFmpegReader (RTSP)
2.  Frame decoded and placed in FrameBuffer
3.  BatchProcessor collects frame with others; sends batch to YOLOv11
4.  YOLOv11 returns: [{class: "person", bbox: [...], confidence: 0.91}]
5.  ByteTrack assigns track_id: 2041 (new track, not seen before)
6.  Frame qualifies for face recognition (track age > 10, face area > 64px)
7.  RetinaFace locates face in person crop; ArcFace generates 512-dim embedding
8.  FAISS search returns: employee_id=E0342, similarity=0.87 (> 0.65 threshold)
9.  EventPublisher sends to RabbitMQ: evap.events, routing_key=face.recognized
    Message payload: {camera_id, track_id, employee_id, timestamp, zone_id}
10. detection_worker receives message:
    a. INSERT into detection_events (TimescaleDB)
    b. INSERT/UPDATE attendance_records (check-in if no record today)
    c. SET redis: employee:E0342:last_seen = {camera_id, timestamp, zone_id}
    d. INCR redis: zone:Z007:count (atomic increment of zone occupancy)
11. detection_worker publishes to evap.notifications (fanout):
    {event_type: "attendance.checkin", employee_id, name, camera_id, timestamp}
12. WebSocket manager receives from dashboard_push queue
13. Broadcasts to all clients subscribed to "dashboard:global" and "zone:Z007"
14. React dashboard updates: attendance count +1, zone occupancy badge updates
    Latency from physical event to dashboard: ~1.2 s (p95)
```

### Flow 2: Vehicle Enters → ANPR → Blacklist Check → ERP Sync

```
1.  YOLO detects class="car", confidence=0.94; ByteTrack assigns track_id
2.  Vehicle crop routed to ANPR sub-pipeline
3.  WPOD-Net detects plate region; applies perspective warp
4.  LPRNet reads plate: "MH12AB4567", combined confidence=0.91
5.  Redis lookup: plate:MH12AB4567:lookup → MISS (not cached)
6.  DB query: SELECT status, owner_name FROM vehicles WHERE plate='MH12AB4567'
    Result: {status: "blacklisted", owner_name: "Vendor Corp Ltd"}
7.  Result cached in Redis with 300s TTL
8.  EventPublisher publishes to evap.alerts, routing_key="blacklist":
    {camera_id, plate, status:"blacklisted", owner_name, timestamp}
9.  alert_worker receives:
    a. Dedup check: GET alert:dedup:{sha256(camera+plate)} → MISS (new event)
    b. SET alert:dedup:{hash} EX 300 (5-min dedup window)
    c. INSERT alert record, severity=HIGH
    d. Publish to evap.notifications: email + SMS queues + dashboard_push
10. Email notification sent to security team via SendGrid
11. SMS sent to on-duty guard via Twilio
12. Simultaneously, EventPublisher publishes to evap.events:
    routing_key="detection.vehicle.entry"
13. detection_worker also publishes to erp_sync_jobs queue:
    {event_type: "vehicle.entry", plate, camera_id, site_id, timestamp}
14. sync_worker receives ERP job:
    POST https://erp.company.com/api/vehicles/entry (HMAC-signed)
    Retries up to 3× with exponential backoff on failure
```

### Flow 3: Alert Triggered → Classification → Notification Delivery

```
1.  Zone rule engine (runs in detection_worker) evaluates event stream:
    zone:Z002:count = 47, zone.max_occupancy = 30 → CROWD rule triggered
2.  detection_worker publishes to evap.alerts, routing_key="crowd":
    {camera_id, zone_id, count:47, threshold:30, timestamp}
3.  alert_worker receives message:
    a. Rule classification: severity = "HIGH" (occupancy > 150% of limit)
    b. Dedup check: no duplicate within 5-min window
    c. INSERT alerts table: {type:"crowd_formation", severity:"HIGH", status:"active"}
    d. Publish to evap.notifications (fanout) with alert envelope
4.  dashboard_push consumer → WebSocket broadcast to all clients
    React alertStore adds alert; unread badge increments; alert panel slides open
5.  email_notifications consumer → SendGrid API:
    To: security-team@company.com
    Subject: [HIGH] Crowd Formation — Zone: Main Lobby (47 persons)
    Body: HTML template with camera snapshot attachment
6.  sms_notifications consumer → Twilio API:
    To: +91-XXXXXXXXXX (on-call guard)
    Body: "EVAP ALERT: Crowd in Main Lobby (47 persons). Camera: cam_002"
7.  If alert not acknowledged within SLA (default 10 min):
    Escalation task (Celery eta=+10min) fires → notifies supervisor via email
8.  Guard acknowledges via dashboard → PATCH /api/v1/alerts/{id}/acknowledge
    Alert status → "acknowledged"; escalation task revoked if pending
```

### Flow 4: Executive Report Request → PDF Generation → Email Delivery

```
1.  User clicks "Generate Report" on Reports page:
    POST /api/v1/reports/generate
    Body: {type:"monthly_summary", month:"2026-05", format:"pdf", recipients:["ceo@company.com"]}
2.  FastAPI validates request, creates report_jobs record (status=queued)
    Publishes Celery task: report_worker.generate_report.delay(report_id)
    Returns: {report_id: "rpt_8841", status: "queued"}
    Frontend polls GET /api/v1/reports/rpt_8841/status every 3s
3.  report_worker picks up task:
    a. Queries TimescaleDB continuous aggregates for attendance stats (daily rollups)
    b. Queries vehicle_events for entry/exit counts and ANPR hit rates
    c. Queries alerts table for incident summary and MTTR
    d. Queries camera uptime metrics from Prometheus via HTTP API
4.  Data assembled into ReportData dataclass; rendered into PDF via ReportLab:
    - Cover page with company logo and report period
    - KPI scorecard table (attendance rate, incidents, camera uptime)
    - Trend charts (matplotlib figures embedded as PNG in PDF)
    - Per-department attendance breakdown table
    - Incident log with resolution times
    - Camera health summary
5.  PDF uploaded to S3/MinIO: reports/{company_id}/2026-05-monthly.pdf
    Presigned URL generated (expires 7 days)
6.  report_worker updates report_jobs: status=completed, s3_url=...
    Publishes email job to evap.notifications
7.  email_notifications consumer → SendGrid:
    To: ceo@company.com
    Subject: EVAP Monthly Report — May 2026
    Body: "Your report is ready." + presigned download link
8.  Frontend polls → status=completed → renders download button + inline preview
```

---

## Scalability Design

### Single-Server Deployment (Up to 20 Cameras)

All components run as Docker Compose services on one physical server. The AI engine, FastAPI backend, and Celery workers share the same GPU. Recommended for pilots, small offices, and development.

```yaml
# docker-compose profile: single
services:
  ai_engine:       # 1 instance, 4 workers
  backend:         # 1 Uvicorn instance, 4 workers
  detection_worker: # concurrency=4
  alert_worker:    # concurrency=2
  report_worker:   # concurrency=1
  sync_worker:     # concurrency=2
  postgres:        # single instance
  redis:           # single instance
  rabbitmq:        # single instance
```

**Frame processing budget per camera:** At 10 FPS × 20 cameras = 200 FPS throughput. YOLOv11m at batch-8 on RTX 3080 achieves ~900 FPS (640×640, FP16) → headroom factor of 4.5×, leaving capacity for face recognition and ANPR sub-pipelines.

### Multi-Worker Deployment (20–100 Cameras)

AI engine runs on dedicated GPU node(s). Backend and workers scale horizontally. Docker Compose with multiple override files and a dedicated GPU host.

- **AI engine:** 2–4 instances across GPU nodes, each managing a camera subset assigned by the `CameraLoadBalancer`.
- **detection_worker:** Scale to 16 concurrency (or multiple containers).
- **PostgreSQL:** Promote to primary + 1 read replica. Read-heavy queries (reports, dashboards) directed to replica via `DATABASE_REPLICA_URL`.
- **Redis:** Redis Cluster or Sentinel (see HA section).

### Kubernetes Horizontal Scaling (100+ Cameras)

```yaml
# deploy/kubernetes/hpa/ai-engine-hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: ai-engine-hpa
spec:
  scaleTargetRef:
    kind: Deployment
    name: ai-engine
  minReplicas: 2
  maxReplicas: 20
  metrics:
    - type: External
      external:
        metric:
          name: evap_rabbitmq_queue_depth
          selector:
            matchLabels:
              queue_name: person_detections
        target:
          type: AverageValue
          averageValue: "500"   # scale up when backlog > 500 messages/pod
```

**Celery workers** scale via Kubernetes Deployments with HPA on `evap_rabbitmq_queue_depth` per queue type. Backend pods scale on CPU/memory with a minimum of 3 replicas for HA.

### Camera Load Distribution Algorithm

The `CameraLoadBalancer` (`ai_engine/pipeline/stream_reader.py`) assigns cameras to AI engine instances using a weighted round-robin algorithm that accounts for:

1. **Camera resolution** (4K cameras cost 4× a 1080p camera in compute budget).
2. **Detection zone complexity** (zones with small-object detection or ANPR enabled cost 2× a standard zone).
3. **Current GPU utilization** of each AI engine pod (polled from Prometheus every 30 s).

On rebalance (triggered by camera add/remove or AI pod scale event), cameras are redistributed with minimum disruption: only cameras that need to move are reassigned, preserving existing track histories where possible via Redis-persisted ByteTrack state.

### Database Read Replicas

```
                    ┌─────────────────────┐
Write path ────────→│  PostgreSQL Primary  │
                    └──────────┬──────────┘
                               │ streaming replication
                    ┌──────────▼──────────┐
Read path ─────────→│  PostgreSQL Replica  │
(reports, dashboards│  (hot standby)       │
 analytics queries) └─────────────────────┘
```

SQLAlchemy connection routing is implemented via a custom `RoutingSession` that directs `SELECT` statements from report/analytics endpoints to the replica URL and all writes to the primary.

---

## High Availability

### Redis Sentinel

For deployments requiring Redis HA without Redis Cluster complexity:

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Redis       │     │  Redis       │     │  Redis       │
│  Primary     │────→│  Replica 1   │────→│  Replica 2   │
│  :6379       │     │  :6380       │     │  :6381       │
└──────────────┘     └──────────────┘     └──────────────┘
       │                    │                    │
┌──────▼────────────────────▼────────────────────▼───────┐
│         Redis Sentinel × 3 (:26379)                    │
│   Monitors primary; promotes replica on failure         │
│   Quorum: 2 (majority must agree on failover)          │
└────────────────────────────────────────────────────────┘
```

EVAP connects to Redis via `redis-py` with Sentinel support. Failover is transparent to the application; `redis.sentinel.Sentinel` resolves the current primary at connection time.

### PostgreSQL Streaming Replication

Primary is configured with `wal_level=replica`, `max_wal_senders=5`. Replica runs in hot-standby mode with `hot_standby=on`. Replication lag is monitored via Prometheus (`pg_replication_lag_seconds` from `postgres_exporter`). Alertmanager fires if lag exceeds 10 seconds.

Failover is manual for small deployments; for Kubernetes deployments, **Patroni** manages automatic failover with etcd as DCS.

### RabbitMQ Mirrored Queues

All critical queues use Quorum Queues (RabbitMQ 3.9+) rather than classic mirrored queues:

```bash
# Applied at queue declaration in aio-pika
arguments={
    "x-queue-type": "quorum",
    "x-delivery-limit": 3,
    "x-dead-letter-exchange": "evap.dlx"
}
```

RabbitMQ is deployed as a 3-node cluster in Kubernetes using the `rabbitmq/cluster-operator`. Quorum queues replicate to all 3 nodes; writes require acknowledgment from a majority (2/3) before confirming to the publisher.

### Celery Worker Redundancy

Celery workers are stateless; any number of replicas can run concurrently consuming the same queues. Task deduplication (for idempotent tasks like attendance record upserts) is handled by the `alert:dedup:*` Redis keys, not by Celery's built-in mechanisms. If a worker crashes mid-task, `acks_late=True` causes RabbitMQ to redeliver the message to another worker.

### Health Check Endpoints

```
GET /health          → {"status": "ok", "version": "4.0.0"}
GET /health/live     → 200 if process is alive (Kubernetes liveness probe)
GET /health/ready    → 200 if DB + Redis + RabbitMQ are reachable (readiness probe)
GET /health/detailed → full component status with latency measurements
```

---

## Security Architecture

### JWT Authentication

EVAP uses **RS256** asymmetric JWT tokens. The private key signs tokens (held only by the backend); the public key verifies them (can be distributed to microservices without exposing signing capability).

| Token Type | Lifetime | Storage | Purpose |
|---|---|---|---|
| Access token | 15 minutes | Memory only (JS variable) | Bearer auth for API calls |
| Refresh token | 7 days | HttpOnly Secure cookie | Obtain new access tokens |

Token refresh flow: when an API call returns 401, the frontend automatically calls `POST /api/v1/auth/refresh` with the HttpOnly cookie. The backend validates the refresh token against the database (stored hashed with `bcrypt`), checks it hasn't been revoked, and issues a new access token.

**Logout** immediately revokes the refresh token in the database and adds the access token's JTI to the Redis blacklist (`session:{jti}` with TTL matching remaining token lifetime).

### RBAC Middleware

Roles are stored in PostgreSQL; permissions are evaluated in a FastAPI dependency:

```python
# backend/app/api/v1/deps.py
async def require_permission(permission: str):
    async def dependency(current_user = Depends(get_current_user)):
        if permission not in current_user.permissions:
            raise HTTPException(403, "Insufficient permissions")
        return current_user
    return dependency

# Usage in endpoint
@router.delete("/cameras/{camera_id}",
    dependencies=[Depends(require_permission("cameras:delete"))])
```

Predefined roles: `super_admin`, `security_manager`, `security_operator`, `hr_manager`, `executive_viewer`, `api_client`. Custom roles can be created via the Settings page.

### RTSP URL Encryption

Camera RTSP URLs (which contain credentials) are never stored in plaintext. They are encrypted with **Fernet** (AES-128-CBC + HMAC-SHA256) using a key derived from `SECRET_KEY` via PBKDF2:

```python
# backend/app/core/security.py
from cryptography.fernet import Fernet
import base64, hashlib

def get_fernet() -> Fernet:
    key = hashlib.pbkdf2_hmac("sha256", SECRET_KEY.encode(), b"evap-rtsp-salt", 100_000)
    return Fernet(base64.urlsafe_b64encode(key[:32]))

def encrypt_rtsp_url(url: str) -> str:
    return get_fernet().encrypt(url.encode()).decode()

def decrypt_rtsp_url(token: str) -> str:
    return get_fernet().decrypt(token.encode()).decode()
```

The decrypted URL is used only at stream connection time and is never serialized to a response body.

### TLS Termination

Nginx terminates TLS at the ingress. Backend services communicate over the internal Docker/Kubernetes network without TLS. Configuration in `deploy/nginx/nginx.conf`:

```nginx
server {
    listen 443 ssl http2;
    ssl_certificate     /etc/ssl/evap/cert.pem;
    ssl_certificate_key /etc/ssl/evap/key.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_session_cache   shared:SSL:10m;

    location /api/ { proxy_pass http://backend:8000; }
    location /ws/  { proxy_pass http://backend:8000; proxy_http_version 1.1;
                     proxy_set_header Upgrade $http_upgrade;
                     proxy_set_header Connection "upgrade"; }
    location /     { root /usr/share/nginx/html; try_files $uri /index.html; }
}
```

### Audit Log Pipeline

Every state-changing API request is recorded in the `audit_logs` table via a FastAPI middleware:

```
Request → AuthMiddleware (resolve user) → AuditMiddleware → Route Handler
                                               ↓
                                     BackgroundTask:
                                     INSERT audit_logs {
                                       user_id, action, resource_type,
                                       resource_id, ip_address, user_agent,
                                       request_body_hash, timestamp
                                     }
```

Audit logs are append-only (no UPDATE/DELETE permissions granted on the table at the DB level). They are exported nightly to S3 as JSONL for long-term compliance retention.

---

## Integration Points

### ERP Webhook Format

EVAP pushes events to ERP systems via signed HTTPS POST requests. The signature uses HMAC-SHA256 of the request body with a shared secret configured per integration:

```http
POST https://erp.company.com/api/evap/events
Content-Type: application/json
X-EVAP-Signature: sha256=<hmac_hex>
X-EVAP-Timestamp: 1750000000

{
  "event_id": "evt_7f3a2c",
  "event_type": "attendance.checkin",
  "timestamp": "2026-06-15T09:14:32Z",
  "data": {
    "employee_id": "E0342",
    "employee_code": "EMP-0342",
    "camera_id": "cam_042",
    "site_code": "HQ-MUMBAI",
    "shift_id": "MORNING",
    "confidence": 0.87
  }
}
```

The ERP endpoint must respond with `200 OK` within 10 seconds. On failure, `sync_worker` retries with exponential backoff: delays of 30 s, 2 min, 10 min, 1 hour. After 4 failures, the job is moved to DLQ and an alert is raised.

### External Alert Webhooks

Third-party systems (access control, building management) can subscribe to EVAP alert webhooks via the Settings → Integrations page. On alert creation, EVAP fans out to all registered webhook URLs:

```json
{
  "webhook_version": "1.0",
  "alert_id": "alt_9902",
  "alert_type": "blacklist_vehicle",
  "severity": "HIGH",
  "camera_id": "cam_015",
  "camera_name": "Parking Gate North",
  "timestamp": "2026-06-15T11:22:00Z",
  "metadata": {
    "plate": "MH12AB4567",
    "zone": "parking_north"
  }
}
```

### REST API for Third-Party Integrations

EVAP exposes a versioned REST API (`/api/v1/`) with API key authentication for machine-to-machine integrations. API keys are created in Settings → API Keys and sent as `Authorization: ApiKey <key>` header.

Key endpoints for integration use cases:

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/attendance/daily` | GET | Retrieve attendance records for a date range |
| `/api/v1/vehicles/events` | GET | Query vehicle entry/exit events |
| `/api/v1/alerts` | GET | List alerts with filters (type, severity, date) |
| `/api/v1/cameras/{id}/snapshot` | GET | Get latest frame JPEG from a camera |
| `/api/v1/visitors` | GET / POST | Query or create visitor records |
| `/api/v1/zones/{id}/occupancy` | GET | Current occupancy count for a zone |

Rate limiting: 1,000 requests/minute per API key. Rate limit headers (`X-RateLimit-Remaining`, `X-RateLimit-Reset`) are included in all responses.

### ONVIF Camera Management

EVAP uses the `onvif-zeep` library for ONVIF-compliant cameras. Supported operations:

| ONVIF Operation | EVAP Usage |
|---|---|
| `GetCapabilities` | Discover supported ONVIF services on camera onboarding |
| `GetProfiles` | Enumerate video streams and select optimal profile for analytics |
| `GetStreamUri` | Resolve RTSP URL programmatically from camera IP |
| `GetDeviceInformation` | Populate camera make/model/firmware fields |
| `WS-Discovery` | Auto-discover cameras on the same subnet during site setup |
| `AbsoluteMove` / `RelativeMove` | PTZ control from camera detail page |
| `SetSynchronizationPoint` | Reset motion detection baseline after configuration change |

ONVIF discovery runs as a periodic task every 5 minutes in development mode, and on-demand (triggered from Settings → Discover Cameras) in production to avoid broadcast storms on large networks.
