#!/usr/bin/env python3
"""
enrollment_cli.py – Command-line tool for enrolling employees into Phase 3.

Sub-command usage:
  python enrollment_cli.py add --id EMP001 --name "Ram Sharma" --dept "Finance" --dir photos/ram/
  python enrollment_cli.py add --id EMP002 --name "Sita KC" --dept "HR" --images img1.jpg img2.jpg
  python enrollment_cli.py update --id EMP001 --dept "Administration"
  python enrollment_cli.py reenroll --id EMP001 --dir photos/emp001/
  python enrollment_cli.py deactivate --id EMP001
  python enrollment_cli.py delete --id EMP001
  python enrollment_cli.py list
  python enrollment_cli.py status --id EMP001

Direct (API) usage — no subcommand needed:
  python enrollment_cli.py --id EMP001 --name "Ram Sharma" --dept "Finance" --images img1.jpg img2.jpg
  python enrollment_cli.py --id EMP001 --name "Ram Sharma" --dept "Finance" --dir photos/ram/ --json
"""

import argparse
import sys
import os

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()


# ---------------------------------------------------------------------------
# Bootstrap: load config and initialise engines
# ---------------------------------------------------------------------------
def _bootstrap():
    """
    Load config and initialise all required components.
    Returns (face_engine, db_manager, db_p3, enrollment) or raises SystemExit.
    """
    try:
        from config_manager import load_config
        cfg = load_config()
    except FileNotFoundError as exc:
        console.print(f"[bold red]Config error:[/bold red] {exc}")
        sys.exit(1)
    except Exception as exc:
        console.print(f"[bold red]Failed to load config:[/bold red] {exc}")
        sys.exit(1)

    if not cfg.database.enabled:
        console.print(
            "[bold yellow]Warning:[/bold yellow] Database is disabled in config.ini "
            "(DATABASE.enabled = false). Enrollment requires a database connection."
        )

    try:
        from db_manager import DatabaseManager
        db_manager = DatabaseManager(cfg.database)
    except Exception as exc:
        console.print(f"[bold red]Database connection failed:[/bold red] {exc}")
        sys.exit(1)

    try:
        from db_manager_p3 import DatabaseManagerP3
        db_p3 = DatabaseManagerP3(db_manager)
    except Exception as exc:
        console.print(f"[bold red]Phase 3 database init failed:[/bold red] {exc}")
        sys.exit(1)

    try:
        from face_recognition_engine import FaceRecognitionEngine
        face_engine = FaceRecognitionEngine(
            backend=cfg.gender.backend,
            model_dir="models/face",
        )
    except Exception as exc:
        console.print(f"[bold red]Face engine init failed:[/bold red] {exc}")
        sys.exit(1)

    try:
        from face_enrollment import FaceEnrollment
        enrollment = FaceEnrollment(face_engine, db_p3)
    except Exception as exc:
        console.print(f"[bold red]Enrollment module init failed:[/bold red] {exc}")
        sys.exit(1)

    return face_engine, db_manager, db_p3, enrollment


# ---------------------------------------------------------------------------
# Sub-command handlers
# ---------------------------------------------------------------------------
def cmd_add(args, enrollment) -> int:
    """Add a new employee."""
    if not args.id or not args.name or not args.dept:
        console.print("[bold red]Error:[/bold red] --id, --name and --dept are required for 'add'.")
        return 1

    if args.dir:
        result = enrollment.enroll_from_directory(
            employee_id=args.id,
            name=args.name,
            department=args.dept,
            designation=args.designation or "",
            image_dir=args.dir,
        )
    elif args.images:
        result = enrollment.add_employee(
            employee_id=args.id,
            name=args.name,
            department=args.dept,
            designation=args.designation or "",
            image_paths=args.images,
        )
    else:
        console.print("[bold red]Error:[/bold red] Provide either --dir or --images.")
        return 1

    _print_result(result)
    return 0 if result.success else 1


def cmd_update(args, enrollment) -> int:
    """Update employee metadata."""
    if not args.id:
        console.print("[bold red]Error:[/bold red] --id is required for 'update'.")
        return 1

    if not any([args.name, args.dept, args.designation]):
        console.print("[bold red]Error:[/bold red] Provide at least one of --name, --dept, --designation.")
        return 1

    result = enrollment.update_employee(
        employee_id=args.id,
        name=args.name,
        department=args.dept,
        designation=args.designation,
    )
    _print_result(result)
    return 0 if result.success else 1


def cmd_reenroll(args, enrollment) -> int:
    """Re-enroll face data for an employee."""
    if not args.id:
        console.print("[bold red]Error:[/bold red] --id is required for 'reenroll'.")
        return 1

    if args.dir:
        # Collect images from directory
        image_dir = args.dir
        if not os.path.isdir(image_dir):
            console.print(f"[bold red]Error:[/bold red] Directory not found: {image_dir}")
            return 1
        image_paths = [
            os.path.join(image_dir, f)
            for f in sorted(os.listdir(image_dir))
            if f.lower().endswith((".jpg", ".jpeg", ".png"))
        ]
    elif args.images:
        image_paths = args.images
    else:
        console.print("[bold red]Error:[/bold red] Provide either --dir or --images.")
        return 1

    result = enrollment.re_enroll_face(employee_id=args.id, image_paths=image_paths)
    _print_result(result)
    return 0 if result.success else 1


