from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError

from .storage import COVER_MAX_BYTES, prepare_cover


OPEN_LIBRARY_BOOKS_URL = "https://openlibrary.org/api/books"
OPEN_LIBRARY_COVER_URL = "https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg?default=false"
NATIONAL_LIBRARY_BOOKS_URL = "https://data.bn.org.pl/api/networks/bibs.json"
METADATA_MAX_BYTES = 256 * 1024
NATIONAL_LIBRARY_MAX_BYTES = 512 * 1024
LOOKUP_TIMEOUT_SECONDS = 6
USER_AGENT = "Booklife/0.1.0 (private ISBN lookup)"
logger = logging.getLogger(__name__)


class InvalidISBN(ValueError):
    pass


class ISBNNotFound(LookupError):
    pass


class ISBNLookupUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class ISBNMetadata:
    isbn: str
    title: str
    author: str
    cover_data_url: str
    source: str


def normalise_isbn(value: str) -> str:
    cleaned = re.sub(r"[^0-9Xx]", "", value or "").upper()
    if len(cleaned) == 10 and _valid_isbn10(cleaned):
        return cleaned
    if len(cleaned) == 13 and cleaned.startswith(("978", "979")) and _valid_isbn13(cleaned):
        return cleaned
    raise InvalidISBN("Enter a valid ISBN-10 or ISBN-13 beginning with 978 or 979.")


def _valid_isbn10(value: str) -> bool:
    if not re.fullmatch(r"[0-9]{9}[0-9X]", value):
        return False
    digits = [10 if character == "X" else int(character) for character in value]
    return sum((10 - index) * digit for index, digit in enumerate(digits)) % 11 == 0


def _valid_isbn13(value: str) -> bool:
    if not value.isdigit():
        return False
    return sum(int(character) * (1 if index % 2 == 0 else 3) for index, character in enumerate(value)) % 10 == 0


