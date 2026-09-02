from __future__ import annotations

import copy
import hashlib
import json
import uuid
from itertools import groupby

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.cache import cache
from django.db import connection, transaction
from django.db.models import Count, Q
from django.db.models.functions import Lower
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .forms import BookForm, CategoryForm
from .isbn import ISBNLookupUnavailable, ISBNNotFound, InvalidISBN, fetch_isbn_metadata, normalise_isbn
from .models import Attachment, Book, Category, LifecycleEvent
from .services import add_event, get_or_create_library, record_initial_events, record_status_event
from .storage import (
    attachment_path,
    available_attachments,
    cover_path,
    delete_attachment_file,
    delete_cover,
    save_attachment,
    save_cover,
)


VIEW_DEFINITIONS = {
    "all": ("Your library", "All books", "One clear view of every book in your collection."),
    "queue": ("Choose what comes next", "Reading queue", "Books already waiting on your shelf."),
    "wishlist": ("Ideas worth keeping", "Wishlist", "Books you may want to buy or read later."),
    "read": ("What stayed with you", "Read", "Ratings, notes, and books you have already finished."),
    "loaned": ("Away from the shelf", "Loaned", "Books that should eventually find their way home."),
    "journal": ("Your reading trail", "Reading journal", "Finished books grouped by reading year."),
    "trash": ("Recover or remove", "Trash", "Deleted books remain recoverable until you remove them permanently."),
}

SORT_FIELDS = {
    "title": Lower("title"),
    "author": Lower("author"),
    "status": "reading_status",
    "rating": "rating",
    "location": "ownership_status",
    "pages": "page_count",
    "finished": "finished_on",
    "updated": "updated_at",
}


def _login_rate_key(request, username: str) -> str:
    """Keep failed-login limits separate for each account on a shared network."""

    address = request.META.get("REMOTE_ADDR", "unknown")
    identity = username.strip().casefold()[:150]
    digest = hashlib.sha256(f"{address}:{identity}".encode("utf-8")).hexdigest()
    return f"booklife:login:{digest}"


def _isbn_rate_key(request) -> str:
    return f"booklife:isbn:{request.user.pk}"


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect("library")

    username = request.POST.get("username", "") if request.method == "POST" else ""
    key = _login_rate_key(request, username)
    attempts = int(cache.get(key, 0))
    throttled = request.method == "POST" and attempts >= 5
    form = AuthenticationForm(request, data=request.POST or None)

    if throttled:
        form.add_error(None, "Too many sign-in attempts. Try again in five minutes.")
        return render(request, "registration/login.html", {"form": form}, status=429)

    if request.method == "POST" and form.is_valid():
        cache.delete(key)
        login(request, form.get_user())
        get_or_create_library(form.get_user())
        next_url = request.POST.get("next", "")
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("library")

    if request.method == "POST":
        cache.set(key, attempts + 1, timeout=300)
    return render(request, "registration/login.html", {"form": form})


@login_required
@require_GET
def isbn_lookup(request):
    key = _isbn_rate_key(request)
    attempts = int(cache.get(key, 0))
    if attempts >= 12:
        return JsonResponse(
            {"error": "Too many ISBN lookups. Wait a minute and try again."},
            status=429,
        )
    cache.set(key, attempts + 1, timeout=60)

    try:
        isbn = normalise_isbn(request.GET.get("isbn", ""))
    except InvalidISBN as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    metadata = cache.get(f"booklife:isbn-result:{isbn}")
    if metadata is None and not cache.add("booklife:isbn-external-lookup", True, timeout=1):
        return JsonResponse(
            {"error": "Another ISBN lookup is in progress. Wait a moment and try again."},
            status=429,
        )
    try:
        if metadata is None:
            metadata = fetch_isbn_metadata(isbn)
            cache.set(f"booklife:isbn-result:{isbn}", metadata, timeout=6 * 60 * 60)
    except ISBNNotFound as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    except ISBNLookupUnavailable as exc:
        return JsonResponse({"error": str(exc)}, status=502)

    return JsonResponse(
        {
            "isbn": metadata.isbn,
            "title": metadata.title,
            "author": metadata.author,
            "cover_data_url": metadata.cover_data_url,
            "source": metadata.source,
        }
    )


@require_POST
def logout_view(request):
    logout(request)
    return redirect("login")


