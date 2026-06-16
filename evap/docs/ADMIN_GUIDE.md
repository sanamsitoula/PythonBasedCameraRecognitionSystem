# EVAP Administrator Guide

**Enterprise Video Analytics Platform — Administrator Reference**
Version 1.0 | Last Updated: June 2026 | For EVAP Operators with Admin or Super Admin role

---

## Table of Contents

1. [User Management](#1-user-management)
2. [Roles and Permissions](#2-roles-and-permissions)
3. [Site Configuration](#3-site-configuration)
4. [Camera Management](#4-camera-management)
5. [Employee Management](#5-employee-management)
6. [Alert Configuration](#6-alert-configuration)
7. [ERP Integration](#7-erp-integration)
8. [Backup Management](#8-backup-management)
9. [Monitoring Dashboard](#9-monitoring-dashboard)
10. [System Maintenance](#10-system-maintenance)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. User Management

### 1.1 Creating Users via UI

1. Navigate to **Settings → Users → Invite User**.
2. Enter the user's email address and select a role.
3. Optionally set a site restriction (user will only see cameras/data from that site).
4. Click **Send Invitation**. The user receives an email with a one-time setup link valid for 48 hours.
5. The user sets their own password and optionally enrolls MFA before first login.

### 1.2 Creating Users via API

```bash
TOKEN="your_admin_jwt_token"

curl -s -X POST http://localhost:8000/api/v1/users/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "jane.ops@company.com",
    "full_name": "Jane Smith",
    "role": "operator",
    "site_ids": ["site-uuid-1", "site-uuid-2"],
    "send_invite_email": true
  }' | python3 -m json.tool
```

### 1.3 Role Assignment

Roles can be changed at any time from **Settings → Users → [User] → Edit Role**. A user can only be assigned a role equal to or below the assigning admin's own role. Super Admin is the only role that can grant Admin.

### 1.4 Password Policy

Configured in **Settings → Security → Password Policy**:

| Setting | Default Value | Description |
|---------|--------------|-------------|
| Minimum length | 12 characters | Reject shorter passwords |
| Require uppercase | Yes | At least one A–Z character |
| Require number | Yes | At least one 0–9 digit |
| Require symbol | Yes | At least one `!@#$%^&*` |
| Max password age | 90 days | Force reset after expiry |
| Password history | 5 | Cannot reuse last 5 passwords |
| Failed login lockout | 5 attempts → 15-minute lockout | Brute-force protection |

### 1.5 MFA (TOTP) Setup

EVAP uses Time-based One-Time Passwords (TOTP) compatible with Google Authenticator, Authy, and 1Password.

**User self-enrollment flow:**
1. User logs in, navigates to **Profile → Security → Enable 2FA**.
2. A QR code is displayed. User scans with authenticator app.
3. User enters the 6-digit code to confirm enrollment.
4. User is shown 8 one-time backup codes — these must be saved securely.
5. All subsequent logins require the TOTP code after password.

**Admin-enforced MFA:**
- Navigate to **Settings → Security → Require MFA** and select roles (recommended: all roles except Viewer).
- Users in those roles are redirected to MFA setup on next login.

**Resetting a user's MFA (lost device):**
```bash
# Via API (Super Admin only)
curl -s -X DELETE "http://localhost:8000/api/v1/users/{user_id}/mfa" \
  -H "Authorization: Bearer $TOKEN"
# User's MFA is cleared; they receive a reset email
```

### 1.6 User Deactivation vs Deletion

| Action | Effect | Reversible? |
|--------|--------|-------------|
| **Deactivate** | User cannot log in; all data (events attributed to user, audit logs) retained | Yes — re-activate at any time |
| **Delete** | Account removed; events retain user name as text string; face enrollment data deleted | No (soft-delete with 30-day recovery window) |

Prefer **deactivation** for offboarding. Reserve deletion for GDPR erasure requests (see Section 5.5).

**Deactivate via UI:** Settings → Users → [User] → Deactivate

**Deactivate via API:**
```bash
curl -s -X PATCH "http://localhost:8000/api/v1/users/{user_id}" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"is_active": false}'
```

### 1.7 Bulk User Import via CSV

1. Download the import template from **Settings → Users → Import → Download Template**.
2. Fill in the CSV with the following columns:

```csv
email,full_name,role,department,site_name,employee_id
john.doe@company.com,John Doe,operator,Security,Main Campus,EMP001
jane.smith@company.com,Jane Smith,viewer,HR,Branch Office,EMP002
```

3. Upload via **Settings → Users → Import → Upload CSV**.
4. Review the preview screen showing validation results (rows with errors are highlighted).
5. Click **Confirm Import**. Invitation emails are sent to all valid entries.

---

## 2. Roles and Permissions

### 2.1 Role Definitions

| Role | Intended For |
|------|-------------|
| **Super Admin** | Platform owner; full control including system config and license management |
| **Admin** | IT / Security Manager; manages users, sites, cameras, and integrations |
| **Operator** | Security/Control room staff; monitors cameras, acknowledges alerts |
| **Viewer** | Management; read-only dashboards and reports |
| **API User** | Automated systems and integrations; no UI access |

### 2.2 Permission Matrix

| Permission | Super Admin | Admin | Operator | Viewer | API User |
|------------|:-----------:|:-----:|:--------:|:------:|:--------:|
| `manage_users` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `manage_roles` | ✅ | ❌ | ❌ | ❌ | ❌ |
| `manage_sites` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `manage_cameras` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `view_live_feed` | ✅ | ✅ | ✅ | ✅ | via API |
| `control_ptz` | ✅ | ✅ | ✅ | ❌ | ❌ |
| `view_recordings` | ✅ | ✅ | ✅ | ✅ | via API |
| `view_attendance` | ✅ | ✅ | ✅ | ✅ | via API |
| `manage_employees` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `manage_face_enrollment` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `export_data` | ✅ | ✅ | ✅ | ❌ | via API |
| `view_alerts` | ✅ | ✅ | ✅ | ✅ | via API |
| `manage_alerts` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `acknowledge_alerts` | ✅ | ✅ | ✅ | ❌ | ❌ |
| `view_reports` | ✅ | ✅ | ✅ | ✅ | via API |
| `manage_erp_integration` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `view_erp_sync_logs` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `system_config` | ✅ | ❌ | ❌ | ❌ | ❌ |
| `manage_backups` | ✅ | ❌ | ❌ | ❌ | ❌ |
| `view_audit_logs` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `manage_api_keys` | ✅ | ✅ | ❌ | ❌ | ❌ |

> **API User** role accesses only endpoints explicitly scoped to the API key's granted permissions. Create separate API keys with minimal scope per integration.

---

## 3. Site Configuration

### 3.1 Adding a New Site

Navigate to **Settings → Sites → Add Site** and fill in:

| Field | Notes |
|-------|-------|
| Site Name | Unique; appears in all reports and camera lists |
| Address | Full street address; used in exported PDF reports |
| **Timezone** | Critical — all attendance timestamps, shift times, and alert schedules are interpreted in this timezone. Wrong timezone will corrupt attendance records. Use IANA format (e.g., `Asia/Dhaka`, `Asia/Dubai`, `Europe/London`) |
| Country | Affects public holiday calendar if integrated |
| Site Contact | Phone and email of on-site manager |
| Capacity | Maximum occupancy; used for crowd alert thresholds |

### 3.2 Adding Buildings and Floors

Within a site, create the physical hierarchy:

1. **Settings → Sites → [Site] → Buildings → Add Building**
   - Building name, number of floors, year built (optional)
2. **Settings → Sites → [Site] → Buildings → [Building] → Floors → Add Floor**
   - Floor name (e.g., "Ground Floor", "Level 2")
   - **Upload Floor Plan Image:** PNG or SVG, recommended 2000×1500px or higher
   - Floor plan is displayed in the Zone Editor and live map view

### 3.3 Configuring Zones

Zones define areas on a floor plan for occupancy tracking and intrusion alerts.

1. Navigate to **Settings → Sites → [Site] → [Building] → [Floor] → Zone Editor**.
2. The uploaded floor plan is displayed as a canvas.
3. Click **Draw Zone** and use the polygon tool to trace the zone boundary.
4. Configure zone properties:

| Property | Description |
|----------|-------------|
| Zone Name | Unique per floor (e.g., "Server Room", "Cafeteria") |
| Zone Type | `restricted`, `public`, `emergency_exit`, `parking` |
| Capacity Limit | Alert fires when occupancy exceeds this number |
| Authorized Groups | Only these employee groups are permitted (for `restricted` zones) |
| Working Hours Restriction | Optionally restrict access to zone only during shift hours |
| Color | Visual identifier on live map |

5. Assign cameras to zones: each camera can cover one or more zones.

### 3.4 Site-Level Settings

Navigate to **Settings → Sites → [Site] → Configuration**:

- **Working Hours:** Default shift start/end times used for attendance calculation when no individual shift is assigned.
- **Public Holidays:** Upload a CSV of dates or sync with Google Calendar / Outlook.
- **Overtime Threshold:** Minutes after shift end before overtime is flagged.
- **Late Arrival Grace Period:** Minutes after shift start before marking "late".
- **Data Retention:** How long to keep video snapshots and event logs for this site (default: 90 days for snapshots, 2 years for events).

---

## 4. Camera Management

### 4.1 Adding a Camera

Navigate to **Cameras → Add Camera** and fill in:

| Field | Notes |
|-------|-------|
| Camera Name | Unique, descriptive (e.g., "Lobby-East-PTZ-01") |
| RTSP URL | Full URL including credentials — stored encrypted at rest (AES-256) |
| Site / Building / Floor / Zone | Physical location assignment |
| Resolution | Select from: 1080p, 4K, 720p (used to set decode parameters) |
| Frame Rate | 15 or 25 FPS recommended for AI processing |
| Is PTZ? | Enables PTZ control panel in live view |
| Recording Mode | `continuous`, `motion_triggered`, `ai_event_triggered` |
| Retention Days | Override site default per camera |

> **Security note:** RTSP URLs containing passwords are never returned in API responses or displayed after saving. Use the **Test Connection** button immediately after adding.

### 4.2 Camera Health Monitoring

Camera health is visible on the **Cameras** dashboard and via API:

```bash
curl -s "http://localhost:8000/api/v1/cameras/health-summary" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
# {
#   "total": 24,
#   "streaming": 22,
#   "offline": 1,
#   "degraded": 1,    ← streaming but high packet loss
#   "ai_active": 21
# }
```

Health indicators per camera:

| Status | Meaning |
|--------|---------|
| `streaming` | RTSP connected, frames being decoded |
| `offline` | RTSP connection failed |
| `degraded` | Connected but frame drops > 10% or FPS below threshold |
| `ai_active` | AI pipeline running and producing detections |
| `ai_paused` | Stream connected but AI disabled (e.g., outside working hours) |

### 4.3 Configuring AI Per Camera

Each camera can have a different set of AI models enabled to optimize GPU usage:

Navigate to **Cameras → [Camera] → AI Configuration**:

| Model | GPU Cost | Use When |
|-------|---------|----------|
| Person Detection (YOLOv11) | Low | All cameras |
| Face Recognition (InsightFace) | High | Entry/exit points, high-security zones |
| Vehicle Detection (YOLOv11) | Low | Parking lots, perimeter |
| ANPR | Medium | Vehicle entry gates |
| Crowd Detection | Low | Lobbies, cafeterias |
| Loitering Detection | Low | ATMs, restricted corridors |

### 4.4 Camera Groupings and Views

Create named **Views** (multi-camera grid layouts) for the control room:

1. Navigate to **Live View → Manage Views → New View**.
2. Select layout (2×2, 3×3, 4×4, or custom grid).
3. Drag cameras from the list into grid slots.
4. Save with a name (e.g., "Main Lobby Overview").
5. Views can be shared across operators or set as default for a site.

### 4.5 PTZ Camera Control

PTZ (Pan-Tilt-Zoom) controls appear in the live view panel when a camera is marked as PTZ:

- **Directional arrows:** 8-direction movement
- **Zoom slider:** Optical zoom in/out
- **Presets:** Save and recall named positions (e.g., "Entrance Wide", "Registration Desk Close-up")
- **Auto-tour:** Cycle through presets on a schedule

PTZ commands are sent via the backend to the camera using ONVIF PTZ service. Ensure the camera's ONVIF port (typically 80 or 8080) is accessible from the EVAP server.

### 4.6 Testing an RTSP Stream

Before deploying a camera, test the stream from the server:

```bash
# Test with FFprobe (fastest, no decode)
ffprobe -v error -rtsp_transport tcp \
  -i "rtsp://admin:password@192.168.1.100:554/Streaming/Channels/101" \
  -show_entries stream=width,height,codec_name,r_frame_rate \
  -of csv=p=0

# Expected output:
# video,1920,1080,h264,25/1

# Full playback test (5 seconds)
ffplay -t 5 -rtsp_transport tcp \
  "rtsp://admin:password@192.168.1.100:554/Streaming/Channels/101"
```

---

## 5. Employee Management

### 5.1 Manual Employee Entry

Navigate to **Employees → Add Employee**:

| Field | Required | Notes |
|-------|----------|-------|
| Full Name | Yes | |
| Employee ID | Yes | Must match payroll/ERP system ID |
| Email | Yes | Used for personal attendance reports |
| Department | Yes | Pre-defined departments from Settings |
| Designation | No | Job title |
| Site | Yes | Primary work site |
| Shift | Yes | Assigned shift schedule |
| Join Date | Yes | Attendance tracking starts from this date |
| Access Groups | No | Used for zone access control |
| Photo | Recommended | Used as face enrollment source |

### 5.2 Bulk Import via CSV/Excel

Download the import template: **Employees → Import → Download Template**

Template columns:
```csv
employee_id,full_name,email,department,designation,site_name,shift_name,join_date,access_groups
EMP001,Ahmed Hassan,ahmed@company.com,Security,Guard,Main Campus,Morning Shift,2024-01-15,security;reception
EMP002,Sara Al-Rashid,sara@company.com,HR,Manager,Branch Office,Office Hours,2024-03-01,
```

- `access_groups`: semicolon-separated list of group names
- `shift_name` must exactly match a shift configured in **Settings → Shifts**
- Date format: `YYYY-MM-DD`

Import steps:
1. **Employees → Import → Upload File** (CSV or XLSX)
2. Map columns if headers differ from template
3. Review validation report — errors shown per row
4. Click **Import Valid Rows** (invalid rows are skipped with an error report)

### 5.3 Face Enrollment Process

Face enrollment enables attendance tracking and access control via facial recognition.

**Photo Requirements:**
- Minimum resolution: 640×480 px
- Face must occupy at least 30% of image area
- Frontal face (±15° yaw, ±10° pitch)
- Even lighting, no heavy shadows on face
- No sunglasses or face coverings
- Accepted formats: JPG, PNG
- Multiple photos per employee improve recognition accuracy (recommended: 3–5 photos from slightly different angles)

**Enrollment via UI:**
1. Navigate to **Employees → [Employee] → Face Enrollment**.
2. Click **Upload Photos** and select 1–5 photos.
3. EVAP runs a quality check; photos failing quality thresholds are flagged.
4. Click **Enroll** to generate and store the face embedding vector.
5. Status changes to **Enrolled** with a confidence score.

**Enrollment quality thresholds** (configurable in Settings → AI → Face Recognition):

| Parameter | Default | Reject If |
|-----------|---------|-----------|
| Min face size (px) | 112×112 | Face bounding box smaller |
| Blur score | 0.7 | Laplacian variance below threshold |
| Brightness | 40–220 | Mean pixel outside range |
| Occlusion score | 0.8 | Eyes or mouth heavily covered |

### 5.4 Department and Shift Configuration

**Departments:** Settings → Organization → Departments → Add Department
- Name, parent department (for hierarchy), default site, cost center code

**Shifts:** Settings → Organization → Shifts → Add Shift

| Field | Example |
|-------|---------|
| Shift Name | Morning Shift |
| Start Time | 08:00 |
| End Time | 17:00 |
| Grace Period (Late) | 10 minutes |
| Grace Period (Early Out) | 10 minutes |
| Break Duration | 60 minutes |
| Days | Mon, Tue, Wed, Thu, Fri |
| Overtime Threshold | 60 minutes after shift end |

Rotating / night shifts are supported. Contact support@beamlab.dev for shift pattern configuration.

### 5.5 Employee Deactivation and Face Data Deletion (GDPR)

**Deactivation** (standard offboarding):
1. **Employees → [Employee] → Deactivate**
2. Face recognition stops matching this employee immediately
3. Historical attendance records and events are retained
4. Can be reactivated if employee returns

**Full Data Deletion** (GDPR erasure request):
```bash
# This permanently deletes face embeddings, photos, and personal data
# Attendance records are anonymized (employee_id replaced with a hash)
curl -s -X DELETE "http://localhost:8000/api/v1/employees/{employee_id}?gdpr_erase=true" \
  -H "Authorization: Bearer $TOKEN"
# Requires Super Admin role
# Returns a deletion certificate with timestamp for compliance records
```

---

## 6. Alert Configuration

### 6.1 Alert Rule Types

| Rule Type | Trigger |
|-----------|---------|
| **Occupancy Threshold** | Zone occupancy exceeds or drops below a count |
| **Unauthorized Zone Access** | Person not in authorized group enters a restricted zone |
| **Loitering** | Person remains in a zone longer than N seconds without exit |
| **Crowd Formation** | N or more people clustered within a radius in a short period |
| **Blacklisted Vehicle** | ANPR matches a plate in the blacklist |
| **Unrecognized Person** | Face not matched to any enrolled employee (configurable confidence threshold) |
| **Attendance Anomaly** | Employee absent, late, or leaving early beyond threshold |
| **Camera Offline** | Camera stops streaming for more than N minutes |
| **Perimeter Breach** | Person or vehicle detected in a defined exterior zone after hours |

### 6.2 Creating an Alert Rule

1. Navigate to **Alerts → Rules → Create Rule**.
2. Select **Rule Type** and configure type-specific parameters:

   *Example: Unauthorized Zone Access*
   ```
   Rule Name:        Server Room Intrusion
   Camera(s):        Server Room Cam 1
   Zone:             Server Room
   Trigger:          Person detected in zone + NOT in group "IT Staff"
   Working Hours:    All hours (24/7)
   Severity:         Critical
   Cooldown Period:  5 minutes (suppress repeat alerts within this window)
   ```

3. Assign **Notification Channels** (see 6.4).
4. Set **Escalation Rules** (see 6.5).
5. Click **Save and Enable**.

### 6.3 Notification Channels

| Channel | Setup Location | Notes |
|---------|---------------|-------|
| Email (SMTP) | Settings → Notifications → Email | Requires SMTP config in .env |
| SMS (Twilio) | Settings → Notifications → SMS | Requires `TWILIO_*` env vars |
| Push (FCM) | Settings → Notifications → Push | Requires Firebase project; user must have EVAP mobile app installed |
| Webhook | Settings → Notifications → Webhook | POST JSON payload to any URL |
| In-App | Always on | Real-time alerts in dashboard notification bell |

### 6.4 Configuring Each Notification Channel

**Email (SMTP):**
Configured via `.env` variables:
```dotenv
SMTP_HOST=smtp.mailgun.org
SMTP_PORT=587
SMTP_USERNAME=postmaster@mg.yourdomain.com
SMTP_PASSWORD=your_password
SMTP_FROM_EMAIL=alerts@yourdomain.com
SMTP_TLS=true
```
Test: **Settings → Notifications → Email → Send Test Email**

**SMS (Twilio):**
```dotenv
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_FROM_NUMBER=+15551234567
```
Test: **Settings → Notifications → SMS → Send Test SMS** (enter a mobile number)

**Push (FCM):**
```dotenv
FCM_SERVER_KEY=AAAAxxxxxx:APA91bxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```
Requires the EVAP mobile app installed on the recipient's device. Recipients must grant notification permission and be logged in.

**Webhook:**
Alert payload format:
```json
{
  "alert_id": "alert-uuid",
  "rule_name": "Server Room Intrusion",
  "severity": "critical",
  "camera_name": "Server Room Cam 1",
  "site_name": "Main Campus",
  "triggered_at": "2026-06-15T14:32:11Z",
  "snapshot_url": "https://evap.yourdomain.com/media/snapshots/alert-uuid.jpg",
  "details": {
    "zone": "Server Room",
    "person_count": 1,
    "recognized_employee": null
  }
}
```
Configure webhook URL, optional Bearer token for authentication, and retry policy (default: 3 retries with exponential backoff).

### 6.5 Alert Escalation Rules

Escalation sends a second (or third) notification to a different channel or recipient if the alert is not acknowledged within a time limit.

**Example escalation chain:**
```
Level 1 — Immediately:        Email → on-duty@company.com
Level 2 — After 5 minutes:    SMS → +971501234567 (Shift Supervisor)
Level 3 — After 15 minutes:   Email + SMS → security.manager@company.com
```

Configure at **Alerts → Rules → [Rule] → Escalation** by adding levels with time delays and channels.

### 6.6 Alert Suppression Schedules (Maintenance Windows)

Suppress alerts during planned maintenance to avoid noise:

1. Navigate to **Alerts → Suppression → New Window**.
2. Select affected cameras or sites.
3. Set start and end datetime.
4. Optionally set a recurrence (e.g., every Sunday 02:00–04:00 for scheduled maintenance).
5. Add a reason note (shown in audit logs).

Suppressed alerts are still logged in the database but do not trigger notifications.

---

## 7. ERP Integration

### 7.1 Supported ERPs

| ERP | Version | Integration Type |
|-----|---------|-----------------|
| **Odoo** | 17+ | OAuth2 REST API |
| **SAP HR** | S/4HANA 2023+ | RFC/BAPI (Python pyrfc) |
| **Generic HRMS** | Any | REST API (configurable) |

### 7.2 Odoo 17 Integration

**Prerequisites in Odoo:**
- Install modules: `hr`, `hr_attendance`, `hr_biometric_attendance` (community)
- Create an OAuth2 application: Settings → Technical → OAuth Providers → New

**Configuration in EVAP:**
```dotenv
ODOO_URL=https://odoo.yourdomain.com
ODOO_DATABASE=your_odoo_db_name
ODOO_CLIENT_ID=evap_integration_client_id
ODOO_CLIENT_SECRET=evap_integration_client_secret
```

**EVAP → Odoo data flow:**
- EVAP pushes attendance check-in/check-out events to Odoo `hr.attendance` in real time
- EVAP pulls employee records (name, ID, department, designation) from Odoo on a nightly batch sync

**Setup steps:**
1. Enter Odoo credentials in **Settings → Integrations → Odoo**.
2. Click **Test Connection** — should return employee count and Odoo version.
3. Click **Run Initial Employee Sync** to import all active employees.
4. Enable **Real-time Attendance Push** toggle.

### 7.3 SAP HR Integration

**Prerequisites:**
- SAP RFC/BAPI access enabled: `HRPAD00EMPREL` BAPI for employee reads; custom BAPI or IDoc for attendance writes (coordinate with SAP BASIS team)
- Python `pyrfc` library installed (requires SAP NW RFC SDK)

```dotenv
SAP_HOST=sap.yourdomain.com
SAP_SYSNR=00
SAP_CLIENT=100
SAP_USER=EVAP_RFC_USER
SAP_PASSWORD=rfc_user_password
SAP_LANG=EN
```

Setup: **Settings → Integrations → SAP HR → Configure → Test RFC Connection**

### 7.4 Sync Schedules

| Sync Type | Direction | Schedule | Trigger |
|-----------|-----------|----------|---------|
| Attendance event | EVAP → ERP | Real-time | Each face recognition check-in/out |
| Employee roster | ERP → EVAP | Nightly 02:00 (site timezone) | Batch cron |
| Department/shift updates | ERP → EVAP | Nightly 02:00 | Batch cron |
| Employee deactivations | ERP → EVAP | Nightly 02:00 | Batch cron |

### 7.5 Monitoring Sync Health

Navigate to **Settings → Integrations → [ERP] → Sync Logs**:

- Green: last sync succeeded
- Yellow: partial sync (some records had errors — see error detail)
- Red: last sync failed entirely

Key metrics shown:
- Records synced in last run
- Last successful sync timestamp
- Error count and error details (expandable per record)

API endpoint for monitoring:
```bash
curl -s "http://localhost:8000/api/v1/integrations/odoo/sync-status" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
# {
#   "last_sync": "2026-06-15T02:01:34Z",
#   "status": "success",
#   "employees_synced": 312,
#   "attendance_events_pushed": 48,
#   "errors": []
# }
```

### 7.6 Manual Re-sync

Trigger an out-of-schedule sync from the UI: **Settings → Integrations → [ERP] → Run Sync Now**

Or via API:
```bash
curl -s -X POST "http://localhost:8000/api/v1/integrations/odoo/sync" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"sync_type": "employees"}'
```

---

## 8. Backup Management

### 8.1 Backup Configuration

Navigate to **Settings → System → Backups**:

| Setting | Recommended Value |
|---------|------------------|
| Database backup schedule | Daily at 01:00 (site timezone) |
| Backup retention | 30 days |
| Backup destination | S3 or S3-compatible (MinIO) |
| S3 bucket | `evap-backups-prod` |
| Encryption | AES-256 (enabled by default) |
| Backup test schedule | Weekly (automated restore test to staging) |

### 8.2 Automated pg_dump to S3

The backup Celery task runs `pg_dump` and streams directly to S3. No intermediate local file is written.

```bash
# Manual trigger
docker compose exec backend python -m scripts.backup_now
# Starting backup: evap_2026-06-15T010000Z.sql.gz.enc
# Uploading to s3://evap-backups-prod/database/2026/06/15/...
# Backup complete. Size: 2.3 GB. Duration: 94s.
```

Backup files are named: `evap_{YYYY-MM-DDTHHMMSSZ}.sql.gz.enc`

### 8.3 Snapshot File Retention

Video snapshots (event thumbnails) are stored in S3 with a lifecycle policy:
- Snapshots older than the configured retention period are automatically deleted
- Configure in **Settings → System → Storage → Snapshot Retention**

Set the S3 lifecycle rule directly (more reliable than application-level cleanup):
```json
{
  "Rules": [{
    "ID": "evap-snapshot-expiry",
    "Filter": {"Prefix": "media/snapshots/"},
    "Status": "Enabled",
    "Expiration": {"Days": 90}
  }]
}
```

### 8.4 Testing the Restore Procedure

Test restore monthly. Full procedure:

```bash
# 1. List available backups
aws s3 ls s3://evap-backups-prod/database/ --recursive | tail -10

# 2. Download latest backup
aws s3 cp s3://evap-backups-prod/database/2026/06/15/evap_2026-06-15T010000Z.sql.gz.enc /tmp/

# 3. Decrypt
openssl enc -d -aes-256-cbc -in /tmp/evap_2026-06-15T010000Z.sql.gz.enc \
  -out /tmp/evap_restore.sql.gz \
  -pass file:/etc/evap/backup_encryption_key

# 4. Restore to staging database
gunzip -c /tmp/evap_restore.sql.gz | psql -U evap -d evap_staging -h staging-db-host

# 5. Run schema validation
psql -U evap -d evap_staging -c "SELECT COUNT(*) FROM employees;"
psql -U evap -d evap_staging -c "SELECT COUNT(*) FROM cameras;"
psql -U evap -d evap_staging -c "SELECT MAX(created_at) FROM attendance_events;"

# 6. Document test results in the backup test log
```

### 8.5 RTO/RPO Targets

| Metric | Target | Notes |
|--------|--------|-------|
| **RPO** (Recovery Point Objective) | 1 hour | Maximum data loss acceptable; daily backup + WAL archiving covers this |
| **RTO** (Recovery Time Objective) | 4 hours | Time to restore from backup and resume operations |

For sub-1-hour RPO, enable **PostgreSQL WAL archiving to S3** (continuous backup). Contact support@beamlab.dev for setup instructions.

---

## 9. Monitoring Dashboard

### 9.1 Accessing Grafana

Grafana is available at: `http://monitoring.evap.local:3000`

Default credentials (change immediately after first login):
- Username: `admin`
- Password: set during deployment in `GRAFANA_ADMIN_PASSWORD` env var

### 9.2 Key Dashboards

| Dashboard | URL Path | Purpose |
|-----------|----------|---------|
| System Overview | `/d/evap-overview` | CPU, memory, disk across all nodes |
| Camera Health | `/d/evap-cameras` | Per-camera FPS, packet loss, offline events |
| AI Performance | `/d/evap-ai` | Detection latency, GPU utilization, queue depth |
| API Performance | `/d/evap-api` | Request rate, P95/P99 latency, error rate |
| Database Health | `/d/evap-db` | Query latency, connections, replication lag |
| Celery Workers | `/d/evap-celery` | Queue depth, task rate, failed tasks |
| Alert Volume | `/d/evap-alerts` | Alert counts by type, acknowledgement rates |

### 9.3 Key Metrics and Thresholds

| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| API P99 latency | > 500ms | > 2000ms | Check DB queries, scale backend |
| GPU utilization | > 80% | > 95% | Reduce cameras per GPU or add GPU |
| Detection queue depth | > 50 | > 200 | Scale celery-detection workers |
| Cameras offline % | > 5% | > 20% | Check network, camera firmware |
| DB connection pool usage | > 70% | > 90% | Tune PgBouncer pool size |
| Disk usage | > 75% | > 90% | Purge old snapshots, expand volume |
| RabbitMQ queue messages | > 100 | > 1000 | Add alert workers, check DLQ |
| Celery task failure rate | > 1% | > 5% | Check worker logs, DLQ |

### 9.4 Alertmanager Rules for On-Call

Configure `alertmanager.yml` to page the on-call engineer:

```yaml
# deploy/monitoring/alertmanager.yml
global:
  resolve_timeout: 5m

route:
  group_by: ['alertname', 'cluster']
  group_wait: 10s
  group_interval: 5m
  repeat_interval: 4h
  receiver: 'evap-oncall'
  routes:
    - match:
        severity: critical
      receiver: 'evap-oncall-pagerduty'
      continue: true

receivers:
  - name: 'evap-oncall'
    email_configs:
      - to: 'oncall@yourdomain.com'
        from: 'alertmanager@yourdomain.com'
        smarthost: 'smtp.mailgun.org:587'
        auth_username: 'postmaster@mg.yourdomain.com'
        auth_password: 'smtp_password'

  - name: 'evap-oncall-pagerduty'
    pagerduty_configs:
      - routing_key: 'your_pagerduty_integration_key'
        description: '{{ .CommonAnnotations.summary }}'
```

---

## 10. System Maintenance

### 10.1 Log Rotation

EVAP application logs are written to `/var/log/evap/`. Configure logrotate:

```
# /etc/logrotate.d/evap
/var/log/evap/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0640 evap evap
    sharedscripts
    postrotate
        docker kill -s USR1 evap-backend-1 2>/dev/null || true
    endscript
}
```

Apply immediately: `sudo logrotate -f /etc/logrotate.d/evap`

### 10.2 Snapshot Cleanup Cron

In addition to S3 lifecycle rules, run a cleanup task daily:

```bash
# Runs via Celery Beat — verify it is scheduled
docker compose exec backend celery -A app.workers inspect scheduled | grep cleanup_old_snapshots

# Manual trigger
docker compose exec backend python -m scripts.cleanup_snapshots --days 90
# Deleted 1,247 snapshot files older than 90 days. Freed 34.2 GB.
```

### 10.3 Database Vacuum and Analyze Schedule

PostgreSQL autovacuum handles most cleanup automatically, but large tables benefit from manual scheduling:

```sql
-- Run via cron or Celery Beat — recommended weekly at 03:00
VACUUM ANALYZE attendance_events;
VACUUM ANALYZE detection_events;
VACUUM ANALYZE alert_instances;

-- Check table bloat
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
    n_dead_tup,
    last_autovacuum
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 10;
```

### 10.4 Cache Invalidation

Redis cache entries expire automatically based on TTL. For manual invalidation after a configuration change:

```bash
# Invalidate all camera config cache entries
docker compose exec backend python -m scripts.cache_invalidate --pattern "camera:config:*"

# Invalidate all user permission cache
docker compose exec backend python -m scripts.cache_invalidate --pattern "user:permissions:*"

# Full cache flush (use sparingly — causes temporary latency spike)
docker compose exec redis redis-cli FLUSHDB
```

### 10.5 Model Reloading Without Downtime

Reload AI models after updating weights without restarting the full service:

```bash
# Reload all models on all workers (zero-downtime rolling reload)
curl -s -X POST http://localhost:8000/api/v1/system/ai/reload \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"models": ["yolo", "insightface", "anpr"]}' | python3 -m json.tool
# {
#   "status": "reload_queued",
#   "estimated_duration_seconds": 45,
#   "message": "Workers will reload models in a rolling fashion. No detections lost."
# }
```

### 10.6 Upgrading EVAP

Follow this procedure for every version upgrade:

```bash
# 1. Read the release notes for breaking changes
# https://github.com/beamlab/evap/releases

# 2. Take a database backup before upgrading
docker compose exec backend python -m scripts.backup_now

# 3. Pull new images
docker compose pull

# 4. Restart with zero-downtime (rolling update)
docker compose up -d --no-deps --build backend
docker compose up -d --no-deps celery-detection celery-alerts celery-beat

# 5. Apply new migrations
docker compose exec backend alembic upgrade head

# 6. Verify health
curl -s http://localhost:8000/health | python3 -m json.tool

# 7. Restart frontend
docker compose up -d --no-deps frontend

# 8. If anything is wrong, roll back immediately
docker compose stop backend
docker compose run --rm backend alembic downgrade -1
# Then restore the previous image tag by editing docker-compose.yml
```

---

## 11. Troubleshooting

### 11.1 Camera Shows Offline but RTSP is Reachable

**Symptom:** Dashboard shows camera as "offline" but `ffprobe` confirms the stream is up.

**Diagnosis:**
```bash
# Check AI engine logs for the specific camera UUID
docker compose logs celery-detection | grep "cam-your-camera-uuid" | tail -30

# Common errors to look for:
# "CUDA out of memory" → GPU memory exhaustion
# "Connection timeout" → EVAP server cannot reach camera (firewall/VLAN)
# "Codec not supported" → Camera using H.265 HEVC; check EVAP codec config
# "Authentication failed" → RTSP credentials changed on camera
```

**Resolution steps:**
1. If "CUDA out of memory": reduce GPU load by disabling AI on non-critical cameras, or redistribute cameras across GPUs.
2. If "Connection timeout": verify that the EVAP server (container network) can reach the camera IP. Check VLAN routing and firewall rules.
3. If codec error: navigate to **Camera → Edit → Advanced → Video Codec** and set to H.264.
4. If authentication: re-enter RTSP credentials in **Cameras → [Camera] → Edit → Update Credentials**.

### 11.2 High Memory Usage on Celery Worker

**Symptom:** `celery-detection` container using > 90% of allocated memory limit, close to OOM kill.

**Diagnosis:**
```bash
docker stats evap-celery-detection-1
# CONTAINER ID   NAME                     CPU %   MEM USAGE / LIMIT   MEM %
# abc123         evap-celery-detection-1  34.2%   11.2GiB / 12GiB     93.3%

# Check for memory leaks in recent tasks
docker compose logs celery-detection | grep -i "memory\|leak\|RSS" | tail -20
```

**Resolution:**
```bash
# 1. Graceful restart (finishes current tasks first)
docker compose exec celery-detection celery -A app.workers control shutdown

# 2. Docker will restart automatically (restart: unless-stopped)
# 3. If persistent, enable worker max-tasks-per-child to force periodic restart
# Add to celery command:
#   --max-tasks-per-child=500
```

**Long-term fix:** Check the EVAP GitHub issues for the specific model causing the leak. Ensure ONNX Runtime sessions are properly closed after batch processing.

### 11.3 Database Connections Exhausted

**Symptom:** API returns `500 Internal Server Error` with "remaining connection slots are reserved for non-replication superuser connections" in logs.

**Diagnosis:**
```sql
-- Check current connections
SELECT count(*), state, wait_event_type, wait_event
FROM pg_stat_activity
GROUP BY state, wait_event_type, wait_event
ORDER BY count DESC;

-- Check max connections setting
SHOW max_connections;
```

**Resolution — PgBouncer tuning:**

EVAP bundles PgBouncer as a sidecar. Edit `deploy/pgbouncer/pgbouncer.ini`:

```ini
[databases]
evap = host=postgres port=5432 dbname=evap

[pgbouncer]
listen_port = 6432
listen_addr = 0.0.0.0
auth_type = md5
auth_file = /etc/pgbouncer/userlist.txt
pool_mode = transaction           ; best for FastAPI async workloads
max_client_conn = 1000            ; total client connections PgBouncer accepts
default_pool_size = 25            ; connections to PostgreSQL per database/user pair
min_pool_size = 5
reserve_pool_size = 5
reserve_pool_timeout = 3
server_idle_timeout = 600
```

Restart: `docker compose restart pgbouncer`

Also ensure `max_connections` in PostgreSQL `postgresql.conf` is set appropriately (200–500 for most deployments) and `shared_buffers` is 25% of total RAM.

### 11.4 RabbitMQ Queue Growing (Messages Accumulating)

**Symptom:** Grafana shows `detection` queue depth rising steadily; cameras may show detection lag.

**Diagnosis:**
```bash
# Check queue depths via management API
curl -s -u evap:$RABBITMQ_PASS \
  "http://localhost:15672/api/queues/%2F/detection" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print('Messages:', d['messages'], '| Consumers:', d['consumers'])"

# Check Dead Letter Queue (failed tasks)
curl -s -u evap:$RABBITMQ_PASS \
  "http://localhost:15672/api/queues/%2F/detection.dlq" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print('DLQ Messages:', d['messages'])"
```

**Resolution:**
```bash
# Scale up detection workers immediately
docker compose up -d --scale celery-detection=4

# If DLQ has messages — inspect failed tasks
docker compose exec backend celery -A app.workers inspect revoked
# Then purge DLQ after investigation
curl -s -u evap:$RABBITMQ_PASS \
  -X DELETE "http://localhost:15672/api/queues/%2F/detection.dlq/contents"
```

**Root cause:** DLQ buildup usually indicates a bug in the detection task (unhandled exception). Check worker logs for stack traces:
```bash
docker compose logs celery-detection | grep -A 10 "Task failed\|Traceback"
```

### 11.5 License Expiry Warning

EVAP Enterprise licenses are time-limited. When approaching expiry (< 30 days), a yellow banner appears in the dashboard header.

**Check license status:**
```bash
curl -s "http://localhost:8000/api/v1/system/license" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
# {
#   "status": "active",
#   "licensed_cameras": 50,
#   "active_cameras": 24,
#   "expiry_date": "2026-12-31",
#   "days_remaining": 199,
#   "features": ["face_recognition", "anpr", "erp_integration"]
# }
```

To renew: contact sales@beamlab.dev with your `license_id` (shown in System → About). A new license key will be provided and applied at **Settings → System → License → Enter License Key**.

---

*EVAP Administrator Guide — For support, contact support@beamlab.dev or open a ticket at https://github.com/beamlab/evap/issues*
