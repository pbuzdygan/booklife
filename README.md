# Booklife

> Every book has a life beyond its pages.

Booklife 0.1.0 is a private, lightweight digital library for books you own,
want to buy, plan to read, have finished, loaned, or passed on. Its interface
uses direction: compact, calm, and practical, with the familiar efficiency of a list tool but its own visual identity.

The application is an English-language Django monolith backed by one SQLite
database at `data/booklife.sqlite3`.

For privacy, Booklife signs a user out when the browser session ends. An active
sign-in also expires after at most 12 hours, or immediately after the Booklife
container restarts.

## What works in 0.1.0

- private sign-in with no public registration;
- isolated libraries for administratively created accounts;
- add, inspect, edit, search, filter, sort, trash, restore, and permanently
  remove books;
- compact table, cover layout, responsive mobile list, and keyboard shortcuts;
- saved views for the queue, wishlist, read books, loans, journal, and trash;
- independent reading and ownership states, categories, ratings, page counts,
  finish dates, shelf details, and plain-text notes;
- Settings-based category management, optional processed covers, and protected
  book attachments;
- ISBN-10/ISBN-13 lookup that can fill the title, author, and processed cover,
  with camera barcode scanning on modern mobile browsers;
- automatic lifecycle history for meaningful status changes;
- owner-scoped JSON export;
- installable PWA with application assets cached safely, without caching private
  library pages offline;
- verified SQLite integrity checks and consistent online backups.

The detailed scope and visible progress are in [docs/PLAN.md](docs/PLAN.md).
Technical structure and operating rules are in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Start Booklife

An end user needs Docker with Docker Compose and the commonly available OpenSSL
command. Python, Django, SQLite, and other development tools do not need to be
installed on the host computer.

First copy `.env.example` to `.env`. On Linux or macOS:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Generate the private application key once:

```bash
openssl rand -hex 32
```

This prints 32 cryptographically random bytes as 64 hexadecimal characters.
Copy the complete result into `.env`:

```dotenv
BOOKLIFE_SECRET_KEY=paste-the-generated-64-character-value-here
```

Then build and start Booklife:

```bash
docker compose build
docker compose up -d
```

When `data/booklife.sqlite3` does not exist, Booklife creates the database and a
first-run account automatically. Open `http://127.0.0.1:8019` and sign in with
username `booklife` and temporary password `booklife`. The first sign-in creates
its private library and a small set of starter categories.

Change the public temporary password immediately:

```bash
docker compose run --rm web python manage.py changepassword booklife
```

Python is not required on the host; this command runs inside the container.

### Login credentials

Only a completely new database receives the temporary `booklife` / `booklife`
account. Its credentials and the password-change command are printed clearly in
the container logs. The account is a regular private-library user, not a site
administrator.

#### Regular users and superusers

Booklife deliberately separates everyday library access from site
administration:

| Capability | Regular user | Superuser |
|---|---:|---:|
| Sign in to Booklife and use the normal library interface | Yes | Yes |
| Add, edit, categorise, export, trash, and restore books in their own library | Yes | Yes |
| Upload covers and attachments for books in their own library | Yes | Yes |
| See another user's private library in the normal interface | No | No |
| Open the Django administration site at `/admin/` | No | Yes |
| Create, edit, deactivate, or delete user accounts | No | Yes |
| Inspect or change other users' libraries and records through `/admin/` | No | Yes |
| Grant elevated permissions to another account | No | Yes |

The automatically created `booklife` account is a **regular user**. It is the
safer account for daily use because a mistake cannot affect other accounts. A
superuser is intended only for administration and should have a separate,
strong password. Although a superuser has broad access through `/admin/`, the
normal Booklife interface still opens that superuser's own private library; it
does not combine every user's books into one library.

Anyone who can use the host terminal and run Docker management commands should
also be treated as an administrator: they can create accounts or access the
persistent `data` directory outside Booklife's web permissions.

To create a separate administrator account from the folder containing
`compose.yaml`, run:

```bash
docker compose run --rm web python manage.py createsuperuser
```