def cmd_deactivate(args, enrollment) -> int:
    """Deactivate an employee."""
    if not args.id:
        console.print("[bold red]Error:[/bold red] --id is required for 'deactivate'.")
        return 1

    console.print(f"Deactivating employee [bold]{args.id}[/bold] …")
    result = enrollment.deactivate_employee(args.id)
    _print_result(result)
    return 0 if result.success else 1


def cmd_delete(args, enrollment) -> int:
    """Delete an employee and all their face data."""
    if not args.id:
        console.print("[bold red]Error:[/bold red] --id is required for 'delete'.")
        return 1

    console.print(
        f"[bold yellow]Warning:[/bold yellow] This will permanently delete employee "
        f"[bold]{args.id}[/bold] and all their face embeddings."
    )
    try:
        confirm = input("Type 'yes' to confirm: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        console.print("\nAborted.")
        return 1

    if confirm != "yes":
        console.print("Aborted.")
        return 0

    result = enrollment.delete_employee(args.id)
    _print_result(result)
    return 0 if result.success else 1


def cmd_list(args, enrollment, db_p3) -> int:
    """List all employees and their enrollment status."""
    try:
        employees = db_p3.get_all_active_employees()
    except Exception as exc:
        console.print(f"[bold red]Error fetching employee list:[/bold red] {exc}")
        return 1

    if not employees:
        console.print("[yellow]No active employees found in the database.[/yellow]")
        return 0

    table = Table(
        title="Enrolled Employees",
        box=box.ROUNDED,
        show_lines=True,
        header_style="bold cyan",
    )
    table.add_column("ID",          style="bold",         no_wrap=True)
    table.add_column("Name",        style="white")
    table.add_column("Department",  style="dim white")
    table.add_column("Designation", style="dim white")
    table.add_column("Images",      justify="right",  style="green")
    table.add_column("Last Enrolled", style="dim")

    for emp in employees:
        status_info = enrollment.get_enrollment_status(emp["employee_id"])
        image_count   = str(status_info.get("image_count",   0))
        last_enrolled = str(status_info.get("last_enrolled", "Never"))

        table.add_row(
            emp["employee_id"],
            emp["employee_name"],
            emp["department"],
            emp.get("designation", ""),
            image_count,
            last_enrolled,
        )

    console.print(table)
    return 0


def cmd_status(args, enrollment) -> int:
    """Show enrollment status for a single employee."""
    if not args.id:
        console.print("[bold red]Error:[/bold red] --id is required for 'status'.")
        return 1

    info = enrollment.get_enrollment_status(args.id)
    if not info:
        console.print(f"[bold red]Employee not found:[/bold red] {args.id}")
        return 1

    status_colour = {
        "active":   "green",
        "inactive": "yellow",
        "deleted":  "red",
    }.get(info.get("status", ""), "white")

    panel_text = (
        f"[bold]Employee ID:[/bold]   {info['employee_id']}\n"
        f"[bold]Name:[/bold]          {info['name']}\n"
        f"[bold]Department:[/bold]    {info['department']}\n"
        f"[bold]Designation:[/bold]   {info.get('designation', '')}\n"
        f"[bold]Status:[/bold]        [{status_colour}]{info['status']}[/{status_colour}]\n"
        f"[bold]Face Images:[/bold]   {info['image_count']}\n"
        f"[bold]Last Enrolled:[/bold] {info['last_enrolled']}"
    )
    console.print(Panel(panel_text, title=f"Enrollment Status – {args.id}", expand=False))
    return 0


# ---------------------------------------------------------------------------
# Output helper
# ---------------------------------------------------------------------------
def _print_result(result) -> None:
    if result.success:
        msg = f"[bold green]SUCCESS[/bold green]  {result.message}"
        if result.embedding_count:
            msg += f"  ([green]{result.embedding_count} embedding(s)[/green])"
    else:
        msg = f"[bold red]FAILED[/bold red]  {result.message}"
    console.print(msg)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="enrollment_cli.py",
        description="CCTV Phase 3 – Employee Face Enrollment CLI",
    )
    # Top-level (direct / API mode) args — used when no subcommand is given
    parser.add_argument("--id",          default=None, help="Employee ID (direct mode)")
    parser.add_argument("--name",        default=None, help="Full name (direct mode)")
    parser.add_argument("--dept",        default=None, help="Department (direct mode)")
    parser.add_argument("--designation", default=None, help="Job title (direct mode)")
    parser.add_argument("--dir",         default=None, help="Image directory (direct mode)")
    parser.add_argument("--images",      nargs="+",    default=None, metavar="IMAGE",
                        help="Image file paths (direct mode)")
    parser.add_argument("--json",        action="store_true",
                        help="Output result as JSON (for API callers)")

    sub = parser.add_subparsers(dest="command")  # not required — enables direct mode

    # ── add ──────────────────────────────────────────────────────────────────
    p_add = sub.add_parser("add", help="Enroll a new employee")
    p_add.add_argument("--id",          required=True,  help="Employee ID (e.g. EMP001)")
    p_add.add_argument("--name",        required=True,  help="Full name")
    p_add.add_argument("--dept",        required=True,  help="Department")
    p_add.add_argument("--designation", default="",     help="Job title / designation (optional)")
    _add_image_args(p_add)

    # ── update ────────────────────────────────────────────────────────────────
    p_upd = sub.add_parser("update", help="Update employee metadata")
    p_upd.add_argument("--id",          required=True)
    p_upd.add_argument("--name",        default=None)
    p_upd.add_argument("--dept",        default=None)
    p_upd.add_argument("--designation", default=None)

    # ── reenroll ──────────────────────────────────────────────────────────────
    p_re = sub.add_parser("reenroll", help="Replace all face data for an employee")
    p_re.add_argument("--id", required=True)
    _add_image_args(p_re)

    # ── deactivate ────────────────────────────────────────────────────────────
    p_deact = sub.add_parser("deactivate", help="Deactivate an employee")
    p_deact.add_argument("--id", required=True)

    # ── delete ────────────────────────────────────────────────────────────────
    p_del = sub.add_parser("delete", help="Permanently delete an employee and their face data")
    p_del.add_argument("--id", required=True)

    # ── list ──────────────────────────────────────────────────────────────────
    sub.add_parser("list", help="List all enrolled employees")

    # ── status ────────────────────────────────────────────────────────────────
    p_stat = sub.add_parser("status", help="Show enrollment status for one employee")
    p_stat.add_argument("--id", required=True)

    return parser


