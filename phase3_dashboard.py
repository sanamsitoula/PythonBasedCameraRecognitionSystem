"""
phase3_dashboard.py – Full-terminal Rich console dashboard for Phase 3.

Layout (4 rows):
  Row 1: SYSTEM STATUS | PEOPLE OVERVIEW | ATTENDANCE TODAY
  Row 2: ACTIVE EMPLOYEES | ACTIVE VISITORS | CANTEEN
  Row 3: DEPARTMENT STATUS | SMART ALERTS | AI ANALYSIS
  Row 4: MOVEMENT LOG (full width, last 8 events)
"""

import threading
from datetime import datetime
from typing import Optional

from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import phase3_state as state
from config_manager import AppConfig

_console = Console()
_lock = threading.Lock()


# ─────────────────────────── module-level camera state ───────────────────────

_CAMERAS: list = []   # list of {"ip": str, "status": str, "fps": float}


# ─────────────────────────── rendering helpers ───────────────────────────────

def _bar(value: float, max_val: float, width: int = 10) -> str:
    filled = int(min(value / max(max_val, 1), 1.0) * width)
    return "█" * filled + "░" * (width - filled)


def _fmt_dur(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def _status_colour(s: str) -> str:
    sl = s.lower()
    if any(w in sl for w in ("ok", "connect", "online", "active")):
        return "green"
    if any(w in sl for w in ("error", "fail", "lost", "critical", "offline")):
        return "red"
    return "yellow"


# ─────────────────────────── panel builders ──────────────────────────────────

def _system_panel(s: state.Phase3State) -> Panel:
    t = Table(box=None, show_header=False, padding=(0, 1))
    t.add_column(style="bold yellow", width=14)
    t.add_column()

    uptime = str(datetime.now() - s.start_time).split(".")[0]
    cpu_colour = "red" if s.cpu_pct > 85 else "yellow" if s.cpu_pct > 65 else "green"

    # Camera list (multi-camera support via set_cameras())
    if _CAMERAS:
        for cam in _CAMERAS[:4]:
            ip_str = cam.get("ip", "–")
            st_str = cam.get("status", "–")
            fps_v  = cam.get("fps", 0.0)
            t.add_row(
                "Camera",
                Text(f"{ip_str}  {st_str}  {fps_v:.1f}fps",
                     style=_status_colour(st_str)),
            )
    else:
        t.add_row("Camera IP", Text("–", style="cyan"))

    t.add_row("FPS",     f"{s.actual_fps:.1f}")
    t.add_row("Frame#",  f"{s.frame_number:,}")
    t.add_row("Uptime",  uptime)
    t.add_row("RAM",     f"{s.ram_gb:.2f} GB")
    t.add_row("CPU",     Text(f"{s.cpu_pct:.1f}%  {_bar(s.cpu_pct, 100, 8)}", style=cpu_colour))
    t.add_row("DB",      Text("Online" if s.db_available else "Disabled",
                              style="green" if s.db_available else "dim"))
    if s.error_count:
        t.add_row("Errors", Text(str(s.error_count), style="bold red"))

    return Panel(t, title="[bold yellow]SYSTEM STATUS", border_style="yellow")


def _people_panel(s: state.Phase3State) -> Panel:
    t = Table(box=None, show_header=False, padding=(0, 1))
    t.add_column(style="bold green", width=18)
    t.add_column()

    total_occ = s.employees_present + s.visitors_present
    t.add_row("Employees",    f"[bold cyan]{s.employees_present}[/bold cyan]")
    t.add_row("  ♂ Male",    f"[blue]{s.male_employees}[/blue]")
    t.add_row("  ♀ Female",  f"[pink1]{s.female_employees}[/pink1]")
    t.add_row("──────────",   "──────")
    t.add_row("Visitors",     f"[bold magenta]{s.visitors_present}[/bold magenta]")
    t.add_row("  ♂ Male",    f"[blue]{s.male_visitors}[/blue]")
    t.add_row("  ♀ Female",  f"[pink1]{s.female_visitors}[/pink1]")
    t.add_row("──────────",   "──────")
    t.add_row("Total Occ.",   f"[bold white]{total_occ}[/bold white]")

    return Panel(t, title="[bold green]PEOPLE OVERVIEW", border_style="green")


def _attendance_panel(s: state.Phase3State) -> Panel:
    total = max(s.present_today + s.late_today + s.absent_today, 1)

    t = Table(box=None, show_header=False, padding=(0, 1))
    t.add_column(style="bold", width=10)
    t.add_column(justify="right", width=5)
    t.add_column(width=12)

    t.add_row(
        "[green]Present[/green]",
        str(s.present_today),
        f"[green]{_bar(s.present_today, total, 12)}[/green]",
    )
    t.add_row(
        "[yellow]Late[/yellow]",
        str(s.late_today),
        f"[yellow]{_bar(s.late_today, total, 12)}[/yellow]",
    )
    t.add_row(
        "[red]Absent[/red]",
        str(s.absent_today),
        f"[red]{_bar(s.absent_today, total, 12)}[/red]",
    )

    return Panel(t, title="[bold blue]ATTENDANCE TODAY", border_style="blue")


def _active_employees_panel(s: state.Phase3State) -> Panel:
    employees = list(s.active_employees)[:8]

    if not employees:
        return Panel("[dim]No employees currently tracked[/dim]",
                     title="[bold cyan]ACTIVE EMPLOYEES", border_style="cyan")

    t = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    t.add_column("EMP_ID",  style="bold cyan",  width=9)
    t.add_column("Name",    style="white",       width=15)
    t.add_column("Dept",    style="green",       width=12)
    t.add_column("Zone",    style="yellow",      width=10)
    t.add_column("Entry",   style="dim",         width=8)

    for emp in employees:
        # EmployeeSummary: employee_id, employee_name, department, current_zone,
        #                  current_camera_id, entry_time, gender
        name_trunc = (emp.employee_name or "–")[:15]
        entry_str  = emp.entry_time.strftime("%H:%M:%S") if emp.entry_time else "–"
        t.add_row(
            emp.employee_id,
            name_trunc,
            emp.department or "–",
            emp.current_zone or "–",
            entry_str,
        )

    return Panel(t, title="[bold cyan]ACTIVE EMPLOYEES", border_style="cyan")


def _active_visitors_panel(s: state.Phase3State) -> Panel:
    visitors = list(s.active_visitors)[:6]

    if not visitors:
        return Panel("[dim]No active visitors[/dim]",
                     title="[bold magenta]ACTIVE VISITORS", border_style="magenta")

    t = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    t.add_column("VISITOR-ID",  style="bold magenta", width=12)
    t.add_column("Zone",        style="yellow",        width=10)
    t.add_column("First Seen",  style="dim",           width=10)
    t.add_column("Duration",    style="white",         width=10)

    now = datetime.now()
    for vis in visitors:
        # VisitorSummaryP3: visitor_id, current_zone, current_camera_id, first_seen, gender
        dur_str = _fmt_dur((now - vis.first_seen).total_seconds()) if vis.first_seen else "–"
        fs_str  = vis.first_seen.strftime("%H:%M:%S") if vis.first_seen else "–"
        t.add_row(
            vis.visitor_id,
            vis.current_zone or "–",
            fs_str,
            dur_str,
        )

    return Panel(t, title="[bold magenta]ACTIVE VISITORS", border_style="magenta")


def _canteen_panel(s: state.Phase3State) -> Panel:
    t = Table(box=None, show_header=False, padding=(0, 1))
    t.add_column(style="bold white", width=16)
    t.add_column()

    t.add_row("Current Count",  f"[bold white]{s.canteen_current}[/bold white]")
    t.add_row("Today's Visits", str(s.canteen_today_visits))

    return Panel(t, title="[bold white]CANTEEN", border_style="white")


def _department_panel(s: state.Phase3State) -> Panel:
    depts = list(s.department_summaries)[:8]

    if not depts:
        return Panel("[dim]No department data[/dim]",
                     title="[bold bright_blue]DEPARTMENT STATUS", border_style="bright_blue")

    t = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    t.add_column("Dept",       style="bold bright_blue", width=14)
    t.add_column("Present",    style="green",             width=8)
    t.add_column("In Office",  style="cyan",              width=9)
    t.add_column("In Canteen", style="yellow",            width=10)

    for dept in depts:
        # DeptSummaryEntry: department, present, in_office, in_canteen
        t.add_row(
            dept.department,
            str(dept.present),
            str(dept.in_office),
            str(dept.in_canteen),
        )

    return Panel(t, title="[bold bright_blue]DEPARTMENT STATUS", border_style="bright_blue")


def _alerts_panel(s: state.Phase3State) -> Panel:
    """Display last 5 alerts. phase3_state.recent_alerts stores plain strings."""
    alerts = list(s.recent_alerts)[-5:]
    alerts.reverse()

    lines = []
    for entry in alerts:
        # Entries may be Alert objects (with .severity/.message/.timestamp)
        # or plain strings written by append_alert().
        if hasattr(entry, "severity"):
            sev  = entry.severity
            msg  = entry.message
            ts   = entry.timestamp
            ts_str = ts.strftime("%H:%M:%S") if ts else "–"
        else:
            sev, msg, ts_str = "info", str(entry), "–"
            # Try to parse "[HH:MM:SS] severity: message" format
            if entry.startswith("[") and "]" in entry:
                bracket_end = entry.index("]")
                ts_str = entry[1:bracket_end]
                rest   = entry[bracket_end + 2:]
                for sev_word in ("CRITICAL", "WARNING", "INFO"):
                    if rest.upper().startswith(sev_word):
                        sev = sev_word.lower()
                        msg = rest[len(sev_word):].lstrip(": ")
                        break
                else:
                    msg = rest

        colour = {"critical": "red", "warning": "yellow", "info": "green"}.get(
            sev.lower(), "white"
        )
        lines.append(
            f"[{colour}][{ts_str}] {sev.upper()}: {msg[:55]}[/{colour}]"
        )

    content = "\n".join(lines) if lines else "[dim]No alerts[/dim]"
    return Panel(content, title="[bold red]SMART ALERTS", border_style="red")


def _ai_panel(s: state.Phase3State) -> Panel:
    text = getattr(s, "ai_text", None) or "Awaiting first analysis…"
    ai_ts = getattr(s, "ai_timestamp", "–") or "–"
    meta  = f"\n[dim]Last: {ai_ts}[/dim]"
    return Panel(
        text + meta,
        title="[bold bright_cyan]AI ANALYSIS",
        border_style="bright_cyan",
    )


def _log_panel(s: state.Phase3State) -> Panel:
    tail = list(s.log_tail)[-8:]
    content = "\n".join(tail) if tail else "[dim]No events yet.[/dim]"
    return Panel(content, title="[bold blue]MOVEMENT LOG", border_style="blue")


# ─────────────────────────── layout assembly ─────────────────────────────────

def _render() -> Layout:
    s = state.get_state()

    layout = Layout()
    layout.split_column(
        Layout(name="row1", ratio=3),
        Layout(name="row2", ratio=3),
        Layout(name="row3", ratio=3),
        Layout(name="row4", ratio=2),
    )
    layout["row1"].split_row(
        Layout(_system_panel(s),     name="sys"),
        Layout(_people_panel(s),     name="ppl"),
        Layout(_attendance_panel(s), name="att"),
    )
    layout["row2"].split_row(
        Layout(_active_employees_panel(s), name="emps"),
        Layout(_active_visitors_panel(s),  name="vis"),
        Layout(_canteen_panel(s),          name="can"),
    )
    layout["row3"].split_row(
        Layout(_department_panel(s), name="dept"),
        Layout(_alerts_panel(s),     name="alrt"),
        Layout(_ai_panel(s),         name="ai"),
    )
    layout["row4"].update(_log_panel(s))
    return layout


# ─────────────────────────── Dashboard class ─────────────────────────────────

class Phase3Dashboard:
    """Rich Live terminal dashboard for CCTV Phase 3."""

    def __init__(self, config: AppConfig, refresh_rate: float = 0.5):
        self._refresh = refresh_rate
        self._live: Optional[Live] = None
        self._running = False

    def start(self) -> None:
        """Start the Rich Live display (call once)."""
        self._running = True
        self._live = Live(
            _render(),
            console=_console,
            refresh_per_second=max(1, int(1 / self._refresh)),
            screen=True,
        )
        self._live.start()

    def stop(self) -> None:
        """Stop the Rich Live display cleanly."""
        self._running = False
        if self._live:
            self._live.stop()

    def tick(self) -> None:
        """Call once per main-loop iteration to push a fresh render."""
        if self._live and self._running:
            self._live.update(_render())

    def set_cameras(self, camera_list: list) -> None:
        """Update the multi-camera list shown in SYSTEM STATUS.

        Parameters
        ----------
        camera_list : list of dicts, each with keys:
            ip (str), status (str), fps (float)
        """
        global _CAMERAS
        _CAMERAS = list(camera_list)


# ─────────────────────────── pre-flight helper ───────────────────────────────

def print_preflight_p3(cameras: list) -> None:
    """Print a startup verification table for Phase 3 cameras.

    Parameters
    ----------
    cameras : list of camera-result dicts with keys:
        ip, status, success (bool), width, height, fps, codec, error_message
    """
    from rich import box as rbox
    console = Console()
    console.rule("[bold yellow]PHASE 3 – PRE-FLIGHT VERIFICATION")

    t = Table(box=rbox.SIMPLE_HEAVY, show_header=True)
    t.add_column("Camera IP",  style="bold cyan",  width=18)
    t.add_column("Status",                          width=10)
    t.add_column("Resolution",                      width=14)
    t.add_column("FPS",                             width=6)
    t.add_column("Codec",                           width=10)
    t.add_column("Note",       style="dim",         width=30)

    for cam in cameras:
        ok         = cam.get("success", False)
        status_txt = Text("OK" if ok else "FAILED", style="green" if ok else "red")
        res        = f"{cam.get('width', '?')}x{cam.get('height', '?')}" if ok else "–"
        fps        = str(cam.get("fps", "–")) if ok else "–"
        cod        = cam.get("codec", "–") if ok else "–"
        note       = cam.get("error_message", "") if not ok else ""
        t.add_row(cam.get("ip", "–"), status_txt, res, fps, cod, note)

    console.print(t)