Enter a username, optionally enter an email address, then enter the password
twice. The terminal intentionally shows no characters while a password is being
typed. Public registration remains unavailable.

If the password is later forgotten, replace `YOUR_USERNAME` and set a new one:

```bash
docker compose run --rm web python manage.py changepassword YOUR_USERNAME
```

### Access from the local network

The secure default publishes Booklife only on the same computer. To open it from
another device on a trusted home network, set these values in `.env`, replacing
the example IP with the Booklife host's LAN address:

```dotenv
BOOKLIFE_BIND_ADDRESS=0.0.0.0
BOOKLIFE_PORT=8019
BOOKLIFE_ALLOWED_HOSTS=localhost,127.0.0.1,your.server.ip.address
BOOKLIFE_CSRF_TRUSTED_ORIGINS=http://your.server.ip.address:8019
BOOKLIFE_SECURE_COOKIES=false
BOOKLIFE_SECURE_SSL_REDIRECT=false
```

Recreate the container after changing `.env`, then open
`http://your.server.ip.address:8019`. If it is still unreachable, allow inbound TCP port
8019 in the host firewall. Plain HTTP should be used only on a trusted private
network. For access outside that network, place Booklife behind HTTPS and enable
secure cookies and HTTPS redirection.

A mobile browser may warn that the sign-in form is not secure while this HTTP
setup is used. That warning is accurate: do not enter a Booklife password over
an untrusted network. An installed PWA also requires HTTPS outside `localhost`.

#### Trusted HTTPS reverse proxy alongside local HTTP

Booklife can remain reachable over plain HTTP inside a trusted lab network and
also use HTTPS through Nginx Proxy Manager. Add both exact browser origins and
enable proxy-header trust in the installation's `.env`:

```dotenv
BOOKLIFE_ALLOWED_HOSTS=localhost,127.0.0.1,your.server.ip.address,books.example.test
BOOKLIFE_CSRF_TRUSTED_ORIGINS=http://your.server.ip.address:8019,https://books.example.test
BOOKLIFE_TRUST_PROXY_HEADERS=true
BOOKLIFE_SECURE_COOKIES=false
BOOKLIFE_SECURE_SSL_REDIRECT=false
```

Replace `books.example.test` with the real proxy hostname. Nginx Proxy Manager
must replace `X-Forwarded-Proto` with the original request scheme; its standard
proxy configuration normally does this. Recreate the container after changing
the values.

Only enable `BOOKLIFE_TRUST_PROXY_HEADERS` for a proxy you control. Do not expose
the container port directly to an untrusted network, because a direct client
could forge forwarded headers. Keeping secure cookies and forced redirection
off is necessary while the same login must work over direct HTTP, but it is a
deliberate reduction in transport protection. When local HTTP is no longer
needed, enable both settings and use HTTPS exclusively.

### ISBN lookup and mobile scanning

The **ISBN fetch** section appears above Identity when adding or editing a book.
Enter an ISBN manually and select **Fetch details**, or select **Scan barcode**
on a supported mobile browser. Booklife accepts valid ISBN-10 values and
ISBN-13 book barcodes beginning with `978` or `979`; unrelated product barcodes
are ignored. The digits printed beside a book barcode represent the same value,
so separate OCR is not needed.