def _add_image_args(parser: argparse.ArgumentParser) -> None:
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument(
        "--dir",
        default=None,
        help="Directory containing face images (jpg/jpeg/png)",
    )
    grp.add_argument(
        "--images",
        nargs="+",
        default=None,
        metavar="IMAGE",
        help="Space-separated list of image file paths",
    )


def _json_result(result, use_json: bool) -> None:
    """Print result as JSON when --json flag is set; also print plain text."""
    if use_json:
        import json
        data = {
            "success": result.success,
            "message": result.message,
            "embedding_count": getattr(result, "embedding_count", 0) or 0,
        }
        print(json.dumps(data))
    else:
        _print_result(result)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> int:
    parser = _build_parser()
    args   = parser.parse_args()

    use_json = getattr(args, "json", False)

    # Direct / API mode: no subcommand but --id and --name provided
    if not args.command:
        if args.id and args.name:
            # Treat as "add"
            if not use_json:
                console.print(
                    Panel(
                        "[bold cyan]CCTV Phase 3 – Enrollment CLI (direct mode)[/bold cyan]",
                        expand=False,
                    )
                )
            _face_engine, _db_manager, _db_p3, enrollment = _bootstrap()
            try:
                result = _direct_enroll(args, enrollment)
                _json_result(result, use_json)
                if not use_json and result.success:
                    print(
                        f"Enrolled {getattr(result, 'embedding_count', 0) or 0} "
                        f"embeddings for {args.name} ({args.id})"
                    )
                return 0 if result.success else 1
            except Exception as exc:
                if use_json:
                    import json
                    print(json.dumps({"success": False, "message": str(exc), "embedding_count": 0}))
                else:
                    console.print(f"[bold red]Unexpected error:[/bold red] {exc}")
                return 1
        else:
            parser.print_help()
            return 1

    if not use_json:
        console.print(
            Panel(
                "[bold cyan]CCTV Phase 3 – Enrollment CLI[/bold cyan]",
                expand=False,
            )
        )

    _face_engine, _db_manager, db_p3, enrollment = _bootstrap()

    dispatch = {
        "add":        lambda: cmd_add(args, enrollment),
        "update":     lambda: cmd_update(args, enrollment),
        "reenroll":   lambda: cmd_reenroll(args, enrollment),
        "deactivate": lambda: cmd_deactivate(args, enrollment),
        "delete":     lambda: cmd_delete(args, enrollment),
        "list":       lambda: cmd_list(args, enrollment, db_p3),
        "status":     lambda: cmd_status(args, enrollment),
    }

    handler = dispatch.get(args.command)
    if handler is None:
        console.print(f"[bold red]Unknown command:[/bold red] {args.command}")
        return 1

    try:
        return handler()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user.[/yellow]")
        return 1
    except Exception as exc:
        console.print(f"[bold red]Unexpected error:[/bold red] {exc}")
        return 1


def _direct_enroll(args, enrollment):
    """Run enrollment from direct-mode args (no subcommand)."""
    if args.dir:
        return enrollment.enroll_from_directory(
            employee_id=args.id,
            name=args.name,
            department=args.dept or "General",
            designation=args.designation or "",
            image_dir=args.dir,
        )
    elif args.images:
        return enrollment.add_employee(
            employee_id=args.id,
            name=args.name,
            department=args.dept or "General",
            designation=args.designation or "",
            image_paths=args.images,
        )
    else:
        raise ValueError("Provide --dir or --images for enrollment")


if __name__ == "__main__":
    sys.exit(main())
