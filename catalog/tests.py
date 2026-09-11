import base64
import json
import io
import os
import sqlite3
import tempfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from PIL import Image

from .models import Attachment, Book, Category, LifecycleEvent
from .isbn import ISBNMetadata, ISBNNotFound, InvalidISBN, fetch_isbn_metadata, normalise_isbn
from .management.commands.prepare_booklife import create_first_run_user
from .management.commands.prepare_booklife import database_has_personal_data
from .services import get_or_create_library
from .signals import secure_sqlite_files


class SQLitePermissionTests(TestCase):
    def test_database_and_sidecars_are_private(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "booklife.sqlite3"
            sidecar = Path(f"{database}-wal")
            database.touch(mode=0o644)
            sidecar.touch(mode=0o644)
            os.chmod(database, 0o644)
            os.chmod(sidecar, 0o644)
            connection = SimpleNamespace(
                vendor="sqlite",
                settings_dict={"NAME": database},
            )

            secure_sqlite_files(sender=None, connection=connection)

            self.assertEqual(database.stat().st_mode & 0o777, 0o600)
            self.assertEqual(sidecar.stat().st_mode & 0o777, 0o600)


class BookModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="reader")
        self.library = get_or_create_library(self.user)

    def test_rating_requires_read_or_abandoned_status(self):
        book = Book(
            library=self.library,
            title="A queued book",
            reading_status=Book.ReadingStatus.QUEUED,
            ownership_status=Book.OwnershipStatus.OWNED,
            rating=8,
        )
        with self.assertRaises(ValidationError):
            book.full_clean()

    def test_finish_date_requires_read_status(self):
        book = Book(
            library=self.library,
            title="Not finished",
            reading_status=Book.ReadingStatus.READING,
            finished_on=date(2026, 8, 1),
        )
        with self.assertRaises(ValidationError):
            book.full_clean()

    def test_soft_delete_querysets_are_separate(self):
        active = Book.objects.create(library=self.library, title="Active")
        deleted = Book.objects.create(library=self.library, title="Deleted", deleted_at=timezone.now())
        self.assertQuerySetEqual(Book.objects.active(), [active])
        self.assertQuerySetEqual(Book.objects.trashed(), [deleted])


class ISBNTests(TestCase):
    def test_isbn_checksums_and_book_prefix_are_enforced(self):
        self.assertEqual(normalise_isbn("ISBN 978-0-306-40615-7"), "9780306406157")
        self.assertEqual(normalise_isbn("0-306-40615-2"), "0306406152")
        for value in ("9780306406158", "4006381333931", "not an isbn"):
            with self.assertRaises(InvalidISBN):
                normalise_isbn(value)

    @patch("catalog.isbn._fetch_cover_data_url", return_value="")
    @patch("catalog.isbn._national_library_metadata", return_value=("Polish edition", "Eliot Siegel"))
    @patch("catalog.isbn._open_library_metadata", side_effect=ISBNNotFound("missing"))
    def test_national_library_is_used_when_open_library_has_no_record(
        self,
        _open_library,
        _national_library,
        _cover,
    ):
        metadata = fetch_isbn_metadata("9788074130519")
        self.assertEqual(metadata.title, "Polish edition")
        self.assertEqual(metadata.author, "Eliot Siegel")
        self.assertEqual(metadata.source, "National Library of Poland")