Manual lookup works over HTTP but requires the Booklife container to have
outbound Internet access. Booklife checks
[Open Library](https://openlibrary.org/developers/api) first and uses the
[National Library of Poland](https://data.bn.org.pl/docs) as a fallback for
editions missing from that catalogue. It sends only the entered ISBN and the
server's network address; account names, library contents, and notes are not
sent. Returned values remain suggestions: review the title, author, and cover
before saving the book. A missing cover does not prevent title and author from
being used.

Live camera access requires HTTPS or `localhost`. Booklife uses the browser's
native EAN-13 detector when available and automatically falls back to a locally
stored ZXing scanner in browsers such as mobile Edge that do not provide that
API. No camera image is uploaded to Booklife or a third party. On plain-HTTP LAN
access, Booklife explains the browser security limitation and keeps the manual
field available. Camera permission is requested only after selecting **Scan
barcode**, and the camera stops after recognition or cancellation.

The `./data` bind mount is writable even though the rest of the container
filesystem is read-only. Do not add `--volumes` to Docker Compose maintenance
commands; the application data should remain untouched.

### Update Booklife

Application updates can include a matching database migration. Create a verified
database backup, rebuild the image, apply migrations, and only then recreate the
running container:

```bash
docker compose run --rm web python manage.py backup_booklife --output-dir /app/data/backups
docker compose build web
docker compose run --rm web python manage.py migrate
docker compose up -d --force-recreate
```

The container checks for pending migrations before starting. If a migration was
missed, its logs show the exact command to run instead of allowing library pages
to fail later. Never use `--volumes` during an update.

### Keep the secret key private

Generate the key only once for an installation. Keep the completed `.env` file
private and never commit, publish, or copy its value into documentation.
Replacing the key later does not remove books from SQLite, but it signs out
existing sessions and invalidates values protected by the previous application
signature.

Set `BOOKLIFE_UID` and `BOOKLIFE_GID` in `.env` to the owner of the local
`data/` directory if that user is not `1000:1000`. Set these values before
building because the image creates its non-root user with the same identifiers.
The build verifies that this user can read `manage.py` and import Booklife. The
container remains non-root, uses a read-only root filesystem, and writes
persistent data only to `./data`. Network binding stays configurable through
`.env` and defaults to `127.0.0.1`.

The example disables HTTPS redirection for local access. Before exposing the
application through a private HTTPS reverse proxy, set the allowed host and
trusted origin, enable `BOOKLIFE_SECURE_SSL_REDIRECT`, and keep the database on
a local filesystem rather than an NFS or synchronised folder. Run exactly one
application container against a database file.

## Developer setup without Docker

Running directly from source is an optional development workflow. It requires
Python 3.13 or newer with SQLite 3.31 or newer; SQLite 3.51.3 or newer is
recommended.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --requirement requirements.lock
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8000
```

Debug mode uses a clearly marked development-only key. A real key supplied
through `BOOKLIFE_SECRET_KEY` remains mandatory when debug mode is disabled
outside the container workflow.

## Database care

Check the database:

```bash
docker compose run --rm web python manage.py check_database
docker compose run --rm web python manage.py check_database --full
```

Create a consistent backup while the application is running:

```bash
docker compose run --rm web python manage.py backup_booklife --output-dir /app/data/backups
```

The backup appears in `data/backups/`. The command uses SQLite's online backup
mechanism, verifies the resulting file, and restricts its file permissions.
It covers the database, but not `data/covers` or `data/attachments`. For a full
installation backup, stop Booklife and copy the complete `data` directory to
encrypted storage; restart only after the copy finishes. Do not make a generic
copy of an active database file, and do not separate its `-wal` or `-shm` files
after an unclean stop. Recovery details are in
[data/README.md](data/README.md).

## Quality checks for developers

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
python manage.py collectstatic --noinput
```

The project checks the available SQLite version at startup. A runtime below the
supported minimum fails clearly; an older-than-recommended runtime produces a
warning so it can be upgraded deliberately.

## Release policy

All current work remains in release **0.1.0**. User-visible changes are recorded
in [CHANGELOG.md](CHANGELOG.md) under Bug fixes, Improvements, and New features.
Interface icons and the barcode-scanning component are stored locally; their
licenses are recorded in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## GitHub workflow

The repository uses two long-lived branches:

- `dev` — integration work;
- `main` — stable, releasable work.

GitHub Actions runs the Django checks, migrations check, test suite, and
static-file build for pushes and pull requests targeting either branch. It does
not build a Docker image at that stage. Publishing a GitHub Release targeted at
`main` or `dev` runs the separate Docker release build for that exact release
tag and publishes it to GitHub Container Registry (GHCR). It never deploys the
image automatically.

For a release build, create the tag and GitHub Release from the intended branch,
then select that same branch as the release target. The workflow rejects any
target other than `main` or `dev` so the two channels cannot be mixed.