def _read_response(
    url: str,
    *,
    accept: str,
    limit: int,
    provider: str,
    log_failures: bool = True,
) -> tuple[bytes, str]:
    request = Request(url, headers={"Accept": accept, "User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=LOOKUP_TIMEOUT_SECONDS) as response:
            content = response.read(limit + 1)
            content_type = response.headers.get_content_type()
    except HTTPError as exc:
        if log_failures:
            logger.warning("%s ISBN lookup returned HTTP %s.", provider, exc.code)
        raise
    except (OSError, TimeoutError, URLError) as exc:
        if log_failures:
            logger.warning("%s ISBN lookup could not connect: %s.", provider, type(exc).__name__)
        raise ISBNLookupUnavailable("The book service is temporarily unavailable.") from exc
    if len(content) > limit:
        raise ISBNLookupUnavailable("The book service returned an unexpectedly large response.")
    return content, content_type


def _fetch_cover_data_url(isbn: str) -> str:
    try:
        content, content_type = _read_response(
            OPEN_LIBRARY_COVER_URL.format(isbn=isbn),
            accept="image/jpeg,image/png,image/webp",
            limit=COVER_MAX_BYTES,
            provider="Open Library Covers",
            log_failures=False,
        )
    except HTTPError as exc:
        if exc.code == 404:
            return ""
        return ""
    except ISBNLookupUnavailable:
        return ""

    if content_type not in {"image/jpeg", "image/png", "image/webp"}:
        return ""
    try:
        processed = prepare_cover(ContentFile(content, name=f"{isbn}.jpg"))
    except ValidationError:
        return ""
    encoded = base64.b64encode(processed).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _open_library_metadata(isbn: str) -> tuple[str, str]:
    key = f"ISBN:{isbn}"
    query = urlencode({"bibkeys": key, "format": "json", "jscmd": "data"})
    try:
        content, content_type = _read_response(
            f"{OPEN_LIBRARY_BOOKS_URL}?{query}",
            accept="application/json",
            limit=METADATA_MAX_BYTES,
            provider="Open Library",
        )
    except HTTPError as exc:
        raise ISBNLookupUnavailable("The book service is temporarily unavailable.") from exc

    if content_type != "application/json":
        raise ISBNLookupUnavailable("The book service returned an invalid response.")
    try:
        record = json.loads(content).get(key)
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError) as exc:
        raise ISBNLookupUnavailable("The book service returned an invalid response.") from exc
    if not isinstance(record, dict):
        raise ISBNNotFound("No book was found for this ISBN.")

    title = " ".join(str(record.get("title", "")).split())[:255]
    authors = record.get("authors", [])
    author_names = [
        " ".join(str(author.get("name", "")).split())
        for author in authors[:8]
        if isinstance(author, dict) and author.get("name")
    ] if isinstance(authors, list) else []
    author = ", ".join(author_names)[:255]
    if not title:
        raise ISBNNotFound("No usable book title was found for this ISBN.")
    return title, author


def _marc_subfields(record: dict, tag: str, allowed_codes: set[str]) -> list[str]:
    fields = record.get("marc", {}).get("fields", [])
    values = []
    for field in fields if isinstance(fields, list) else []:
        tagged = field.get(tag) if isinstance(field, dict) else None
        if not isinstance(tagged, dict):
            continue
        for subfield in tagged.get("subfields", []):
            if not isinstance(subfield, dict):
                continue
            for code, value in subfield.items():
                if code in allowed_codes and value:
                    values.append(" ".join(str(value).split()).strip(" /,;."))
    return [value for value in values if value]


def _display_author(value: str) -> str:
    if value.count(",") == 1:
        surname, given_names = (part.strip() for part in value.split(",", 1))
        if surname and given_names:
            return f"{given_names} {surname}"
    return value


def _national_library_metadata(isbn: str) -> tuple[str, str]:
    query = urlencode({"isbnIssn": isbn, "limit": 1})
    try:
        content, content_type = _read_response(
            f"{NATIONAL_LIBRARY_BOOKS_URL}?{query}",
            accept="application/json",
            limit=NATIONAL_LIBRARY_MAX_BYTES,
            provider="National Library of Poland",
        )
    except HTTPError as exc:
        raise ISBNLookupUnavailable("The National Library catalogue is temporarily unavailable.") from exc

    if content_type != "application/json":
        raise ISBNLookupUnavailable("The National Library catalogue returned an invalid response.")
    try:
        records = json.loads(content).get("bibs", [])
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError) as exc:
        raise ISBNLookupUnavailable("The National Library catalogue returned an invalid response.") from exc
    if not isinstance(records, list):
        raise ISBNLookupUnavailable("The National Library catalogue returned an invalid response.")

    record = next(
        (
            item
            for item in records
            if isinstance(item, dict)
            and isbn in re.sub(r"[^0-9X]", "", str(item.get("isbnIssn", "")).upper())
        ),
        None,
    )
    if record is None:
        raise ISBNNotFound("No book was found for this ISBN.")

    title_parts = _marc_subfields(record, "245", {"a", "b", "n", "p"})
    title = " ".join(title_parts)[:255]
    authors = _marc_subfields(record, "100", {"a"})
    if not title:
        title = " ".join(str(record.get("title", "")).split())[:255]
    if not authors:
        authors = [" ".join(str(record.get("author", "")).split())]
    author = ", ".join(_display_author(value) for value in authors if value)[:255]
    if not title:
        raise ISBNNotFound("No usable book title was found for this ISBN.")
    return title, author


def fetch_isbn_metadata(value: str) -> ISBNMetadata:
    isbn = normalise_isbn(value)
    open_library_error = None
    try:
        title, author = _open_library_metadata(isbn)
        source = "Open Library"
    except (ISBNNotFound, ISBNLookupUnavailable) as exc:
        open_library_error = exc
        try:
            title, author = _national_library_metadata(isbn)
            source = "National Library of Poland"
        except ISBNNotFound:
            if isinstance(open_library_error, ISBNNotFound):
                raise ISBNNotFound("No book was found for this ISBN in the available catalogues.") from None
            raise ISBNLookupUnavailable("The book catalogues could not complete this lookup. Try again later.") from None
        except ISBNLookupUnavailable:
            raise ISBNLookupUnavailable("The book catalogues could not complete this lookup. Try again later.") from None

    return ISBNMetadata(
        isbn=isbn,
        title=title,
        author=author,
        cover_data_url=_fetch_cover_data_url(isbn),
        source=source,
    )
