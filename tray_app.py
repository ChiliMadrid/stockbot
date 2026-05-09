"""Optional Windows tray/status controls for StockBot."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

from backup_manager import run_backup
from config import AppConfig, load_config
from dashboard_exporter import export_dashboard
from health_check import has_failures, run_health_checks


def read_status(config: AppConfig) -> dict:
    """Read bot status without exposing secrets."""
    if not config.bot_status_file.exists():
        return {"status": "unknown", "message": "No status file yet."}
    try:
        return json.loads(config.bot_status_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "error", "message": "Status file could not be read."}


def write_pause(config: AppConfig, paused: bool) -> None:
    """Create or remove the pause flag read by main.py."""
    config.bot_pause_file.parent.mkdir(parents=True, exist_ok=True)
    if paused:
        config.bot_pause_file.write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
    elif config.bot_pause_file.exists():
        config.bot_pause_file.unlink()


def open_dashboard(config: AppConfig) -> None:
    """Open the latest dashboard in the default browser."""
    dashboard_path = config.dashboard_dir / "dashboard_latest.html"
    if not dashboard_path.exists():
        export_dashboard(config)
    webbrowser.open(dashboard_path.resolve().as_uri())


def open_logs_folder(config: AppConfig) -> None:
    """Open the logs folder on Windows."""
    config.log_file.parent.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(["explorer", str(config.log_file.parent.resolve())])


def run_health_check(config: AppConfig) -> str:
    """Run health checks and return a short status string."""
    results = run_health_checks()
    status = "FAIL" if has_failures(results) else "PASS"
    return f"Health check: {status} ({len(results)} checks)"


def run_console_menu(config: AppConfig) -> None:
    """Fallback menu when tray dependencies are unavailable."""
    actions = {
        "1": ("Show status", lambda: print(json.dumps(read_status(config), indent=2))),
        "2": ("Open dashboard", lambda: open_dashboard(config)),
        "3": ("Run health check", lambda: print(run_health_check(config))),
        "4": ("Export dashboard now", lambda: print(export_dashboard(config)["dashboard_latest"])),
        "5": ("Pause monitoring", lambda: write_pause(config, True)),
        "6": ("Resume monitoring", lambda: write_pause(config, False)),
        "7": ("Open logs folder", lambda: open_logs_folder(config)),
        "8": ("Run backup now", lambda: print(run_backup(config))),
        "9": ("Quit", None),
    }
    while True:
        print("\nStockBot Tray Fallback")
        for key, (label, _) in actions.items():
            print(f"{key}. {label}")
        choice = input("Choose: ").strip()
        if choice == "9":
            return
        action = actions.get(choice)
        if action is None:
            print("Unknown option.")
            continue
        try:
            action[1]()
        except Exception as exc:
            print(f"Action failed: {exc}")


def run_tray_app(config: AppConfig | None = None) -> None:
    """Run the optional tray app, falling back to a console menu when unavailable."""
    config = config or load_config()
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        print("Tray dependencies are not installed. Using console fallback.")
        print("Optional packages for a real tray icon: pystray pillow")
        run_console_menu(config)
        return

    def icon_image() -> Image.Image:
        image = Image.new("RGB", (64, 64), "#101215")
        draw = ImageDraw.Draw(image)
        draw.ellipse((14, 14, 50, 50), fill="#6ec6a4")
        draw.rectangle((28, 20, 36, 44), fill="#101215")
        return image

    def menu_status(_icon, _item):
        status = read_status(config)
        print(f"StockBot status: {status.get('status')} - {status.get('message', '')}")

    def menu_open_dashboard(_icon, _item):
        open_dashboard(config)

    def menu_health(_icon, _item):
        print(run_health_check(config))

    def menu_export(_icon, _item):
        print(export_dashboard(config)["dashboard_latest"])

    def menu_pause(_icon, _item):
        write_pause(config, True)

    def menu_resume(_icon, _item):
        write_pause(config, False)

    def menu_logs(_icon, _item):
        open_logs_folder(config)

    def menu_quit(icon, _item):
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Show status", menu_status),
        pystray.MenuItem("Open dashboard", menu_open_dashboard),
        pystray.MenuItem("Run health check", menu_health),
        pystray.MenuItem("Export dashboard now", menu_export),
        pystray.MenuItem("Pause monitoring", menu_pause),
        pystray.MenuItem("Resume monitoring", menu_resume),
        pystray.MenuItem("Open logs folder", menu_logs),
        pystray.MenuItem("Quit tray app", menu_quit),
    )
    icon = pystray.Icon("StockBot", icon_image(), "StockBot", menu)
    icon.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if not load_config().enable_tray_app:
        print("ENABLE_TRAY_APP=false. Starting manual tray controls anyway.")
    run_tray_app()
