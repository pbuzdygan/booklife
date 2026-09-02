# Changelog

This file records user-visible changes to Booklife. Every change remains part of
version 0.1.0 until the first release is deliberately closed.

## 0.1.0 — in development

### Bug fixes

- Made camera ISBN scanning work in mobile browsers such as Edge that do not
  provide their own barcode detector; Booklife now switches automatically to a
  scanner stored inside the application.
- Added the National Library of Poland as a fallback when Open Library does not
  contain a local edition, so a valid ISBN can still fill its title and author;
  a missing cover no longer prevents the useful metadata from being returned.
- Made ISBN service logs distinguish a missing catalogue record from a provider
  connection or HTTP failure, replacing an unexplained generic lookup error.
- Fixed valid PNG, JPEG, WebP, and PDF attachments being rejected when a browser
  or mobile gallery did not preserve a useful filename; Booklife now recognises
  the actual file contents and stores them with a safe extension.
- Fixed the production static-file manifest used by the login page, preventing a
  fresh container from returning a server error immediately after setup.
- Made future page errors visible in container logs so they can be diagnosed
  from their actual cause instead of a generic error page.
- Prevented an outdated database schema from producing unexplained page errors;
  the container now stops with a clear migration instruction before serving the
  application.
- Removed an ineffective browser isolation header from plain HTTP responses, so
  browsers no longer report that ignored HTTPS-only protection in the console.
- Removed the custom container entrypoint that could become unreadable under
  restrictive host permissions; the application now starts directly and more
  reliably.
- Matched the image user to the configured host UID and verified application
  files during every image build, preventing unreadable management commands and
  failed application imports.
- Fixed local-network access by making the listening address configurable and
  allowing sessions to work correctly when a trusted installation intentionally
  uses plain HTTP.
- Corrected the initial product direction so the application and its documents
  consistently use English and no longer propose an unnecessarily heavy
  database service.
- Prevented an older edit page from silently overwriting newer changes made in
  another session.
- Closed the filter panel after applying filters and when clicking elsewhere, so
  it no longer remains in the way of the refreshed library.
- Made malformed or outdated filter links fall back safely instead of breaking
  the library view.
- Ensured that books, notes, history, categories, and exports from one account
  cannot appear in another account's private library.
- Made Django Admin identify every book and category by its owning user and
  filter records by that user, removing ambiguous duplicate “My library” values.
- Made success and information notifications dismiss themselves after five
  seconds while retaining the explicit close control.
- Kept mobile navigation complete and comfortable by adding Loaned and sign-out
  controls, increasing header edge spacing, and removing the unused row-density
  toggle.
- Scoped failed sign-in throttling to the submitted account as well as the
  client address, so a blocked account no longer blocks other users on the same
  network.
- Made signed-in sessions expire on application restart instead of surviving in
  the persistent library database.

### Improvements

- Documented how one installation can use trusted local HTTP and HTTPS through
  Nginx Proxy Manager, including the safer default for new installations.
- Documented the exact difference between regular users and superusers, making
  it clear which account is safest for everyday library use and which account
  can administer the entire installation.
- Adopted **A — Clear Utility** as the Booklife interface standard: compact
  tables, restrained colour, clear focus states, and responsive mobile views.
- Simplified operation to one application and one SQLite database stored in the
  `data` folder, with no separate database service.
- Kept spreadsheet import out of this stage so Booklife can focus on a reliable
  everyday library experience.
- Added a recovery guide, database health checks, and verified backups that can
  be created while Booklife is running.
- Hardened private use with protected sessions, safer password hashing, sign-in
  throttling, request protection, and a container that runs without root access.
- Added visible completion markers to the plan so delivered and remaining work
  can be understood at a glance.
- Removed Python from the end-user setup and replaced application-key creation
  with one standard OpenSSL command.
- Kept the project and container package free of generated test caches, build
  output, and temporary logs so installations remain clean and predictable.
- Clarified first-time sign-in directly on the login page, including how to
  create the first account and which credentials should be entered.
- Replaced mixed interface symbols with a consistent set of locally stored
  Tabler icons, without contacting an external service while Booklife is used.
- Grouped category management, Trash, and JSON export under one Settings area,
  making the main navigation quieter and maintenance tools easier to find.
- Kept the familiar generated cover visible whenever an optional cover image is
  missing, so incomplete file backups do not break the library layout.
- Added the Booklife mark as a maintained branding set, including favicon,
  Apple Touch Icon, and installed-PWA PNG variants.
- Prepared the repository for GitHub with focused ignore rules, formatting
  metadata, branch-aware quality checks, and release-only Docker builds.

### New features

- Added ISBN fetch above Identity: readers can enter an ISBN or scan a supported
  mobile EAN-13 book barcode, then review the fetched title, author, and cover
  before saving. Unrelated product barcodes and invalid checksums are ignored.
- Added private sign-in and a separate library for every account created by an
  administrator; public registration is not available.
- Added persistent book records with title, author, reading status, location,
  shelf detail, rating, page count, finish date, notes, and multiple categories.
- Added the complete Clear Utility library interface with compact table and
  cover layouts for desktop and mobile.
- Added search, column sorting, filters, and one-click views for all books, the
  reading queue, wishlist, read books, loaned books, journal, and trash.
- Added quick acquisition from the wishlist so an owned book moves to the shelf
  and reading queue in one action.
- Added book history that records important moments such as discovery,
  acquisition, queueing, reading, lending, returning, and restoration.
- Added recoverable trash, deliberate permanent deletion, and a portable JSON
  export of a private library.
- Added a single-container setup that keeps the live database in `./data` and
  exposes Booklife only on the local machine by default.
- Added an optional local-network mode so Booklife can be opened from another
  device on the same trusted network.
- Added automatic first-run setup for an empty `data` folder: Booklife creates
  its database and a temporary regular account, then prints the credentials and
  immediate password-change command prominently in the logs.
- Added category management that can create reusable categories or remove them
  without deleting books that used them.
- Added optional book covers that can be selected from a device or photographed
  on mobile, then automatically cropped and reduced for list and grid views.
- Added protected book attachments with clear file limits and private downloads;
  their contents remain outside SQLite in `data/attachments`.
- Added an installable PWA that caches application assets only and never stores
  authenticated library pages offline.
