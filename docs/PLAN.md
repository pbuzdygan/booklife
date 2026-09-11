# Booklife — product and delivery plan

**Tagline:** Every book has a life beyond its pages.  
**Document version:** 0.4  
**Application release:** 0.1.0 (in development)  
**Updated:** 1 September 2026  
**First-release goal:** replace the current Microsoft Lists workflow for book tracking with a fast,
private, lightweight web application while preserving compact tables, useful
views, filtering, and quick editing.

## How progress is shown

- `[ ]` means planned.
- `[~]` means in progress.
- `[x]` with strikethrough means delivered and verified at the current stage.

This convention will be used throughout this file. A completed item stays in the
plan so progress remains visible without checking commit history.

## 1. Product direction

Booklife is a personal tool, not a social reading network. It keeps one clear
record of books that have been discovered, acquired, queued, read, loaned, or
given away.

Product principles:

1. **Information first.** A screen should show useful data without visual noise.
2. **Fast capture.** A title can be saved with only the minimum information and
   completed later.
3. **Saved views over dashboards.** Everyday questions such as “What should I
   read next?” should be one click away.
4. **Current state plus history.** The list stays simple while important changes
   can form a lightweight lifecycle.
5. **Private by default.** The library, notes, and future attachments are never
   public unless a future feature explicitly changes that.
6. **Lightweight operation.** One application process, one SQLite file, and a
   simple container workflow are enough for the expected scale.

## 2. What the reference files taught us

The Microsoft Lists export is a design and domain reference only. It will not be
imported by the first versions of Booklife.

It demonstrates these useful concepts:

- title and author;
- reading status: Interested, Queued, and Read;
- personal rating from 1 to 10;
- multiple categories;
- physical or ownership state: Shelf, To buy, Loaned, and Given away;
- page count, reading year, notes, and optional attachments;
- compact saved views grouped or filtered by location, rating, year, and status;
- colour as a scanning aid for states and categories.

The export currently represents 59 books and confirms that a compact list is the
main working surface. Its technical SharePoint metadata is intentionally out of
scope. Data import, cleanup, and migration will be considered much later, after
the core application proves useful.

## 3. MVP scope

### Required for the first usable release

- [x] ~~Private sign-in for an administratively created owner, with no public registration.~~
- [x] ~~Compact desktop table and a responsive mobile list.~~
- [x] ~~Add, view, edit, move to trash, restore, and permanently delete a book.~~
- [x] ~~Search by title, author, and notes.~~
- [x] ~~Filter by status, ownership/location, category, rating, and year.~~
- [x] ~~Sort the main columns.~~
- [x] ~~Saved views for All books, Reading queue, Wishlist, Read, Loaned, and Journal.~~
- [x] ~~Multiple categories per book.~~
- [x] ~~A Settings area for adding and removing reusable categories.~~
- [x] ~~Rating from 1–10, page count, finish date/year, and plain-text notes.~~
- [x] ~~Optional processed book covers with a resilient placeholder when a file is unavailable.~~
- [x] ~~Protected, size-limited attachments stored outside SQLite.~~
- [x] ~~ISBN lookup for title, author, and processed cover, with validated ISBN-10/ISBN-13 input and optional mobile EAN-13 camera scanning.~~
- [x] ~~Automatic lifecycle entries for meaningful status changes.~~
- [x] ~~Export a personal library copy in portable JSON.~~
- [x] ~~Keyboard-accessible and mobile-friendly primary flows.~~
- [x] ~~Installable PWA with a private offline boundary: application assets are cached, while authenticated library pages are never stored offline.~~

### Explicitly outside the MVP

- Spreadsheet import or migration from Microsoft Lists.
- Public profiles, social features, and other readers’ reviews.
- AI recommendations or automatic note summaries.
- Advanced statistics and reading goals.
- Separate native iOS or Android applications distributed through App Store or
  Google Play (this does not exclude the installed web PWA).
- OCR, an e-book reader, and bookstore integrations.

### Later, small additions

