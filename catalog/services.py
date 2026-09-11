from __future__ import annotations

from datetime import datetime, time

from django.db import transaction
from django.utils import timezone

from .models import Book, Category, Library, LifecycleEvent


DEFAULT_CATEGORIES = (
    "Self-development",
    "Time management",
    "Team",
    "Family",
    "Psychology",
    "Stoicism",
    "Fiction",
)


@transaction.atomic
def get_or_create_library(user) -> Library:
    library, created = Library.objects.get_or_create(owner=user, defaults={"name": "My library"})
    if created:
        Category.objects.bulk_create([Category(library=library, name=name) for name in DEFAULT_CATEGORIES])
    return library


def event_time_for_book(book: Book, event_type: str):
    if event_type == LifecycleEvent.EventType.READ and book.finished_on:
        value = datetime.combine(book.finished_on, time(hour=12))
        return timezone.make_aware(value, timezone.get_current_timezone())
    return timezone.now()


def add_event(book: Book, event_type: str, actor, detail: str = "") -> LifecycleEvent:
    return LifecycleEvent.objects.create(
        book=book,
        event_type=event_type,
        detail=detail[:255],
        happened_at=event_time_for_book(book, event_type),
        actor=actor,
    )


def record_initial_events(book: Book, actor) -> None:
    add_event(book, LifecycleEvent.EventType.DISCOVERED, actor, "Added to Booklife")
    record_status_event(book, None, actor)


def record_status_event(book: Book, previous: Book | None, actor) -> None:
    previous_reading = previous.reading_status if previous else None
    previous_ownership = previous.ownership_status if previous else None

    if previous_reading != book.reading_status:
        reading_events = {
            Book.ReadingStatus.QUEUED: (LifecycleEvent.EventType.QUEUED, "Added to the reading queue"),
            Book.ReadingStatus.READING: (LifecycleEvent.EventType.STARTED, "Started reading"),
            Book.ReadingStatus.READ: (LifecycleEvent.EventType.READ, "Finished reading"),
            Book.ReadingStatus.ABANDONED: (LifecycleEvent.EventType.ABANDONED, "Stopped reading"),
        }
        if event := reading_events.get(book.reading_status):
            add_event(book, event[0], actor, event[1])

    if previous_ownership != book.ownership_status:
        ownership_events = {
            Book.OwnershipStatus.OWNED: (LifecycleEvent.EventType.ACQUIRED, "Moved to the shelf"),
            Book.OwnershipStatus.LOANED: (LifecycleEvent.EventType.LOANED, "Away from the shelf"),
            Book.OwnershipStatus.GIVEN_AWAY: (LifecycleEvent.EventType.GIVEN_AWAY, "Passed on to a new home"),
        }
        if event := ownership_events.get(book.ownership_status):
            add_event(book, event[0], actor, event[1])
