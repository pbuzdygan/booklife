from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Run SQLite quick_check or the full integrity_check."

    def add_arguments(self, parser):
        parser.add_argument("--full", action="store_true", help="Run the slower full integrity check.")

    def handle(self, *args, **options):
        pragma = "integrity_check" if options["full"] else "quick_check"
        with connection.cursor() as cursor:
            cursor.execute(f"PRAGMA {pragma}")
            rows = [row[0] for row in cursor.fetchall()]
        if rows != ["ok"]:
            raise CommandError(f"SQLite {pragma} failed: {'; '.join(rows)}")
        self.stdout.write(self.style.SUCCESS(f"SQLite {pragma}: ok"))