1. **Loans:** person or alias, loan date, expected return, reminder, and quick
   return action.
2. **Statistics:** books and pages per year, rating distribution, and categories.
3. **Optional migration:** a separate, reviewed tool if the old data still needs
   to be moved at that point.

## 4. Primary user flows

### Add a book to the wishlist

1. Select **Add book**.
2. Enter a title and optionally an author.
3. Keep the defaults: status **Interested**, location **To buy**.
4. Save and see the book immediately in **Wishlist**.

### Acquire and queue a book

1. Open a wishlist book and choose **I own it**.
2. Location changes to **Shelf** and status changes to **Queued**.
3. Booklife records the acquisition without losing the earlier discovery state.

### Finish a book

1. Edit the book and change its reading status to **Read**.
2. Add a rating, finish date, and an optional note.
3. The book appears in **Journal** and receives a completion event.

### Loan a book (detailed flow planned for Phase 3)

Version 0.1.0 can set a book's location to **Loaned** and show it in the Loaned
view. Phase 3 will add the safer structured flow:

1. Choose **Loan book**, then provide a person alias and optional due date.
2. Location changes to **Loaned** while reading status remains unchanged.
3. Returning it closes the loan and restores location to **Shelf**.

## 5. Information model

The familiar interface labels stay simple, but the model separates reading state
from ownership state. A book can therefore be both **Read** and **Loaned**.

```text
User
 └─ Library
     └─ Book ──< BookCategory >── Category
         ├─< LifecycleEvent
         ├─< Attachment
         └─< Loan (later)
```

### Book

| Field | Rule |
|---|---|
| `id` | UUID generated by the application |
| `library_id` | ownership boundary applied to every query |
| `title` | required, 1–255 characters |
| `author` | free-text author credit; optional during quick capture |
| `reading_status` | `interested`, `queued`, `reading`, `read`, `abandoned` |
| `ownership_status` | `wanted`, `owned`, `loaned`, `given_away`, `unknown` |
| `shelf_location` | optional detail such as “Living room · shelf 2” |
| `rating` | integer from 1–10, available after reading or abandoning |
| `page_count` | positive integer with a practical upper limit |
| `finished_on` | optional full date; year-based views are derived from it |
| `notes` | plain text with an application-level size limit |
| `version` | optimistic-lock counter to prevent accidental overwrites |
| timestamps | created, updated, and soft-deleted timestamps |

### LifecycleEvent

An event stores a type, time, optional short note, and the actor. The application
creates events automatically after meaningful actions; the user does not need to
maintain a timeline manually.

### Loan and Attachment

`Loan` stores the person alias, loan date, expected return, and actual return.
`Attachment` stores display metadata and a generated storage name rather than
trusting the uploaded filename. File contents remain under `data/attachments`
and are available only through an owner-authorised download.

## 6. UX and visual directions

### Navigation

- **All books** — the complete compact table;
- **Reading queue** — Queued and, later, Reading;
- **Wishlist** — Interested and To buy;
- **Read** — completed books with rating and year;
- **Loaned** — active loans;
- **Journal** — completed books grouped by reading year.

### Shared interaction standards

- desktop table with a sticky header and a permanently compact row height;
- compact cards on smaller screens;
- dedicated, uncluttered detail and editing pages;
- search and saved views visible without opening a settings screen;
- colour always paired with text, never used as the only status indicator;
- Tabler Icons is the single interface icon system; icons are stored locally,
  labelled through their surrounding controls, and never loaded from a CDN;
- clear focus states, keyboard operation, readable contrast, and restrained motion;
- no decorative animation, oversized dashboard cards, or unnecessary gradients.

### Selected visual standard

The design exploration compared three directions and selected **A — Clear
Utility**. The temporary prototype was removed once that decision had been
implemented in the persistent application, keeping the repository focused on
one maintained interface.

**A — Clear Utility:** cool neutral canvas, crisp dividers, compact controls,
and a familiar productivity-tool rhythm without copying Microsoft Lists.

## 7. Architecture

