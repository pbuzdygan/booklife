import sqlite3

from django.core.checks import Error, Warning, register


MINIMUM_SQLITE = (3, 31, 0)
RECOMMENDED_SQLITE = (3, 51, 3)


@register()
def check_sqlite_version(app_configs, **kwargs):
    version = sqlite3.sqlite_version_info
    if version < MINIMUM_SQLITE:
        return [
            Error(
                f"SQLite {sqlite3.sqlite_version} is too old for Booklife.",
                hint="Use SQLite 3.31.0 or newer.",
                id="booklife.E001",
            )
        ]
    if version < RECOMMENDED_SQLITE:
        return [
            Warning(
                f"SQLite {sqlite3.sqlite_version} is supported but older than the recommended patched line.",
                hint="Use SQLite 3.51.3 or newer for improved WAL safety.",
                id="booklife.W001",
            )
        ]
    return []
