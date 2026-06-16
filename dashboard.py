"""
dashboard.py – Live Rich console dashboard for CCTV Phase 1.

Renders a full-terminal panel that refreshes at the rate defined in config
without any flickering.  All state is written via the update_*() methods
from the main loop; the dashboard renders asynchronously via Rich Live.
"""

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import psutil
from rich.columns import Columns
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from config_manager import AppConfig
from detection import DetectionResult
from ai_analyst import AiInsight


@dataclass
class DashboardState:
    # Camera
    camera_ip: str = ""
    camera_status: str = "Connecting…"
    rtsp_status: str = "Initialising"
    stream_resolution: str = "–"
    stream_fps_nominal: float = 0.0
    codec: str = "–"

    # Detection
    det: DetectionResult = field(default_factory=DetectionResult)
    actual_fps: float = 0.0

    # System
    cpu_pct: float = 0.0
    ram_gb: float = 0.0
    device_label: str = "CPU"

    # Operational
    reconnect_count: int = 0
    last_reconnect: str = "–"
    start_time: datetime = field(default_factory=datetime.now)
    last_error: str = ""
    frame_failures: int = 0

    # AI
    ai_insight: AiInsight = field(default_factory=AiInsight)

    # Misc
    log_tail: list = field(default_factory=list)   # last 5 log lines for display


_STATE = DashboardState()
_LOCK  = threading.Lock()
_console = Console()


# ─────────────────────────── public update helpers ───────────────────────────

def update_camera(ip: str, status: str, rtsp: str) -> None:
    with _LOCK:
        _STATE.camera_ip     = ip
        _STATE.camera_status = status
        _STATE.rtsp_status   = rtsp


def update_stream_info(resolution: str, fps: float, codec: str) -> None:
    with _LOCK:
        _STATE.stream_resolution   = resolution
        _STATE.stream_fps_nominal  = fps
        _STATE.codec               = codec


def update_detection(det: DetectionResult, actual_fps: float) -> None:
    with _LOCK:
        _STATE.det        = det
        _STATE.actual_fps = actual_fps


def update_system(cpu: float, ram_gb: float, device: str) -> None:
    with _LOCK:
        _STATE.cpu_pct      = cpu
        _STATE.ram_gb       = ram_gb
        _STATE.device_label = device


def update_reconnect(count: int) -> None:
    with _LOCK:
        _STATE.reconnect_count = count
        _STATE.last_reconnect  = datetime.now().strftime("%H:%M:%S")


def update_error(msg: str) -> None:
    with _LOCK:
        _STATE.last_error = msg[:80]


def update_frame_failures(count: int) -> None:
    with _LOCK:
        _STATE.frame_failures = count


def update_ai_insight(insight: "AiInsight") -> None:
    with _LOCK:
        _STATE.ai_insight = insight


def append_log(msg: str) -> None:
    with _LOCK:
        _STATE.log_tail.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        if len(_STATE.log_tail) > 6:
            _STATE.log_tail.pop(0)


# ─────────────────────────── rendering ──────────────────────────────────────

def _status_colour(status: str) -> str:
    if "connect" in status.lower():
        return "green"
    if "error" in status.lower() or "fail" in status.lower() or "lost" in status.lower():
        return "red"
    return "yellow"