The technical design, storage rules, container operation, and GitHub delivery
automation are documented in [ARCHITECTURE.md](ARCHITECTURE.md).

## 8. Security and privacy

### Identity and sessions

- no public registration; a fresh installation receives one temporary regular
  account, while additional accounts are created administratively;
- regular accounts manage only their own books, categories, covers, attachments,
  trash, and exports in the Booklife interface;
- superusers retain a separate private library for normal use but can also open
  `/admin/`, manage accounts and permissions, and administer every library;
- the temporary `booklife` account is deliberately not a superuser, and routine
  library work should use a regular account to limit the impact of mistakes;
- Argon2id password hashing; MFA and passkeys remain future work;
- `Secure`, `HttpOnly`, and appropriate `SameSite` session cookies;
- session rotation after sign-in; sessions end when the browser closes, never
  exceed 12 hours, and are invalidated when the application restarts;
- login rate limiting without revealing whether an account exists;
- CSRF protection for every state-changing operation;
- ownership checks on every book, loan, event, and future file request.

### Data and application

- server-side validation, ORM queries, and output escaping;
- notes stay plain text until there is a strong reason for rich text;
- Content Security Policy, HSTS, MIME protections, frame restrictions, and a
  strict referrer policy;
- a private application key generated once with OpenSSL, supplied at runtime
  through `.env`, and never committed or embedded in an image;
- logs exclude notes, passwords, session values, and file contents;
- ISBN lookup sends only the requested ISBN to fixed Open Library and National
  Library of Poland HTTPS endpoints, uses strict response limits and timeouts,
  and never sends library or account data;
- soft deletion, a clear trash flow, and confirmation for irreversible actions;
- locked dependencies, automated vulnerability checks, and regular patching;
- request, field, cover, and attachment size limits.

### SQLite-specific protection

- `data/booklife.sqlite3`, `-wal`, `-shm`, covers, attachments, and backups are
  excluded from version control and container images;
- the database directory is readable and writable only by the application user;
- backups are encrypted before leaving the host;
- no endpoint can serve paths from `data/` directly;
- a single writer instance avoids unsupported distributed locking assumptions;
- migrations always run after a verified backup and include a rollback plan.

### Covers and attachments

- covers accept JPEG, PNG, or WebP input up to 10 MB, remove metadata, crop to a
  consistent book ratio, and are saved as compact JPEG files;
- attachments use a narrow PDF, UTF-8 TXT, JPEG, PNG, and WebP allowlist, with
  signature validation, a 10 MB per-file limit, and ten files per book;
- generated storage names prevent uploaded names from becoming filesystem paths;
- files stay outside the static web root and every read or delete checks the
  owning library;
- downloads use attachment disposition and MIME-sniffing protection;
- missing files are omitted from the interface without breaking the book record.

## 9. Delivery plan

### Phase 0 — product direction

- [x] ~~Review the reference description and Lists structure.~~
- [x] ~~Define the product scope, states, and primary flows.~~
- [x] ~~Evaluate desktop and mobile flows in an early interactive prototype.~~
- [x] ~~Compare three visual directions and select one.~~
- [x] ~~Choose SQLite and define the `data/` storage convention.~~
- [x] ~~Select A — Clear Utility as the preferred visual direction.~~
- [x] ~~Allow several administratively created accounts with isolated private
  libraries while keeping public registration disabled.~~

**Exit condition:** the selected direction is understandable without explanation,
and reading status versus ownership state is clear.

### Phase 1 — foundation and vertical slice

- [x] ~~Create the Django application and module boundaries.~~
- [x] ~~Add the SQLite configuration, version check, WAL settings, and `data/` volume.~~
- [x] ~~Add private sign-in and the library ownership boundary.~~
- [x] ~~Implement the first end-to-end slice: list, search, add, and edit one book.~~
- [x] ~~Add model tests and authorisation integration tests.~~
- [x] ~~Add a backup command and prove restoration in an isolated environment.~~
- [x] ~~Refuse to start against pending database migrations and provide the exact
  recovery command in container logs.~~
