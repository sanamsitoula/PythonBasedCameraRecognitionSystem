"""
phase2_dashboard.py – Full-terminal Rich console dashboard for Phase 2.

Layout (6 panels):
  ┌──────────────┬──────────────┬──────────────┐
  │ CAMERA       │ DETECTION    │ SYSTEM       │
  │ STATUS       │ STATS        │ HEALTH       │
  ├──────────────┼──────────────┼──────────────┤
  │ ACTIVE       │ ENTRY/EXIT   │ AI ANALYSIS  │
  │ TRACKS       │ & OCCUPANCY  │              │
  └──────────────┴──────────────┴──────────────┘
  ┌─────────────────────────────────────────────┐
  │ RECENT EVENTS                               │
  └─────────────────────────────────────────────┘
"""

import threading
from datetime import datetime
from typing import Optional

from rich.columns import Columns
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

import analytics_state as state
from config_manager import AppConfig


_console = Console()
_lock    = threading.Lock()


# ─────────────────────────── rendering helpers ───────────────────────────────

def _status_colour(s: str) -> str:
    sl = s.lower()
    if "connect" in sl:    return "green"
    if any(w in sl for w in ("error", "fail", "lost", "critical")): return "red"
    return "yellow"


def _bar(value: float, max_val: float, width: int = 10) -> str:
    filled = int(min(value / max(max_val, 1), 1.0) * width)
    return "█" * filled + "░" * (width - filled)