def _render() -> Layout:
    with _LOCK:
        s = _STATE

    uptime = str(datetime.now() - s.start_time).split(".")[0]

    # ── Camera Status panel ──────────────────────────────────────────────────
    cam_table = Table(box=None, show_header=False, padding=(0, 1))
    cam_table.add_column(style="bold cyan", width=20)
    cam_table.add_column()
    cam_table.add_row("Camera IP",   s.camera_ip or "–")
    cam_table.add_row("Status",      Text(s.camera_status, style=_status_colour(s.camera_status)))
    cam_table.add_row("RTSP",        Text(s.rtsp_status, style=_status_colour(s.rtsp_status)))
    cam_table.add_row("Resolution",  s.stream_resolution)
    cam_table.add_row("Nominal FPS", f"{s.stream_fps_nominal:.0f}")
    cam_table.add_row("Codec",       s.codec)
    cam_table.add_row("Uptime",      uptime)
    cam_panel = Panel(cam_table, title="[bold yellow]CAMERA STATUS", border_style="yellow")

    # ── Detection Stats panel ────────────────────────────────────────────────
    det = s.det
    det_table = Table(box=None, show_header=False, padding=(0, 1))
    det_table.add_column(style="bold green", width=20)
    det_table.add_column()
    det_table.add_row("Frame #",     str(det.frame_number))
    det_table.add_row("People",      _count_str(det.people))
    det_table.add_row("Cars",        _count_str(det.cars))
    det_table.add_row("Motorcycles", _count_str(det.motorcycles))
    det_table.add_row("Buses",       _count_str(det.buses))
    det_table.add_row("Trucks",      _count_str(det.trucks))
    det_table.add_row("Bicycles",    _count_str(det.bicycles))
    det_table.add_row("─" * 14,      "─" * 6)
    det_table.add_row("Actual FPS",  f"{s.actual_fps:.1f}")
    det_panel = Panel(det_table, title="[bold green]DETECTION STATS", border_style="green")

    # ── System Health panel ──────────────────────────────────────────────────
    sys_table = Table(box=None, show_header=False, padding=(0, 1))
    sys_table.add_column(style="bold magenta", width=20)
    sys_table.add_column()
    sys_table.add_row("CPU Usage",     f"{s.cpu_pct:.1f}%")
    sys_table.add_row("Memory",        f"{s.ram_gb:.2f} GB")
    sys_table.add_row("YOLO Device",   s.device_label)
    sys_table.add_row("Reconnects",    str(s.reconnect_count))
    sys_table.add_row("Last Reconnect",s.last_reconnect)
    sys_table.add_row("Frame Fails",   str(s.frame_failures))
    if s.last_error:
        sys_table.add_row("Last Error", Text(s.last_error[:40], style="red"))
    sys_panel = Panel(sys_table, title="[bold magenta]SYSTEM HEALTH", border_style="magenta")

    # ── Recent Log panel ─────────────────────────────────────────────────────
    log_text = "\n".join(s.log_tail) if s.log_tail else "No events yet."
    log_panel = Panel(log_text, title="[bold blue]RECENT EVENTS", border_style="blue")

    # ── AI Analysis panel ─────────────────────────────────────────────────────
    ai = s.ai_insight
    ai_colour  = "red" if ai.error else "bright_cyan"
    ai_content = Text(ai.text, style=ai_colour)
    ai_meta    = f"\n[dim]Model: {ai.model}   Last update: {ai.timestamp}[/dim]"
    ai_panel   = Panel(
        ai_content.__str__() + ai_meta,
        title="[bold bright_cyan]AI ANALYSIS",
        border_style="bright_cyan",
    )

    layout = Layout()
    layout.split_column(
        Layout(name="top", ratio=2),
        Layout(name="bottom", ratio=1),
    )
    layout["top"].split_row(
        Layout(cam_panel, name="cam"),
        Layout(det_panel, name="det"),
        Layout(sys_panel, name="sys"),
    )
    layout["bottom"].split_row(
        Layout(log_panel, name="log"),
        Layout(ai_panel,  name="ai"),
    )
    return layout


def _count_str(n: int) -> str:
    if n == 0:
        return "[dim]0[/dim]"
    return f"[bold white]{n}[/bold white]"


# ─────────────────────────── dashboard runner ────────────────────────────────

class Dashboard:
    def __init__(self, config: AppConfig):
        self._refresh = config.display.dashboard_refresh_rate
        self._live: Optional[Live] = None
        self._running = False

    def start(self) -> None:
        self._running = True
        self._live = Live(
            _render(),
            console=_console,
            refresh_per_second=int(1 / self._refresh),
            screen=True,
        )
        self._live.start()

    def tick(self) -> None:
        """Call this from the main loop to push an updated render."""
        if self._live and self._running:
            self._live.update(_render())

    def stop(self) -> None:
        self._running = False
        if self._live:
            self._live.stop()


def print_verification_result(result, config: AppConfig) -> None:
    """Print a simple pre-flight report before the Live dashboard starts."""
    console = Console()
    console.rule("[bold yellow]CAMERA PRE-FLIGHT VERIFICATION")

    table = Table(box=box.SIMPLE_HEAVY, show_header=False)
    table.add_column(style="bold cyan", width=22)
    table.add_column()

    table.add_row("Camera IP",   config.camera.ip)
    table.add_row("Status",      "[green]Connected[/green]" if result.success else "[red]FAILED[/red]")
    table.add_row("RTSP Port",   "[green]Open[/green]" if result.port_open else "[red]Closed[/red]")
    table.add_row("Stream",      "[green]Available[/green]" if result.stream_ok else "[red]Unavailable[/red]")

    if result.success:
        table.add_row("Resolution", f"{result.width}x{result.height}")
        table.add_row("FPS",        f"{result.fps}")
        table.add_row("Codec",      result.codec)

    console.print(table)

    if not result.success:
        console.print(f"\n[bold red][ERROR] Verification Failed[/bold red]")
        console.print(f"[red]{result.error_message}[/red]")
