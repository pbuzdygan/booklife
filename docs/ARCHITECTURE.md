# Booklife architecture

Booklife is a deliberately small, private modular monolith: one repository, one
Django web application, one SQLite database, and one container service. It is
designed for one running application instance and a small number of trusted
users, rather than horizontal scaling.

## System overview

```text
Browser / installed PWA
          |
          v
Django + Gunicorn container
          |
          +-- SQLite database: /app/data/booklife.sqlite3
          +-- Covers:          /app/data/covers/
          +-- Attachments:     /app/data/attachments/
          +-- Backups:         /app/data/backups/
```

The PWA caches only public application assets such as CSS, JavaScript, icons,
and the web manifest. Authenticated HTML and private library data are always
fetched from the server and are never kept in the offline cache.

## Application design

- **Framework:** Django 5.2 LTS on Python 3.14.
- **HTTP interface:** server-rendered Django templates with small local
  JavaScript modules where browser capabilities add value, such as ISBN barcode
  scanning and PWA installation.
- **Domain module:** `catalog` owns books, categories, lifecycle events,
  attachments, forms, views, storage, and management commands.
- **Authentication:** Django authentication with no public registration. Each
  user owns one library, and application queries enforce that ownership boundary.
  Sessions end with the browser, have a fixed 12-hour maximum lifetime, and are
  invalidated when the application process restarts.
- **Static assets:** WhiteNoise serves versioned production assets. PWA branding
  sources live in `branding/`; application copies live under
  `catalog/static/catalog/icons/`.

## Data and storage

SQLite is an intentional production choice for the expected scale. The live
database is `data/booklife.sqlite3`; covers and attachments remain outside the
database so database backups stay compact and file access can be authorised by
the application.

Operating rules:

- keep `data/` on a local filesystem with reliable locking, never NFS or a
  synchronised network folder;
- mount the whole directory because SQLite can create `-wal` and `-shm` files;
- use WAL mode, a five-second busy timeout, foreign-key enforcement, and safe
  synchronous writes;
- run one application container against the database;
- make migrations and backups explicit maintenance operations;
- use `check_database` for `quick_check` or `integrity_check`, and use the
  SQLite backup API through `backup_booklife` instead of copying a live file.

## Container operation

The `web` service in `compose.yaml` is the only runtime service. It runs as a
non-root user, has a read-only application filesystem, and can write only to
the mounted `data/` directory and a small temporary filesystem. On startup it
prepares an empty database or refuses to run when an existing database has
pending migrations.

Configuration is provided through `.env`, with `.env.example` documenting safe
local defaults. The application binds to `127.0.0.1` by default. HTTPS and
trusted reverse-proxy settings are documented in the root README.

## Delivery automation

GitHub Actions has two independent responsibilities:

- `quality.yml` runs Django checks, migration checks, tests, and static-file
  collection for pushes and pull requests to `main` and `dev`. It does not build
  a Docker image.
- `release-build.yml` builds a Docker image only after a GitHub Release targeted
  at `main` or `dev` is published. The image is validated in GitHub Actions but
  is not pushed to a registry or deployed automatically.

## Deliberate boundaries

- Booklife is not a distributed application and must not run several writers
  against one SQLite database.
- The `data/` directory, `.env`, and are excluded from Git and container images.
- A separate native iOS/Android application, public APIs, remote sync, and
  spreadsheet import are outside the current architecture.
