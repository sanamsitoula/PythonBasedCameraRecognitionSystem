"""
config_manager.py – Reads and validates config/config.ini.
Provides a single AppConfig dataclass consumed by all modules.
Phase 2 adds: TrackingConfig, GenderConfig, LineConfig, ZoneConfig,
              DatabaseConfig, OccupancyConfig.
"""

import configparser
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

CONFIG_PATH = os.path.join("config", "config.ini")


@dataclass
class CameraConfig:
    ip: str
    username: str
    password: str
    rtsp_port: int
    rtsp_url: str
    onvif_port: int
    channel: int


@dataclass
class YoloConfig:
    model: str
    confidence: float
    device: str
    iou_threshold: float


@dataclass
class SystemConfig:
    reconnect_attempts: int
    reconnect_delay: int
    save_snapshots: bool
    snapshot_on_detection: bool
    snapshot_on_error: bool
    snapshot_on_reconnect: bool
    frame_failure_threshold: int
    frame_queue_size: int
    max_ram_mb: int
    log_level: str


@dataclass
class AiConfig:
    enabled:           bool
    interval_seconds:  int
    # Provider 1 – Google Gemini (primary)
    gemini_api_key:    str
    gemini_model:      str
    # Provider 2 – Anthropic Claude
    anthropic_api_key: str
    anthropic_model:   str
    # Provider 3 – OpenRouter
    openrouter_api_key: str
    openrouter_model:  str
    # Provider 4 – DeepSeek
    deepseek_api_key:  str
    deepseek_model:    str


@dataclass
class DisplayConfig:
    dashboard_refresh_rate: float
    show_fps: bool
    show_system_health: bool


@dataclass
class TrackingConfig:
    max_age:               int
    min_hits:              int
    iou_threshold:         float
    persist_every_n:       int


@dataclass
class GenderConfig:
    enabled:              bool
    backend:              str
    confidence_threshold: float
    min_bbox_height:      int
    max_workers:          int


@dataclass
class _LineEntry:
    label:           str
    p1:              tuple
    p2:              tuple
    entry_direction: str


@dataclass
class LineConfig:
    lines:  list = field(default_factory=list)   # List[_LineEntry]


@dataclass
class _ZoneEntry:
    zone_id: str
    label:   str
    coords:  list    # [[x,y], …]


@dataclass
class ZoneConfig:
    zones:  list = field(default_factory=list)   # List[_ZoneEntry]


@dataclass
class DatabaseConfig:
    enabled:         bool
    host:            str
    port:            int
    dbname:          str
    user:            str
    password:        str
    pool_min:        int
    pool_max:        int
    write_queue_max: int


@dataclass
class OccupancyConfig:
    average_window_seconds: int
    reset_peak_daily:       bool
    alert_threshold:        int


# ── Phase 3 config dataclasses ────────────────────────────────────────────────

@dataclass
class FaceRecognitionConfig:
    backend:              str
    min_confidence:       float
    re_identify_interval: int
    model_dir:            str
    confirmed_threshold:  float
    possible_threshold:   float


@dataclass
class AttendanceConfig:
    late_threshold: str
    work_start:     str
    work_end:       str
    timezone:       str


@dataclass
class SmartAlertsConfig:
    restricted_zones:  list    # List[str]
    loitering_seconds: int
    crowd_threshold:   int
    office_start_hour: int
    office_end_hour:   int
    enabled:           bool


@dataclass
class VisitorManagementConfig:
    enabled:         bool
    save_snapshots:  bool


@dataclass
class CanteenConfig:
    zone_label:       str
    breakfast_hours:  tuple   # (start_hour, end_hour)
    lunch_hours:      tuple
    dinner_hours:     tuple


@dataclass
class AppConfig:
    camera:             CameraConfig
    yolo:               YoloConfig
    system:             SystemConfig
    display:            DisplayConfig
    ai:                 AiConfig
    tracking:           TrackingConfig
    gender:             GenderConfig
    lines:              LineConfig
    zones:              ZoneConfig
    database:           DatabaseConfig
    occupancy:          OccupancyConfig
    # Phase 3 (optional – have sensible defaults so Phase 2 callers still work)
    face_recognition:   FaceRecognitionConfig = None
    attendance:         AttendanceConfig      = None
    smart_alerts:       SmartAlertsConfig     = None
    visitor_management: VisitorManagementConfig = None
    canteen:            CanteenConfig          = None


