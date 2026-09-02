from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections


class Command(BaseCommand):
    help = "Create and verify a consistent SQLite backup using the SQLite backup API."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default=str(settings.BASE_DIR / "backups"),
            help="Directory for the backup file. Prefer a different disk from the live database.",
        )

    def handle(self, *args, **options):
        source_path = Path(settings.DATABASES["default"]["NAME"]).resolve()
        if not source_path.exists():
            raise CommandError(f"Database does not exist: {source_path}")

        output_dir = Path(options["output_dir"]).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination_path = output_dir / f"booklife-{timestamp}.sqlite3"
        if destination_path.exists():
            raise CommandError(f"Backup already exists: {destination_path}")

        connections.close_all()
        source_uri = f"file:{source_path.as_posix()}?mode=ro"
        try:
            with sqlite3.connect(source_uri, uri=True) as source:
                with sqlite3.connect(destination_path) as destination:
                    source.backup(destination)
                    result = destination.execute("PRAGMA quick_check").fetchone()[0]
                    if result != "ok":
                        raise CommandError(f"Backup verification failed: {result}")
        except Exception:
            destination_path.unlink(missing_ok=True)
            raise

        os.chmod(destination_path, 0o600)
        self.stdout.write(self.style.SUCCESS(f"Verified backup created: {destination_path}"))
