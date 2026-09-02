from django.urls import path

from . import views


urlpatterns = [
    path("", views.library_view, name="library"),
    path("healthz/", views.healthz, name="healthz"),
    path("service-worker.js", views.service_worker, name="service-worker"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("isbn/lookup/", views.isbn_lookup, name="isbn-lookup"),
    path("settings/", views.settings_view, name="settings"),
    path("settings/categories/<uuid:category_id>/delete/", views.category_delete, name="category-delete"),
    path("books/new/", views.book_create, name="book-create"),
    path("books/<uuid:book_id>/", views.book_detail, name="book-detail"),
    path("books/<uuid:book_id>/cover/", views.book_cover, name="book-cover"),
    path("books/<uuid:book_id>/edit/", views.book_update, name="book-update"),
    path("books/<uuid:book_id>/own/", views.book_mark_owned, name="book-mark-owned"),
    path("books/<uuid:book_id>/trash/", views.book_trash, name="book-trash"),
    path("books/<uuid:book_id>/restore/", views.book_restore, name="book-restore"),
    path("books/<uuid:book_id>/delete/", views.book_delete, name="book-delete"),
    path("attachments/<uuid:attachment_id>/download/", views.attachment_download, name="attachment-download"),
    path("attachments/<uuid:attachment_id>/delete/", views.attachment_delete, name="attachment-delete"),
    path("export/books.json", views.export_json, name="export-json"),
]
