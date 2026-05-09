"""Local backup/export utilities for StockBot."""

from __future__ import annotations

import logging
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from config import AppConfig, load_config


class BackupManager:
    """Create local backups without copying secrets."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.logger = logging.getLogger(__name__)

    def run_backup(self) -> Path:
        """Back up SQLite, watchlist config, and latest report artifacts."""
        backup_dir = self._new_backup_dir()
        backup_dir.mkdir(parents=True, exist_ok=True)

        self._backup_database(backup_dir)
        self._copy_if_exists(self.config.watchlist_path, backup_dir / "config" / self.config.watchlist_path.name)
        self._backup_reports(backup_dir)
        self.cleanup_old_backups()

        self.logger.info("Backup completed at %s", backup_dir)
        return backup_dir

    def cleanup_old_backups(self) -> None:
        """Remove backup folders older than BACKUP_KEEP_DAYS."""
        cutoff = datetime.now() - timedelta(days=max(self.config.backup_keep_days, 1))
        if not self.config.backups_dir.exists():
            return
        for path in self.config.backups_dir.iterdir():
            if not path.is_dir():
                continue
            try:
                modified = datetime.fromtimestamp(path.stat().st_mtime)
            except OSError:
                continue
            if modified < cutoff:
                shutil.rmtree(path, ignore_errors=True)

    def _new_backup_dir(self) -> Path:
        """Create a dated backup folder with a timestamp to avoid overwrites."""
        stamp = datetime.now().strftime("%Y-%m-%d/%H%M%S")
        return self.config.backups_dir / stamp

    def _backup_database(self, backup_dir: Path) -> None:
        """Use SQLite's backup API when the database exists."""
        if not self.config.database_path.exists():
            self.logger.warning("Database backup skipped because %s does not exist", self.config.database_path)
            return
        target = backup_dir / "database" / self.config.database_path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.config.database_path) as source:
            with sqlite3.connect(target) as destination:
                source.backup(destination)

    def _backup_reports(self, backup_dir: Path) -> None:
        """Copy generated reports while avoiding logs, env files, and source control data."""
        if not self.config.reports_dir.exists():
            return
        target_root = backup_dir / "reports"
        for source in self.config.reports_dir.rglob("*"):
            if not source.is_file():
                continue
            if source.name.lower() == ".env" or any(part in {".git", ".venv", "logs"} for part in source.parts):
                continue
            relative = source.relative_to(self.config.reports_dir)
            self._copy_if_exists(source, target_root / relative)

    def _copy_if_exists(self, source: Path, target: Path) -> None:
        """Copy a file if present."""
        if not source.exists() or not source.is_file():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def run_backup(config: AppConfig | None = None) -> Path:
    """Run a one-off backup."""
    manager = BackupManager(config or load_config())
    return manager.run_backup()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    backup_path = run_backup()
    print(f"Backup saved to: {backup_path}")