def load_config(path: str = CONFIG_PATH) -> AppConfig:
    """Parse config.ini and return a validated AppConfig."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Configuration file not found: {path}")

    cfg = configparser.ConfigParser()
    cfg.read(path, encoding="utf-8")

    # Env-var overrides for each provider's API key
    _env_gemini    = os.environ.get("GEMINI_API_KEY", "")
    _env_anthropic = os.environ.get("ANTHROPIC_API_KEY", "")
    _env_openrouter = os.environ.get("OPENROUTER_API_KEY", "")
    _env_deepseek  = os.environ.get("DEEPSEEK_API_KEY", "")

    camera = CameraConfig(
        ip=cfg.get("CAMERA", "ip"),
        username=cfg.get("CAMERA", "username"),
        password=cfg.get("CAMERA", "password"),
        rtsp_port=cfg.getint("CAMERA", "rtsp_port", fallback=554),
        rtsp_url=cfg.get("CAMERA", "rtsp_url"),
        onvif_port=cfg.getint("CAMERA", "onvif_port", fallback=80),
        channel=cfg.getint("CAMERA", "channel", fallback=1),
    )

    yolo = YoloConfig(
        model=cfg.get("YOLO", "model", fallback="models/yolo11n.pt"),
        confidence=cfg.getfloat("YOLO", "confidence", fallback=0.40),
        device=cfg.get("YOLO", "device", fallback="auto"),
        iou_threshold=cfg.getfloat("YOLO", "iou_threshold", fallback=0.45),
    )

    system = SystemConfig(
        reconnect_attempts=cfg.getint("SYSTEM", "reconnect_attempts", fallback=10),
        reconnect_delay=cfg.getint("SYSTEM", "reconnect_delay", fallback=5),
        save_snapshots=cfg.getboolean("SYSTEM", "save_snapshots", fallback=True),
        snapshot_on_detection=cfg.getboolean("SYSTEM", "snapshot_on_detection", fallback=True),
        snapshot_on_error=cfg.getboolean("SYSTEM", "snapshot_on_error", fallback=True),
        snapshot_on_reconnect=cfg.getboolean("SYSTEM", "snapshot_on_reconnect", fallback=True),
        frame_failure_threshold=cfg.getint("SYSTEM", "frame_failure_threshold", fallback=30),
        frame_queue_size=cfg.getint("SYSTEM", "frame_queue_size", fallback=10),
        max_ram_mb=cfg.getint("SYSTEM", "max_ram_mb", fallback=4096),
        log_level=cfg.get("SYSTEM", "log_level", fallback="INFO"),
    )

    display = DisplayConfig(
        dashboard_refresh_rate=cfg.getfloat("DISPLAY", "dashboard_refresh_rate", fallback=0.5),
        show_fps=cfg.getboolean("DISPLAY", "show_fps", fallback=True),
        show_system_health=cfg.getboolean("DISPLAY", "show_system_health", fallback=True),
    )

    ai = AiConfig(
        enabled           = cfg.getboolean("AI", "enabled",           fallback=False),
        interval_seconds  = cfg.getint("AI",     "interval_seconds",  fallback=30),
        gemini_api_key    = _env_gemini    or cfg.get("AI", "gemini_api_key",     fallback=""),
        gemini_model      = cfg.get("AI", "gemini_model",     fallback="gemini-2.0-flash"),
        anthropic_api_key = _env_anthropic or cfg.get("AI", "anthropic_api_key", fallback=""),
        anthropic_model   = cfg.get("AI", "anthropic_model", fallback="claude-haiku-4-5-20251001"),
        openrouter_api_key = _env_openrouter or cfg.get("AI", "openrouter_api_key", fallback=""),
        openrouter_model  = cfg.get("AI", "openrouter_model", fallback="openai/gpt-4o"),
        deepseek_api_key  = _env_deepseek  or cfg.get("AI", "deepseek_api_key",  fallback=""),
        deepseek_model    = cfg.get("AI", "deepseek_model",   fallback="deepseek-chat"),
    )

    # ── Phase 2: Tracking ────────────────────────────────────────────────────
    tracking = TrackingConfig(
        max_age         = cfg.getint("TRACKING", "max_age",               fallback=30),
        min_hits        = cfg.getint("TRACKING", "min_hits",              fallback=3),
        iou_threshold   = cfg.getfloat("TRACKING", "iou_threshold",       fallback=0.45),
        persist_every_n = cfg.getint("TRACKING", "persist_every_n_frames", fallback=5),
    )

    # ── Phase 2: Gender ──────────────────────────────────────────────────────
    gender = GenderConfig(
        enabled              = cfg.getboolean("GENDER", "enabled",              fallback=True),
        backend              = cfg.get("GENDER", "backend",                     fallback="deepface"),
        confidence_threshold = cfg.getfloat("GENDER", "confidence_threshold",   fallback=0.65),
        min_bbox_height      = cfg.getint("GENDER", "min_bbox_height_px",       fallback=80),
        max_workers          = cfg.getint("GENDER", "max_workers",              fallback=2),
    )

    # ── Phase 2: Lines ───────────────────────────────────────────────────────
    lines_list = []
    n = 1
    while True:
        key = f"line_{n}"
        if not cfg.has_option("LINE_COUNTER", key):
            break
        coords_raw = cfg.get("LINE_COUNTER", key).split()
        if len(coords_raw) >= 2:
            p1 = tuple(int(v) for v in coords_raw[0].split(","))
            p2 = tuple(int(v) for v in coords_raw[1].split(","))
            label     = cfg.get("LINE_COUNTER", f"{key}_label",           fallback=key)
            entry_dir = cfg.get("LINE_COUNTER", f"{key}_entry_direction", fallback="TOP_TO_BOTTOM")
            from line_counter import LineConfig as _LC
            lines_list.append(_LC(label=label, p1=p1, p2=p2, entry_direction=entry_dir))
        n += 1
    lines = LineConfig(lines=lines_list)

    # ── Phase 2: Zones ───────────────────────────────────────────────────────
    zones_list = []
    n = 1
    while True:
        key = f"zone_{n}"
        if not cfg.has_option("ZONES", key):
            break
        coords_raw = cfg.get("ZONES", key).split()
        coords = [[int(v) for v in pt.split(",")] for pt in coords_raw]
        label  = cfg.get("ZONES", f"{key}_label", fallback=key)
        from zone_manager import ZoneConfig as _ZC
        zones_list.append(_ZC(zone_id=key, label=label, coords=coords))
        n += 1
    zones = ZoneConfig(zones=zones_list)

    # ── Phase 2: Database ────────────────────────────────────────────────────
    _db_pw = os.environ.get("CCTV_DB_PASSWORD") or cfg.get("DATABASE", "password", fallback="")
    database = DatabaseConfig(
        enabled         = cfg.getboolean("DATABASE", "enabled",         fallback=False),
        host            = cfg.get("DATABASE", "host",                   fallback="localhost"),
        port            = cfg.getint("DATABASE", "port",                fallback=5432),
        dbname          = cfg.get("DATABASE", "dbname",                 fallback="cctv_analytics"),
        user            = cfg.get("DATABASE", "user",                   fallback="cctv_user"),
        password        = _db_pw,
        pool_min        = cfg.getint("DATABASE", "pool_min",            fallback=2),
        pool_max        = cfg.getint("DATABASE", "pool_max",            fallback=10),
        write_queue_max = cfg.getint("DATABASE", "write_queue_maxsize", fallback=2000),
    )

    # ── Phase 2: Occupancy ───────────────────────────────────────────────────
    occupancy = OccupancyConfig(
        average_window_seconds = cfg.getint("OCCUPANCY", "average_window_seconds", fallback=300),
        reset_peak_daily       = cfg.getboolean("OCCUPANCY", "reset_peak_daily",   fallback=True),
        alert_threshold        = cfg.getint("OCCUPANCY", "alert_threshold",        fallback=50),
    )

    # ── Phase 3: Face Recognition ────────────────────────────────────────────
    face_recognition = FaceRecognitionConfig(
        backend              = cfg.get("FACE_RECOGNITION", "backend",               fallback="insightface"),
        min_confidence       = cfg.getfloat("FACE_RECOGNITION", "min_confidence",   fallback=0.85),
        re_identify_interval = cfg.getint("FACE_RECOGNITION", "re_identify_interval", fallback=30),
        model_dir            = cfg.get("FACE_RECOGNITION", "model_dir",             fallback="models/face"),
        confirmed_threshold  = cfg.getfloat("FACE_RECOGNITION", "confirmed_threshold", fallback=0.95),
        possible_threshold   = cfg.getfloat("FACE_RECOGNITION", "possible_threshold",  fallback=0.90),
    )

    # ── Phase 3: Attendance ──────────────────────────────────────────────────
    attendance = AttendanceConfig(
        late_threshold = cfg.get("ATTENDANCE", "late_threshold", fallback="09:15"),
        work_start     = cfg.get("ATTENDANCE", "work_start",     fallback="09:00"),
        work_end       = cfg.get("ATTENDANCE", "work_end",       fallback="18:00"),
        timezone       = cfg.get("ATTENDANCE", "timezone",       fallback="UTC"),
    )

    # ── Phase 3: Smart Alerts ────────────────────────────────────────────────
    _restricted_raw = cfg.get(
        "SMART_ALERTS", "restricted_zones",
        fallback="Warehouse,Store,Printing Plant"
    )
    _restricted_zones = [z.strip() for z in _restricted_raw.split(",") if z.strip()]

    smart_alerts = SmartAlertsConfig(
        restricted_zones  = _restricted_zones,
        loitering_seconds = cfg.getint("SMART_ALERTS",  "loitering_seconds",  fallback=900),
        crowd_threshold   = cfg.getint("SMART_ALERTS",  "crowd_threshold",    fallback=20),
        office_start_hour = cfg.getint("SMART_ALERTS",  "office_start_hour",  fallback=7),
        office_end_hour   = cfg.getint("SMART_ALERTS",  "office_end_hour",    fallback=19),
        enabled           = cfg.getboolean("SMART_ALERTS", "enabled",         fallback=True),
    )

    # ── Phase 3: Visitor Management ──────────────────────────────────────────
    visitor_management = VisitorManagementConfig(
        enabled        = cfg.getboolean("VISITOR_MANAGEMENT", "enabled",        fallback=True),
        save_snapshots = cfg.getboolean("VISITOR_MANAGEMENT", "save_snapshots", fallback=True),
    )

    # ── Phase 3: Canteen ─────────────────────────────────────────────────────
    def _parse_hours(raw: str, default: tuple) -> tuple:
        """Parse 'start,end' string into (int, int) tuple."""
        try:
            parts = [int(x.strip()) for x in raw.split(",")]
            return (parts[0], parts[1])
        except (ValueError, IndexError):
            return default

    canteen = CanteenConfig(
        zone_label      = cfg.get("CANTEEN", "zone_label",       fallback="Canteen"),
        breakfast_hours = _parse_hours(
            cfg.get("CANTEEN", "breakfast_hours", fallback="7,10"), (7, 10)
        ),
        lunch_hours     = _parse_hours(
            cfg.get("CANTEEN", "lunch_hours",     fallback="12,15"), (12, 15)
        ),
        dinner_hours    = _parse_hours(
            cfg.get("CANTEEN", "dinner_hours",    fallback="19,22"), (19, 22)
        ),
    )

    log.info("Configuration loaded from %s", path)
    return AppConfig(
        camera             = camera,
        yolo               = yolo,
        system             = system,
        display            = display,
        ai                 = ai,
        tracking           = tracking,
        gender             = gender,
        lines              = lines,
        zones              = zones,
        database           = database,
        occupancy          = occupancy,
        face_recognition   = face_recognition,
        attendance         = attendance,
        smart_alerts       = smart_alerts,
        visitor_management = visitor_management,
        canteen            = canteen,
    )


def build_ai_providers(ai: AiConfig) -> list:
    """Return an ordered list of ProviderConfig objects for AiAnalyst."""
    from ai_analyst import ProviderConfig
    providers = []
    if ai.gemini_api_key.strip():
        providers.append(ProviderConfig(
            name     = "gemini",
            api_key  = ai.gemini_api_key,
            model    = ai.gemini_model,
            endpoint = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        ))
    if ai.anthropic_api_key.strip():
        providers.append(ProviderConfig(
            name         = "anthropic",
            api_key      = ai.anthropic_api_key,
            model        = ai.anthropic_model,
            endpoint     = "https://api.anthropic.com/v1/messages",
            is_anthropic = True,
        ))
    if ai.openrouter_api_key.strip():
        providers.append(ProviderConfig(
            name     = "openrouter",
            api_key  = ai.openrouter_api_key,
            model    = ai.openrouter_model,
            endpoint = "https://openrouter.ai/api/v1/chat/completions",
        ))
    if ai.deepseek_api_key.strip():
        providers.append(ProviderConfig(
            name     = "deepseek",
            api_key  = ai.deepseek_api_key,
            model    = ai.deepseek_model,
            endpoint = "https://api.deepseek.com/v1/chat/completions",
        ))
    return providers
