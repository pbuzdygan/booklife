# Booklife data directory

Booklife stores its live SQLite database here:

```text
data/booklife.sqlite3
```

SQLite may create `booklife.sqlite3-wal` and `booklife.sqlite3-shm` beside it.
The whole directory must stay on one reliable local filesystem and be writable
only by the application user. Never publish this directory as static content.
The database, temporary SQLite files, and generated backups are excluded from
version control and from the container image.

Processed book covers are stored in `data/covers/`, and protected attachment
files are stored in `data/attachments/`. SQLite contains only their metadata and
random storage names. Each folder is created only when its first accepted file
is saved, so its absence in a new installation is normal. Both folders are
private application data: include them in backups, never serve them as static
directories, and never expose them directly
through a web server. If a file is missing, Booklife keeps working and omits the
missing attachment or displays the standard cover placeholder.

## Backup and recovery

Create a consistent snapshot with:

```bash
docker compose run --rm web python manage.py backup_booklife --output-dir /app/data/backups
```

Container backups go to `data/backups/`. The command uses SQLite's online backup
mechanism and verifies the new snapshot. Move long-term copies to encrypted
storage outside the machine and apply a retention policy appropriate for the
library. Do not use a generic file copy for the active SQLite database itself.

To rehearse recovery safely:

1. Stop the Booklife application.
2. Keep the current `data/` directory intact as a rollback copy.
3. Place the chosen verified database backup in a new empty recovery directory
   and name it `booklife.sqlite3`. Restore the matching `covers/` and
   `attachments/` folders when they are part of the backup set.
4. Point `BOOKLIFE_DATA_DIR` to that directory.
5. Run `docker compose run --rm web python manage.py check_database --full`, then
   start Booklife and verify sign-in, the library list, a book detail, and JSON
   export.
6. Switch the application to the recovered directory only after those checks
   pass.

Do not overwrite the only live copy during a recovery rehearsal. After an
unclean stop, keep any `-wal` and `-shm` files beside the database so SQLite can
complete its own recovery.
