from __future__ import annotations

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Lower
from django.urls import reverse


class Library(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="booklife_library",
    )
    name = models.CharField(max_length=120, default="My library")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "libraries"

    def __str__(self) -> str:
        return self.name


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    library = models.ForeignKey(Library, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=80)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "library",
                name="catalog_category_unique_name_per_library",
            )
        ]

    def save(self, *args, **kwargs):
        self.name = self.name.strip()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


class BookQuerySet(models.QuerySet):
    def active(self):
        return self.filter(deleted_at__isnull=True)

    def trashed(self):
        return self.filter(deleted_at__isnull=False)


class Book(models.Model):
    class ReadingStatus(models.TextChoices):
        INTERESTED = "interested", "Interested"
        QUEUED = "queued", "Queued"
        READING = "reading", "Reading"
        READ = "read", "Read"
        ABANDONED = "abandoned", "Abandoned"

    class OwnershipStatus(models.TextChoices):
        WANTED = "wanted", "To buy"
        OWNED = "owned", "Shelf"
        LOANED = "loaned", "Loaned"
        GIVEN_AWAY = "given_away", "Given away"
        UNKNOWN = "unknown", "Unknown"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    library = models.ForeignKey(Library, on_delete=models.CASCADE, related_name="books")
    title = models.CharField(max_length=255)
    author = models.CharField(max_length=255, blank=True)
    reading_status = models.CharField(
        max_length=16,
        choices=ReadingStatus.choices,
        default=ReadingStatus.INTERESTED,
    )
    ownership_status = models.CharField(
        max_length=16,
        choices=OwnershipStatus.choices,
        default=OwnershipStatus.WANTED,
    )
    shelf_location = models.CharField(max_length=120, blank=True)
    rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
    )
    page_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(100_000)],
    )
    finished_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, validators=[MaxLengthValidator(5_000)])
    cover_filename = models.CharField(max_length=80, blank=True, editable=False)
    categories = models.ManyToManyField(Category, related_name="books", blank=True)
    version = models.PositiveIntegerField(default=1)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = BookQuerySet.as_manager()

    class Meta:
        ordering = (Lower("title"), "created_at")
        indexes = [
            models.Index(fields=("library", "reading_status"), name="book_library_reading_idx"),
            models.Index(fields=("library", "ownership_status"), name="book_library_owner_idx"),
            models.Index(fields=("library", "finished_on"), name="book_library_finish_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(rating__isnull=True) | models.Q(rating__gte=1, rating__lte=10),
                name="catalog_book_rating_range",
            ),
            models.CheckConstraint(
                condition=models.Q(page_count__isnull=True) | models.Q(page_count__gte=1, page_count__lte=100_000),
                name="catalog_book_page_count_range",
            ),
        ]

    def clean(self):
        self.title = self.title.strip()
        self.author = self.author.strip()
        self.shelf_location = self.shelf_location.strip()
        self.notes = self.notes.strip()
        errors = {}
        if not self.title:
            errors["title"] = "Enter a title."
        if self.rating is not None and self.reading_status not in {
            self.ReadingStatus.READ,
            self.ReadingStatus.ABANDONED,
        }:
            errors["rating"] = "A rating is available after a book is read or abandoned."
        if self.finished_on and self.reading_status != self.ReadingStatus.READ:
            errors["finished_on"] = "A finish date is available only for a read book."
        if errors:
            raise ValidationError(errors)

    def get_absolute_url(self) -> str:
        return reverse("book-detail", kwargs={"book_id": self.id})

    def __str__(self) -> str:
        return self.title


class Attachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="attachments")
    original_name = models.CharField(max_length=160)
    stored_filename = models.CharField(max_length=80, unique=True, editable=False)
    content_type = models.CharField(max_length=80, editable=False)
    size = models.PositiveIntegerField(editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)

    def __str__(self) -> str:
        return self.original_name


class LifecycleEvent(models.Model):
    class EventType(models.TextChoices):
        DISCOVERED = "discovered", "Discovered"
        ACQUIRED = "acquired", "Acquired"
        QUEUED = "queued", "Queued"
        STARTED = "started", "Started reading"
        READ = "read", "Read"
        ABANDONED = "abandoned", "Abandoned"
        LOANED = "loaned", "Loaned"
        RETURNED = "returned", "Returned"
        GIVEN_AWAY = "given_away", "Given away"
        RESTORED = "restored", "Restored"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=24, choices=EventType.choices)
    detail = models.CharField(max_length=255, blank=True)
    happened_at = models.DateTimeField()
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="booklife_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-happened_at", "-created_at")
        indexes = [models.Index(fields=("book", "happened_at"), name="event_book_happened_idx")]

    def __str__(self) -> str:
        return f"{self.get_event_type_display()}: {self.book.title}"