@require_GET
def healthz(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return JsonResponse({"status": "ok"})


@require_GET
def service_worker(request):
    """Serve the worker at the site root so it can cover the whole application."""

    response = render(request, "catalog/service-worker.js", content_type="application/javascript")
    response["Cache-Control"] = "no-cache"
    response["Service-Worker-Allowed"] = "/"
    return response


def _owned_book_or_404(user, book_id, *, trashed=None):
    queryset = Book.objects.select_related("library").prefetch_related("categories", "events", "attachments")
    queryset = queryset.filter(library__owner=user)
    if trashed is True:
        queryset = queryset.trashed()
    elif trashed is False:
        queryset = queryset.active()
    return get_object_or_404(queryset, id=book_id)


@login_required
@require_GET
def library_view(request):
    library = get_or_create_library(request.user)
    current_view = request.GET.get("view", "all")
    if current_view not in VIEW_DEFINITIONS:
        current_view = "all"

    books = Book.objects.filter(library=library).prefetch_related("categories")
    books = books.trashed() if current_view == "trash" else books.active()

    if current_view == "queue":
        books = books.filter(reading_status__in=(Book.ReadingStatus.QUEUED, Book.ReadingStatus.READING))
    elif current_view == "wishlist":
        books = books.filter(
            Q(reading_status=Book.ReadingStatus.INTERESTED)
            | Q(ownership_status=Book.OwnershipStatus.WANTED)
        )
    elif current_view in {"read", "journal"}:
        books = books.filter(reading_status=Book.ReadingStatus.READ)
    elif current_view == "loaned":
        books = books.filter(ownership_status=Book.OwnershipStatus.LOANED)

    query = request.GET.get("q", "").strip()[:200]
    if query:
        books = books.filter(
            Q(title__icontains=query)
            | Q(author__icontains=query)
            | Q(notes__icontains=query)
        )

    reading_status = request.GET.get("status", "")
    valid_reading = {choice for choice, _ in Book.ReadingStatus.choices}
    if reading_status in valid_reading:
        books = books.filter(reading_status=reading_status)
    else:
        reading_status = ""

    ownership_status = request.GET.get("location", "")
    valid_ownership = {choice for choice, _ in Book.OwnershipStatus.choices}
    if ownership_status in valid_ownership:
        books = books.filter(ownership_status=ownership_status)
    else:
        ownership_status = ""

    category_id = request.GET.get("category", "")
    if category_id:
        try:
            category_uuid = uuid.UUID(category_id)
        except ValueError:
            category_id = ""
        else:
            books = books.filter(categories__id=category_uuid, categories__library=library)

    rating_min = request.GET.get("rating", "")
    if rating_min.isdigit() and 1 <= int(rating_min) <= 10:
        books = books.filter(rating__gte=int(rating_min))
    else:
        rating_min = ""

    year = request.GET.get("year", "")
    if year.isdigit() and 1000 <= int(year) <= 2100:
        books = books.filter(finished_on__year=int(year))
    else:
        year = ""

    sort_key = request.GET.get("sort", "title")
    if sort_key not in SORT_FIELDS:
        sort_key = "title"
    sort_direction = request.GET.get("direction", "asc")
    if sort_direction not in {"asc", "desc"}:
        sort_direction = "asc"
    expression = SORT_FIELDS[sort_key]
    if isinstance(expression, str):
        expression = f"-{expression}" if sort_direction == "desc" else expression
    elif sort_direction == "desc":
        expression = expression.desc()
    books = books.order_by(expression, Lower("title")).distinct()

    filter_values = {
        "status": reading_status,
        "location": ownership_status,
        "category": category_id,
        "rating": rating_min,
        "year": year,
    }
    active_filter_count = sum(bool(value) for value in filter_values.values())
    all_years = sorted(
        {
            date.year
            for date in Book.objects.active()
            .filter(library=library, finished_on__isnull=False)
            .values_list("finished_on", flat=True)
        },
        reverse=True,
    )

    journal_groups = []
    result_books = list(books)
    journal_summary = None
    if current_view == "journal":
        result_books.sort(key=lambda book: (book.finished_on.year if book.finished_on else 0), reverse=True)
        for group_year, grouped_books in groupby(
            result_books,
            key=lambda book: book.finished_on.year if book.finished_on else "No year",
        ):
            journal_groups.append((group_year, list(grouped_books)))
        rated = [book.rating for book in result_books if book.rating is not None]
        journal_summary = {
            "count": len(result_books),
            "average": round(sum(rated) / len(rated), 1) if rated else None,
            "pages": sum(book.page_count or 0 for book in result_books),
            "years": len({book.finished_on.year for book in result_books if book.finished_on}),
        }

    query_without_sort = request.GET.copy()
    query_without_sort.pop("sort", None)
    query_without_sort.pop("direction", None)

    context = {
        "library": library,
        "books": result_books,
        "journal_groups": journal_groups,
        "journal_summary": journal_summary,
        "current_view": current_view,
        "view_kicker": VIEW_DEFINITIONS[current_view][0],
        "view_title": VIEW_DEFINITIONS[current_view][1],
        "view_description": VIEW_DEFINITIONS[current_view][2],
        "query": query,
        "filter_values": filter_values,
        "active_filter_count": active_filter_count,
        "categories": library.categories.order_by("name"),
        "years": all_years,
        "sort_key": sort_key,
        "sort_direction": sort_direction,
        "query_without_sort": query_without_sort.urlencode(),
        "reading_choices": Book.ReadingStatus.choices,
        "ownership_choices": Book.OwnershipStatus.choices,
    }
    return render(request, "catalog/library.html", context)


@login_required
@require_GET
def book_detail(request, book_id):
    book = _owned_book_or_404(request.user, book_id)
    return render(
        request,
        "catalog/book_detail.html",
        {
            "book": book,
            "available_attachments": available_attachments(book),
            "current_view": "trash" if book.deleted_at else "all",
        },
    )


def _apply_book_files(form: BookForm, book: Book, created_files: list[tuple[str, str]]) -> str:
    old_cover_to_delete = ""
    prepared_cover = form.cleaned_data.get("cover")
    if prepared_cover:
        new_cover = save_cover(prepared_cover)
        created_files.append(("cover", new_cover))
        old_cover_to_delete = book.cover_filename
        book.cover_filename = new_cover
        book.save(update_fields=("cover_filename", "updated_at"))
    elif form.cleaned_data.get("clear_cover") and book.cover_filename:
        old_cover_to_delete = book.cover_filename
        book.cover_filename = ""
        book.save(update_fields=("cover_filename", "updated_at"))

    for prepared in form.cleaned_data.get("attachments", []):
        attachment = save_attachment(book, prepared)
        created_files.append(("attachment", attachment.stored_filename))
    return old_cover_to_delete


def _remove_created_files(files: list[tuple[str, str]]) -> None:
    for file_type, filename in files:
        if file_type == "cover":
            delete_cover(filename)
        else:
            delete_attachment_file(filename)


@login_required
@require_http_methods(["GET", "POST"])
def book_create(request):
    library = get_or_create_library(request.user)
    form = BookForm(request.POST or None, request.FILES or None, library=library)
    if request.method == "POST" and form.is_valid():
        created_files = []
        try:
            with transaction.atomic():
                form.instance.library = library
                book = form.save()
                old_cover = _apply_book_files(form, book, created_files)
                record_initial_events(book, request.user)
        except Exception:
            _remove_created_files(created_files)
            raise
        if old_cover:
            delete_cover(old_cover)
        messages.success(request, "Book added to your library.")
        return redirect(book)
    return render(request, "catalog/book_form.html", {"form": form, "mode": "create", "current_view": "all"})


@login_required
@require_http_methods(["GET", "POST"])
def book_update(request, book_id):
    library = get_or_create_library(request.user)
    book = _owned_book_or_404(request.user, book_id, trashed=False)
    form = BookForm(request.POST or None, request.FILES or None, instance=book, library=library)

    if request.method == "POST" and form.is_valid():
        created_files = []
        try:
            with transaction.atomic():
                current = Book.objects.select_for_update().get(id=book.id, library=library, deleted_at__isnull=True)
                submitted_version = form.cleaned_data.get("version") or 0
                if submitted_version != current.version:
                    form.add_error(None, "This book changed in another session. Reload the page and try again.")
                    return render(
                        request,
                        "catalog/book_form.html",
                        {
                            "form": form,
                            "book": current,
                            "available_attachments": available_attachments(current),
                            "mode": "edit",
                            "current_view": "all",
                        },
                        status=409,
                    )
                previous = copy.copy(current)
                form.instance.version = current.version + 1
                updated = form.save()
                old_cover = _apply_book_files(form, updated, created_files)
                record_status_event(updated, previous, request.user)
        except Exception:
            _remove_created_files(created_files)
            raise
        if old_cover:
            delete_cover(old_cover)
        messages.success(request, "Book changes saved.")
        return redirect(updated)

    return render(
        request,
        "catalog/book_form.html",
        {
            "form": form,
            "book": book,
            "available_attachments": available_attachments(book),
            "mode": "edit",
            "current_view": "all",
        },
    )


@login_required
@require_GET
def book_cover(request, book_id):
    book = _owned_book_or_404(request.user, book_id)
    path = cover_path(book.cover_filename)
    if path is None:
        transparent_gif = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
        return HttpResponse(transparent_gif, content_type="image/gif")
    return FileResponse(path.open("rb"), content_type="image/jpeg")


@login_required
@require_GET
def attachment_download(request, attachment_id):
    attachment = get_object_or_404(
        Attachment.objects.select_related("book__library"),
        id=attachment_id,
        book__library__owner=request.user,
    )
    path = attachment_path(attachment)
    if path is None:
        raise Http404("Attachment file not found.")
    return FileResponse(
        path.open("rb"),
        as_attachment=True,
        filename=attachment.original_name,
        content_type=attachment.content_type,
    )


@login_required
@require_POST
def attachment_delete(request, attachment_id):
    attachment = get_object_or_404(
        Attachment.objects.select_related("book__library"),
        id=attachment_id,
        book__library__owner=request.user,
        book__deleted_at__isnull=True,
    )
    book = attachment.book
    attachment.delete()
    messages.success(request, "Attachment removed.")
    return redirect("book-update", book_id=book.id)


@login_required
@require_http_methods(["GET", "POST"])
def settings_view(request):
    library = get_or_create_library(request.user)
    form = CategoryForm(request.POST or None, library=library)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Category added.")
        return redirect("settings")
    categories = library.categories.annotate(book_count=Count("books", distinct=True)).order_by(Lower("name"))
    return render(
        request,
        "catalog/settings.html",
        {"form": form, "categories": categories, "current_view": "settings"},
    )


@login_required
@require_POST
def category_delete(request, category_id):
    library = get_or_create_library(request.user)
    category = get_object_or_404(Category, id=category_id, library=library)
    name = category.name
    category.delete()
    messages.success(request, f"Category “{name}” removed. Books using it were kept.")
    return redirect("settings")


@login_required
@require_POST
def book_mark_owned(request, book_id):
    library = get_or_create_library(request.user)
    with transaction.atomic():
        book = get_object_or_404(
            Book.objects.select_for_update(),
            id=book_id,
            library=library,
            deleted_at__isnull=True,
        )
        previous = copy.copy(book)
        book.ownership_status = Book.OwnershipStatus.OWNED
        if book.reading_status == Book.ReadingStatus.INTERESTED:
            book.reading_status = Book.ReadingStatus.QUEUED
        book.version += 1
        book.full_clean()
        book.save()
        record_status_event(book, previous, request.user)
    messages.success(request, "Book moved to your shelf and reading queue.")
    return redirect(book)


@login_required
@require_POST
def book_trash(request, book_id):
    book = _owned_book_or_404(request.user, book_id, trashed=False)
    book.deleted_at = timezone.now()
    book.version += 1
    book.save(update_fields=("deleted_at", "version", "updated_at"))
    messages.success(request, "Book moved to trash. You can restore it later.")
    return redirect(f"{reverse('library')}?view=trash")


@login_required
@require_POST
def book_restore(request, book_id):
    book = _owned_book_or_404(request.user, book_id, trashed=True)
    book.deleted_at = None
    book.version += 1
    book.save(update_fields=("deleted_at", "version", "updated_at"))
    add_event(book, LifecycleEvent.EventType.RESTORED, request.user, "Restored from trash")
    messages.success(request, "Book restored to your library.")
    return redirect(book)


@login_required
@require_POST
def book_delete(request, book_id):
    book = _owned_book_or_404(request.user, book_id, trashed=True)
    title = book.title
    book.delete()
    messages.success(request, f"“{title}” was permanently deleted.")
    return redirect(f"{reverse('library')}?view=trash")


@login_required
@require_GET
def export_json(request):
    library = get_or_create_library(request.user)
    books = Book.objects.filter(library=library).prefetch_related("categories", "events", "attachments").order_by("created_at")
    payload = {
        "format": "booklife-export",
        "version": 1,
        "exported_at": timezone.now().isoformat(),
        "library": {"id": str(library.id), "name": library.name},
        "books": [
            {
                "id": str(book.id),
                "title": book.title,
                "author": book.author,
                "reading_status": book.reading_status,
                "ownership_status": book.ownership_status,
                "shelf_location": book.shelf_location,
                "rating": book.rating,
                "page_count": book.page_count,
                "finished_on": book.finished_on.isoformat() if book.finished_on else None,
                "notes": book.notes,
                "has_cover": cover_path(book.cover_filename) is not None,
                "categories": [category.name for category in book.categories.all()],
                "attachments": [
                    {
                        "name": attachment.original_name,
                        "content_type": attachment.content_type,
                        "size": attachment.size,
                    }
                    for attachment in available_attachments(book)
                ],
                "deleted_at": book.deleted_at.isoformat() if book.deleted_at else None,
                "created_at": book.created_at.isoformat(),
                "updated_at": book.updated_at.isoformat(),
                "events": [
                    {
                        "type": event.event_type,
                        "detail": event.detail,
                        "happened_at": event.happened_at.isoformat(),
                    }
                    for event in book.events.all()
                ],
            }
            for book in books
        ],
    }
    response = HttpResponse(
        json.dumps(payload, ensure_ascii=False, indent=2),
        content_type="application/json; charset=utf-8",
    )
    response["Content-Disposition"] = f'attachment; filename="booklife-{timezone.localdate().isoformat()}.json"'
    response["X-Content-Type-Options"] = "nosniff"
    return response