def _fmt_dur(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


# ─────────────────────────── panel builders ──────────────────────────────────

def _camera_panel(s: state.AnalyticsState, camera_ip: str,
                   cam_status: str, rtsp_status: str,
                   resolution: str, fps_nom: float, codec: str) -> Panel:
    t = Table(box=None, show_header=False, padding=(0, 1))
    t.add_column(style="bold cyan", width=18)
    t.add_column()
    uptime = str(datetime.now() - s.start_time).split(".")[0]
    t.add_row("Camera IP",    camera_ip or "–")
    t.add_row("Status",       Text(cam_status, style=_status_colour(cam_status)))
    t.add_row("RTSP",         Text(rtsp_status, style=_status_colour(rtsp_status)))
    t.add_row("Resolution",   resolution)
    t.add_row("Nominal FPS",  f"{fps_nom:.0f}")
    t.add_row("Codec",        codec)
    t.add_row("Uptime",       uptime)
    t.add_row("DB",           Text("Online" if s.db_available else "Disabled",
                                   style="green" if s.db_available else "dim"))
    return Panel(t, title="[bold yellow]CAMERA STATUS", border_style="yellow")


def _detection_panel(s: state.AnalyticsState) -> Panel:
    t = Table(box=None, show_header=False, padding=(0, 1))
    t.add_column(style="bold green", width=18)
    t.add_column()

    def _n(n: int) -> str:
        return f"[bold white]{n}[/bold white]" if n else "[dim]0[/dim]"

    t.add_row("People",       _n(s.people_count))
    t.add_row("Cars",         _n(s.car_count))
    t.add_row("Motorcycles",  _n(s.motorcycle_count))
    t.add_row("Buses",        _n(s.bus_count))
    t.add_row("Trucks",       _n(s.truck_count))
    t.add_row("Bicycles",     _n(s.bicycle_count))
    t.add_row("──────────",   "──────")
    t.add_row("Gender ♂",    _n(s.gender_male))
    t.add_row("Gender ♀",    _n(s.gender_female))
    t.add_row("Unknown",      _n(s.gender_unknown))
    t.add_row("──────────",   "──────")
    t.add_row("Actual FPS",   f"{s.actual_fps:.1f}")
    t.add_row("Frame #",      f"{s.frame_number:,}")
    return Panel(t, title="[bold green]DETECTION STATS", border_style="green")


def _system_panel(s: state.AnalyticsState) -> Panel:
    t = Table(box=None, show_header=False, padding=(0, 1))
    t.add_column(style="bold magenta", width=18)
    t.add_column()
    cpu_colour = "red" if s.cpu_pct > 85 else "yellow" if s.cpu_pct > 65 else "green"
    t.add_row("CPU",  Text(f"{s.cpu_pct:.1f}% {_bar(s.cpu_pct, 100, 8)}", style=cpu_colour))
    t.add_row("RAM",  f"{s.ram_gb:.2f} GB")
    t.add_row("YOLO", s.device_label)
    if s.error_count:
        t.add_row("Errors", Text(str(s.error_count), style="bold red"))
        if s.last_error:
            t.add_row("Last Error", Text(s.last_error[:45], style="red"))
    return Panel(t, title="[bold magenta]SYSTEM HEALTH", border_style="magenta")


def _tracks_panel(s: state.AnalyticsState) -> Panel:
    lines = []
    persons  = [p for p in s.active_persons][:8]    # show max 8
    vehicles = [v for v in s.active_vehicles][:4]

    if persons:
        lines.append("[bold white]People:[/bold white]")
        for p in persons:
            gender_tag = {
                "Male":    "[bold blue]♂[/bold blue]",
                "Female":  "[bold pink1]♀[/bold pink1]",
            }.get(p.gender, "[dim]?[/dim]")
            lines.append(
                f"  {gender_tag} [cyan]{p.track_id}[/cyan]  "
                f"[dim]{p.direction}[/dim]  "
                f"[italic]{p.zone}[/italic]"
            )
    else:
        lines.append("[dim]No active person tracks[/dim]")

    if vehicles:
        lines.append("\n[bold white]Vehicles:[/bold white]")
        for v in vehicles:
            lines.append(f"  [yellow]{v.track_id}[/yellow] {v.vehicle_type} [dim]{v.direction}[/dim]")

    content = "\n".join(lines) if lines else "[dim]No active tracks[/dim]"
    return Panel(content, title="[bold cyan]ACTIVE TRACKS", border_style="cyan")


def _entry_exit_panel(s: state.AnalyticsState) -> Panel:
    t = Table(box=None, show_header=False, padding=(0, 1))
    t.add_column(style="bold", width=18)
    t.add_column()
    t.add_row("[green]IN  (Entries)[/green]", f"[bold green]{s.total_entries}[/bold green]")
    t.add_row("[red]OUT (Exits)[/red]",       f"[bold red]{s.total_exits}[/bold red]")
    t.add_row("─" * 14,                       "──────")
    t.add_row("Current Inside",               f"[bold white]{s.current_occupancy}[/bold white]")
    t.add_row("Today's Peak",                 f"[bold yellow]{s.peak_occupancy}[/bold yellow]")
    t.add_row("Average",                      f"{s.avg_occupancy:.1f}")
    return Panel(t, title="[bold]ENTRY / EXIT & OCCUPANCY", border_style="white")


def _ai_panel(s: state.AnalyticsState) -> Panel:
    text  = s.ai_text or "Awaiting first analysis…"
    meta  = f"\n[dim]Last: {s.ai_timestamp}[/dim]"
    return Panel(
        text + meta,
        title    = "[bold bright_cyan]AI ANALYSIS",
        border_style = "bright_cyan",
    )


def _events_panel(s: state.AnalyticsState) -> Panel:
    content = "\n".join(s.log_tail) if s.log_tail else "No events yet."
    return Panel(content, title="[bold blue]RECENT EVENTS", border_style="blue")


# ─────────────────────────── layout assembly ─────────────────────────────────

# These are updated by the main loop between renders
_CAM_IP      = ""
_CAM_STATUS  = "Connecting…"
_RTSP_STATUS = "Initialising"
_RESOLUTION  = "–"
_FPS_NOM     = 0.0
_CODEC       = "–"


def _render() -> Layout:
    s = state.get_state()

    layout = Layout()
    layout.split_column(
        Layout(name="top",    ratio=3),
        Layout(name="middle", ratio=3),
        Layout(name="bottom", ratio=1),
    )
    layout["top"].split_row(
        Layout(_camera_panel(s, _CAM_IP, _CAM_STATUS, _RTSP_STATUS,
                              _RESOLUTION, _FPS_NOM, _CODEC), name="cam"),
        Layout(_detection_panel(s),   name="det"),
        Layout(_system_panel(s),      name="sys"),
    )
    layout["middle"].split_row(
        Layout(_tracks_panel(s),      name="tracks"),
        Layout(_entry_exit_panel(s),  name="ee"),
        Layout(_ai_panel(s),          name="ai"),
    )
    layout["bottom"].update(_events_panel(s))
    return layout


# ─────────────────────────── public update helpers ───────────────────────────

def set_camera_info(ip: str, status: str, rtsp: str,
                    resolution: str, fps: float, codec: str) -> None:
    global _CAM_IP, _CAM_STATUS, _RTSP_STATUS, _RESOLUTION, _FPS_NOM, _CODEC
    _CAM_IP      = ip
    _CAM_STATUS  = status
    _RTSP_STATUS = rtsp
    _RESOLUTION  = resolution
    _FPS_NOM     = fps
    _CODEC       = codec


# ─────────────────────────── Dashboard class ─────────────────────────────────

class Phase2Dashboard:
    def __init__(self, config: AppConfig):
        self._refresh = config.display.dashboard_refresh_rate
        self._live: Optional[Live] = None
        self._running = False

    def start(self) -> None:
        self._running = True
        self._live = Live(
            _render(),
            console          = _console,
            refresh_per_second = max(1, int(1 / self._refresh)),
            screen           = True,
        )
        self._live.start()

    def tick(self) -> None:
        if self._live and self._running:
            self._live.update(_render())

    def stop(self) -> None:
        self._running = False
        if self._live:
            self._live.stop()


def print_preflight(result, config: AppConfig) -> None:
    """Print pre-flight verification result before the dashboard starts."""
    from rich import box as rbox
    console = Console()
    console.rule("[bold yellow]PHASE 2 – PRE-FLIGHT VERIFICATION")
    t = Table(box=rbox.SIMPLE_HEAVY, show_header=False)
    t.add_column(style="bold cyan", width=22)
    t.add_column()
    t.add_row("Camera IP",   config.camera.ip)
    t.add_row("Status",
              "[green]OK[/green]" if result.success else "[red]FAILED[/red]")
    if result.success:
        t.add_row("Resolution", f"{result.width}x{result.height}")
        t.add_row("FPS",        str(result.fps))
        t.add_row("Codec",      result.codec)
    console.print(t)
    if not result.success:
        console.print(f"[bold red]Error:[/bold red] {result.error_message}")