- [x] ~~Bootstrap a missing database and clearly announce the temporary first-run
  credentials and password-change command.~~

**Exit condition:** a user can sign in and safely save a book from desktop and
mobile, and the database can be restored from a tested backup.

### Phase 2 — complete MVP

- [x] ~~Add filters, sorting, saved views, journal, and trash.~~
- [x] ~~Add categories, rating, finish date/year, notes, and lifecycle events.~~
- [x] ~~Add Settings-based category management and move Trash and Export into it.~~
- [x] ~~Add processed covers and protected attachments outside the SQLite file.~~
- [x] ~~Add reviewed ISBN lookup and mobile book-barcode scanning with a local
  compatibility fallback, without storing unnecessary external metadata.~~
- [x] ~~Add portable, owner-scoped JSON export.~~
- [x] ~~Add an installable PWA without storing private library pages offline.~~
- [x] ~~Complete model, authorisation, web-flow, security-header, database
  integrity, and backup/restore checks.~~
- [x] ~~Add GitHub Actions quality checks for `main` and `dev`, plus Docker
  builds only for releases in each channel.~~
- [~] Complete a browser-driven accessibility and container build audit on a
  machine with Docker and supported browser tooling.

**Exit condition:** all primary flows work against persistent SQLite storage, the
selected visual direction is consistent, and recovery is documented and tested.

### Phase 3 — loans and operations

- [ ] Add a documented HTTPS deployment path before Booklife is used for sign-in
  outside a trusted local development environment.
- [ ] Add the loan model, return flow, and reminders.
- [ ] Add storage monitoring and data deletion procedures.

## 10. Test strategy and quality gates

- [x] ~~**Model:** state validation, rating range, categories, lifecycle events,
  and trash.~~
- [x] ~~**Authorisation:** another library's UUID never grants read or write
  access, including through export.~~
- [x] ~~**SQLite core:** startup version gate, WAL safety settings, migrations,
  quick/full integrity checks, online backup, and isolated recovery.~~
- [ ] **SQLite resilience:** measured write contention and unclean-restart tests.
- [x] ~~**Web:** long and accented text, search, saved views, invalid filters,
  sorting links, primary forms, and version-conflict protection.~~
- [x] ~~**Security:** sign-in throttling, owner isolation, CSRF-protected actions,
  private response caching, browser protection headers, and owner-authorised
  cover and attachment access.~~
- [~] **End-to-end:** core flows have Django integration coverage; add
  browser-driven wishlist → acquire → queue → read coverage when browser tooling
  is available. The detailed loan → return flow belongs to Phase 3.
- [~] **Accessibility:** semantic labels, keyboard flow, visible focus, responsive
  layout, and reduced motion are implemented; complete a browser and screen-reader
  audit at 200% zoom.
- [~] **Operations:** healthcheck, migrations, backup, restore, static serving,
  and GitHub Actions build configuration are ready; run the first remote workflow
  and a final local restart test with Docker.

## 11. Decisions and open questions

1. [x] ~~Use A — Clear Utility as Booklife's visual foundation.~~
2. [x] ~~Support several isolated private libraries without public registration.~~
3. [x] ~~Capture a full optional finish date and derive the reading year from it.~~
4. [ ] When detailed loans arrive, should Booklife store only a person alias or
   fuller contact details? The safer default is an alias.
5. [ ] Where will the first persistent version run: one laptop, a home server/NAS, or
   a private hosted machine? SQLite must use a local, reliable filesystem even if
   the application is accessed remotely.

## Sources for technical decisions

- [Django 5.2 LTS release notes](https://docs.djangoproject.com/en/5.2/releases/5.2/)
- [Django database notes — SQLite 3.31+](https://docs.djangoproject.com/en/5.2/ref/databases/#sqlite-notes)
- [SQLite release history — 3.53.4](https://sqlite.org/changes.html)
- [SQLite guidance on safe backup and corruption risks](https://www.sqlite.org/howtocorrupt.html)
- [OWASP authentication guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP file upload guidance](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
