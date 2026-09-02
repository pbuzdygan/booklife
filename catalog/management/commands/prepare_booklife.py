from __future__ import annotations

import sqlite3
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


DEFAULT_USERNAME = "booklife"
DEFAULT_PASSWORD = "booklife"


def database_has_personal_data(database_path: Path) -> bool:
    if not database_path.exists() or database_path.stat().st_size == 0:
        return False
    try:
        uri = f"file:{database_path.resolve().as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as database:
            table_names = {
                row[0]
                for row in database.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
            for table_name in ("auth_user", "catalog_library", "catalog_book"):
                if table_name in table_names:
                    count = database.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
                    if count:
                        return True
    except sqlite3.DatabaseError as exc:
        raise CommandError(
            "The existing Booklife database is not a valid readable SQLite database. "
            "It was left untouched; restore it from a verified backup."
        ) from exc
    return False


def create_first_run_user() -> tuple[object, bool]:
    user_model = get_user_model()
    user, created = user_model.objects.get_or_create(username=DEFAULT_USERNAME)
    if created:
        user.set_password(DEFAULT_PASSWORD)
        user.is_staff = False
        user.is_superuser = False
        user.save(update_fields=("password", "is_staff", "is_superuser"))
    return user, created


class Command(BaseCommand):
    help = "Prepare a brand-new Booklife database, or refuse to start with pending migrations."

    def handle(self, *args, **options):
        database_path = Path(settings.DATABASES["default"]["NAME"])
        fresh_database = not database_has_personal_data(database_path)

        if fresh_database:
            self.stdout.write("No Booklife user data was found. Preparing a new installation...")
            call_command("migrate", interactive=False, verbosity=1)
            _, created = create_first_run_user()
            if not created:
                raise CommandError("The new database could not receive its first-run account.")
            self.stdout.write(self.style.SUCCESS("New Booklife database created successfully."))
            self.stdout.write(
                self.style.WARNING(
                    "\n"
                    "============================================================\n"
                    "FIRST-RUN ACCOUNT CREATED\n"
                    "Username: booklife\n"
                    "Temporary password: booklife\n"
                    "\n"
                    "This password is public and must be changed immediately:\n"
                    "docker compose run --rm web python manage.py changepassword booklife\n"
                    "\n"
                    "To create a separate administrator account, run:\n"
                    "docker compose run --rm web python manage.py createsuperuser\n"
                    "============================================================"
                )
            )
            return

        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()
        if executor.migration_plan(targets):
            raise CommandError(
                "Booklife cannot start: this existing database has pending migrations. "
                "Create a backup, then run: docker compose run --rm web python manage.py migrate"
            )

        self.stdout.write(self.style.SUCCESS("Booklife database is ready."))