class FirstRunAccountTests(TestCase):
    def test_empty_or_partially_initialised_database_is_treated_as_new(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "booklife.sqlite3"
            self.assertFalse(database_has_personal_data(database_path))
            with sqlite3.connect(database_path) as database:
                database.execute("CREATE TABLE auth_user (id INTEGER PRIMARY KEY)")
            self.assertFalse(database_has_personal_data(database_path))
            with sqlite3.connect(database_path) as database:
                database.execute("INSERT INTO auth_user DEFAULT VALUES")
            self.assertTrue(database_has_personal_data(database_path))

    def test_first_run_user_is_regular_and_is_never_reset(self):
        user, created = create_first_run_user()
        self.assertTrue(created)
        self.assertEqual(user.username, "booklife")
        self.assertTrue(user.check_password("booklife"))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

        user.set_password("changed-password")
        user.save(update_fields=("password",))
        same_user, created_again = create_first_run_user()
        self.assertFalse(created_again)
        self.assertTrue(same_user.check_password("changed-password"))


class SessionConfigurationTests(TestCase):
    def test_sessions_are_cleared_when_the_application_process_restarts(self):
        self.assertEqual(settings.SESSION_ENGINE, "django.contrib.sessions.backends.cache")
        self.assertEqual(settings.SESSION_CACHE_ALIAS, "default")
        self.assertEqual(settings.SESSION_COOKIE_AGE, 12 * 60 * 60)
        self.assertTrue(settings.SESSION_EXPIRE_AT_BROWSER_CLOSE)
        self.assertFalse(settings.SESSION_SAVE_EVERY_REQUEST)


class PwaTests(TestCase):
    def test_service_worker_is_available_at_the_root_scope(self):
        response = self.client.get(reverse("service-worker"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        self.assertEqual(response["Cache-Control"], "no-cache")
        self.assertIn(b"Authenticated HTML is never stored offline", response.content)


class AdminTransparencyTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin = user_model.objects.create_superuser(
            username="administrator",
            password="a-secure-test-password",
            email="administrator@example.test",
        )
        self.owner = user_model.objects.create_user(username="first-owner")
        self.other_owner = user_model.objects.create_user(username="second-owner")
        self.library = get_or_create_library(self.owner)
        self.other_library = get_or_create_library(self.other_owner)
        self.category = Category.objects.create(library=self.library, name="History")
        Category.objects.create(library=self.other_library, name="History")
        Book.objects.create(library=self.library, title="First owner book")
        Book.objects.create(library=self.other_library, title="Second owner book")
        self.client.force_login(self.admin)

    def test_book_admin_shows_and_filters_by_library_owner(self):
        response = self.client.get(reverse("admin:catalog_book_changelist"))

        self.assertContains(response, "User")
        self.assertContains(response, "first-owner")
        self.assertContains(response, "second-owner")

        response = self.client.get(
            reverse("admin:catalog_book_changelist"), {"owner": self.owner.pk}
        )
        self.assertContains(response, ">First owner book</a>", count=1)
        self.assertNotContains(response, "Second owner book")

    def test_category_admin_shows_and_filters_by_library_owner(self):
        response = self.client.get(
            reverse("admin:catalog_category_changelist"), {"owner": self.owner.pk}
        )

        self.assertContains(response, "User")
        self.assertContains(response, "first-owner")
        self.assertContains(response, ">History</a>", count=1)


class LibraryViewTests(TestCase):
    def setUp(self):
        cache.clear()
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="owner", password="a-secure-test-password")
        self.other_user = user_model.objects.create_user(username="other")
        self.library = get_or_create_library(self.user)
        self.other_library = get_or_create_library(self.other_user)
        self.client.force_login(self.user)

    def book(self, **values):
        defaults = {
            "library": self.library,
            "title": "Atomic Habits",
            "author": "James Clear",
            "reading_status": Book.ReadingStatus.QUEUED,
            "ownership_status": Book.OwnershipStatus.OWNED,
        }
        defaults.update(values)
        return Book.objects.create(**defaults)

    def form_data(self, **values):
        defaults = {
            "title": "A new book",
            "author": "A. Writer",
            "reading_status": Book.ReadingStatus.INTERESTED,
            "ownership_status": Book.OwnershipStatus.WANTED,
            "shelf_location": "",
            "rating": "",
            "page_count": "",
            "finished_on": "",
            "notes": "",
            "categories": [],
            "new_categories": "",
            "version": "0",
        }
        defaults.update(values)
        return defaults

    def test_library_requires_authentication(self):
        self.client.logout()
        response = self.client.get(reverse("library"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('library')}")

    def test_create_book_records_lifecycle_and_new_category(self):
        response = self.client.post(
            reverse("book-create"),
            self.form_data(new_categories="Leadership, Team"),
        )
        book = Book.objects.get(title="A new book", library=self.library)
        self.assertRedirects(response, book.get_absolute_url())
        self.assertSetEqual(set(book.categories.values_list("name", flat=True)), {"Leadership", "Team"})
        self.assertTrue(book.events.filter(event_type=LifecycleEvent.EventType.DISCOVERED).exists())

    @patch("catalog.views.fetch_isbn_metadata")
    def test_isbn_lookup_returns_only_the_fields_used_by_the_form(self, fetch_metadata):
        fetch_metadata.return_value = ISBNMetadata(
            isbn="9780306406157",
            title="A fetched title",
            author="A. Author",
            cover_data_url="data:image/jpeg;base64,Y292ZXI=",
            source="Open Library",
        )
        response = self.client.get(reverse("isbn-lookup"), {"isbn": "978-0-306-40615-7"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.json()),
            {"isbn", "title", "author", "cover_data_url", "source"},
        )
        fetch_metadata.assert_called_once_with("9780306406157")

    def test_fetched_cover_is_saved_through_the_normal_cover_validation(self):
        image_bytes = io.BytesIO()
        Image.new("RGB", (320, 480), "teal").save(image_bytes, format="JPEG")
        cover_data = "data:image/jpeg;base64," + base64.b64encode(image_bytes.getvalue()).decode("ascii")

        with tempfile.TemporaryDirectory() as directory, override_settings(DATA_DIR=Path(directory)):
            response = self.client.post(
                reverse("book-create"),
                {**self.form_data(title="Fetched cover"), "isbn_cover_data": cover_data},
            )
            book = Book.objects.get(library=self.library, title="Fetched cover")
            self.assertRedirects(response, book.get_absolute_url())
            self.assertTrue((Path(directory) / "covers" / book.cover_filename).is_file())

    def test_search_and_saved_views_return_expected_books(self):
        queued = self.book()
        self.book(
            title="Deep Work",
            author="Cal Newport",
            reading_status=Book.ReadingStatus.INTERESTED,
            ownership_status=Book.OwnershipStatus.WANTED,
        )
        response = self.client.get(reverse("library"), {"view": "queue", "q": "atomic"})
        self.assertContains(response, queued.title)
        self.assertNotContains(response, "Deep Work")

    def test_primary_pages_render_with_real_templates(self):
        book = self.book(
            reading_status=Book.ReadingStatus.READ,
            rating=9,
            finished_on=date(2026, 8, 30),
        )
        for url in (
            reverse("library"),
            f"{reverse('library')}?view=journal",
            f"{reverse('library')}?view=trash",
            book.get_absolute_url(),
            reverse("book-create"),
            reverse("book-update", args=[book.id]),
            reverse("settings"),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_book_form_loads_the_local_barcode_scanner_fallback(self):
        response = self.client.get(reverse("book-create"))
        self.assertContains(response, "catalog/vendor/zxing-browser-0.2.1.min.js")
        self.assertNotContains(response, "unpkg.com")

    def test_book_form_keeps_optional_fields_collapsed_for_quick_capture(self):
        response = self.client.get(reverse("book-create"))

        self.assertContains(response, "Quick capture")
        self.assertContains(response, 'class="quick-cover"')
        self.assertContains(response, "Add or replace cover")
        self.assertContains(response, "More details")
        self.assertNotContains(response, '<label for="id_cover">Cover</label>')
        self.assertNotContains(response, '<details class="form-details" open>')

        book = self.book()
        response = self.client.get(reverse("book-update", args=[book.id]))
        self.assertContains(response, '<details class="form-details" open>')

    def test_empty_view_and_long_non_english_title_render(self):
        empty_response = self.client.get(reverse("library"))
        self.assertContains(empty_response, "Nothing here yet")

        long_title = "The life of a book — " + ("very long title " * 14)
        book = self.book(title=long_title[:255], author="Zoë Brontë")
        response = self.client.get(reverse("library"), {"q": "Brontë"})
        self.assertContains(response, book.title)
        self.assertContains(response, book.author)

    def test_invalid_category_filter_is_ignored(self):
        self.book()
        response = self.client.get(reverse("library"), {"category": "not-a-uuid"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Atomic Habits")

    def test_applied_filters_do_not_reopen_the_filter_panel(self):
        self.book()
        response = self.client.get(reverse("library"), {"status": Book.ReadingStatus.QUEUED})
        self.assertContains(response, "data-filter-panel")
        self.assertNotContains(response, "data-filter-panel open")

    def test_book_from_another_library_is_not_visible(self):
        other_book = Book.objects.create(library=self.other_library, title="Private book")
        response = self.client.get(reverse("book-detail", args=[other_book.id]))
        self.assertEqual(response.status_code, 404)

    def test_mark_owned_moves_wishlist_book_to_queue(self):
        book = self.book(
            title="Wishlist book",
            reading_status=Book.ReadingStatus.INTERESTED,
            ownership_status=Book.OwnershipStatus.WANTED,
        )
        self.client.post(reverse("book-mark-owned", args=[book.id]))
        book.refresh_from_db()
        self.assertEqual(book.reading_status, Book.ReadingStatus.QUEUED)
        self.assertEqual(book.ownership_status, Book.OwnershipStatus.OWNED)
        self.assertSetEqual(
            set(book.events.values_list("event_type", flat=True)),
            {LifecycleEvent.EventType.QUEUED, LifecycleEvent.EventType.ACQUIRED},
        )

    def test_update_rejects_stale_version(self):
        book = self.book()
        response = self.client.post(
            reverse("book-update", args=[book.id]),
            self.form_data(
                title=book.title,
                author=book.author,
                reading_status=book.reading_status,
                ownership_status=book.ownership_status,
                version="0",
            ),
        )
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, "changed in another session", status_code=409)

    def test_update_to_read_records_completion_event(self):
        book = self.book()
        response = self.client.post(
            reverse("book-update", args=[book.id]),
            self.form_data(
                title=book.title,
                author=book.author,
                reading_status=Book.ReadingStatus.READ,
                ownership_status=book.ownership_status,
                rating="9",
                page_count="320",
                finished_on="2026-08-30",
                notes="Worth remembering.",
                version=str(book.version),
            ),
        )
        book.refresh_from_db()
        self.assertRedirects(response, book.get_absolute_url())
        self.assertEqual(book.rating, 9)
        self.assertTrue(book.events.filter(event_type=LifecycleEvent.EventType.READ).exists())

    def test_trash_restore_and_permanent_delete(self):
        book = self.book()
        self.client.post(reverse("book-trash", args=[book.id]))
        book.refresh_from_db()
        self.assertIsNotNone(book.deleted_at)

        self.client.post(reverse("book-restore", args=[book.id]))
        book.refresh_from_db()
        self.assertIsNone(book.deleted_at)

        self.client.post(reverse("book-trash", args=[book.id]))
        self.client.post(reverse("book-delete", args=[book.id]))
        self.assertFalse(Book.objects.filter(id=book.id).exists())

    def test_json_export_is_portable_and_owner_scoped(self):
        own_book = self.book(notes="Private note")
        Book.objects.create(library=self.other_library, title="Someone else's book")
        response = self.client.get(reverse("export-json"))
        payload = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["format"], "booklife-export")
        self.assertEqual([item["id"] for item in payload["books"]], [str(own_book.id)])
        self.assertEqual(payload["books"][0]["notes"], "Private note")

    def test_settings_adds_and_removes_only_owned_categories(self):
        response = self.client.post(reverse("settings"), {"name": "Biography"})
        self.assertRedirects(response, reverse("settings"))
        category = Category.objects.get(library=self.library, name="Biography")

        book = self.book()
        book.categories.add(category)
        response = self.client.post(reverse("category-delete", args=[category.id]))
        self.assertRedirects(response, reverse("settings"))
        self.assertFalse(Category.objects.filter(id=category.id).exists())
        self.assertTrue(Book.objects.filter(id=book.id).exists())

        other_category = self.other_library.categories.first()
        response = self.client.post(reverse("category-delete", args=[other_category.id]))
        self.assertEqual(response.status_code, 404)

    def test_cover_and_attachment_are_private_and_missing_files_are_hidden(self):
        image_bytes = io.BytesIO()
        Image.new("RGB", (900, 1200), "navy").save(image_bytes, format="JPEG")
        image_bytes.seek(0)
        cover = SimpleUploadedFile("cover.jpg", image_bytes.read(), content_type="image/jpeg")
        attachment = SimpleUploadedFile("notes.pdf", b"%PDF-1.4\nbook notes", content_type="application/pdf")

        with tempfile.TemporaryDirectory() as directory, override_settings(DATA_DIR=Path(directory)):
            response = self.client.post(
                reverse("book-create"),
                {
                    **self.form_data(),
                    "cover": cover,
                    "attachments": [attachment],
                },
            )
            book = Book.objects.get(library=self.library, title="A new book")
            stored_attachment = Attachment.objects.get(book=book)
            self.assertRedirects(response, book.get_absolute_url())
            self.assertTrue((Path(directory) / "covers" / book.cover_filename).is_file())
            attachment_path = Path(directory) / "attachments" / stored_attachment.stored_filename
            self.assertTrue(attachment_path.is_file())

            self.assertEqual(self.client.get(reverse("book-cover", args=[book.id])).status_code, 200)
            download = self.client.get(reverse("attachment-download", args=[stored_attachment.id]))
            self.assertEqual(download.status_code, 200)
            self.assertIn("attachment", download["Content-Disposition"])

            other_client = Client()
            other_client.force_login(self.other_user)
            self.assertEqual(other_client.get(reverse("book-cover", args=[book.id])).status_code, 404)
            self.assertEqual(
                other_client.get(reverse("attachment-download", args=[stored_attachment.id])).status_code,
                404,
            )

            attachment_path.unlink()
            detail = self.client.get(book.get_absolute_url())
            self.assertNotContains(detail, "notes.pdf")

            (Path(directory) / "covers" / book.cover_filename).unlink()
            missing_cover = self.client.get(reverse("book-cover", args=[book.id]))
            self.assertEqual(missing_cover.status_code, 200)
            self.assertEqual(missing_cover["Content-Type"], "image/gif")

    def test_unsupported_attachment_is_rejected_without_creating_a_book(self):
        unsafe = SimpleUploadedFile("program.exe", b"MZ\x00\x00", content_type="application/octet-stream")
        with tempfile.TemporaryDirectory() as directory, override_settings(DATA_DIR=Path(directory)):
            response = self.client.post(
                reverse("book-create"),
                {**self.form_data(title="Unsafe upload"), "attachments": [unsafe]},
            )
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Use a PDF, UTF-8 TXT, JPEG, PNG, or WebP attachment")
            self.assertFalse(Book.objects.filter(library=self.library, title="Unsafe upload").exists())

    def test_png_attachment_is_detected_from_content_when_filename_is_unhelpful(self):
        image_bytes = io.BytesIO()
        Image.new("RGBA", (80, 120), (31, 88, 133, 180)).save(image_bytes, format="PNG")
        attachment = SimpleUploadedFile(
            "gallery-upload",
            image_bytes.getvalue(),
            content_type="application/octet-stream",
        )

        with tempfile.TemporaryDirectory() as directory, override_settings(DATA_DIR=Path(directory)):
            response = self.client.post(
                reverse("book-create"),
                {**self.form_data(title="PNG attachment"), "attachments": [attachment]},
            )

            book = Book.objects.get(library=self.library, title="PNG attachment")
            stored_attachment = Attachment.objects.get(book=book)
            self.assertRedirects(response, book.get_absolute_url())
            self.assertEqual(stored_attachment.original_name, "gallery-upload")
            self.assertEqual(stored_attachment.content_type, "image/png")
            self.assertTrue(stored_attachment.stored_filename.endswith(".png"))
            self.assertTrue(
                (Path(directory) / "attachments" / stored_attachment.stored_filename).is_file()
            )

    def test_security_headers_are_added(self):
        response = self.client.get(reverse("library"))
        self.assertIn("default-src 'self'", response["Content-Security-Policy"])
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertNotIn("Cross-Origin-Opener-Policy", response)

        secure_response = self.client.get(reverse("library"), secure=True)
        self.assertEqual(secure_response["Cross-Origin-Opener-Policy"], "same-origin")


class LoginRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        get_user_model().objects.create_user(username="reader", password="a-secure-test-password")
        get_user_model().objects.create_user(username="another-reader", password="another-secure-password")
        self.client = Client(REMOTE_ADDR="198.51.100.24")

    def test_failed_logins_are_rate_limited(self):
        for _ in range(5):
            response = self.client.post(reverse("login"), {"username": "reader", "password": "wrong"})
            self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse("login"), {"username": "reader", "password": "wrong"})
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Too many sign-in attempts", status_code=429)

    def test_limited_account_does_not_block_another_account_on_the_same_network(self):
        for _ in range(5):
            self.client.post(reverse("login"), {"username": "reader", "password": "wrong"})

        response = self.client.post(
            reverse("login"),
            {"username": "another-reader", "password": "another-secure-password"},
        )

        self.assertRedirects(response, reverse("library"))
