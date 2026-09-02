from __future__ import annotations

import logging
import os
from pathlib import Path

from django.db.backends.signals import connection_created
from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Attachment, Book
from .storage import delete_attachment_file, delete_cover


logger = logging.getLogger(__name__)


@receiver(connection_created, dispatch_uid="booklife_secure_sqlite_files")
def secure_sqlite_files(sender, connection, **kwargs):
    """Keep the private database and its sidecar files owner-readable only."""

    if connection.vendor != "sqlite":
        return

    database_name = connection.settings_dict.get("NAME")
    if not database_name or str(database_name) == ":memory:":
        return

    database_path = Path(database_name)
    candidates = (
        database_path,
        Path(f"{database_path}-wal"),
        Path(f"{database_path}-shm"),
    )
    try:
        for path in candidates:
            if path.exists():
                os.chmod(path, 0o600)
    except OSError as exc:
        logger.warning("Could not restrict SQLite file permissions: %s", exc)


@receiver(post_delete, sender=Book, dispatch_uid="booklife_delete_book_cover")
def delete_book_cover(sender, instance, **kwargs):
    if instance.cover_filename:
        filename = instance.cover_filename
        transaction.on_commit(lambda: delete_cover(filename))


@receiver(post_delete, sender=Attachment, dispatch_uid="booklife_delete_attachment_file")
def delete_attachment(sender, instance, **kwargs):
    filename = instance.stored_filename
    transaction.on_commit(lambda: delete_attachment_file(filename))
