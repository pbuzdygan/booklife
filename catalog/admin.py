from django.contrib import admin
from django.contrib.auth import get_user_model

from .models import Book, Category, Library, LifecycleEvent


class OwnerFilter(admin.SimpleListFilter):
    """Filter records by the account that owns their library."""

    title = "User"
    parameter_name = "owner"

    def lookups(self, request, model_admin):
        return get_user_model().objects.order_by("username").values_list("id", "username")

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(library__owner_id=self.value())
        return queryset


@admin.register(Library)
class LibraryAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "created_at")
    search_fields = ("name", "owner__username")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "library", "owner", "created_at")
    list_filter = (OwnerFilter,)
    search_fields = ("name",)

    @admin.display(description="User", ordering="library__owner__username")
    def owner(self, category):
        return category.library.owner.username

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("library__owner")


class LifecycleEventInline(admin.TabularInline):
    model = LifecycleEvent
    extra = 0
    readonly_fields = ("event_type", "detail", "happened_at", "actor", "created_at")
    can_delete = False


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "reading_status", "ownership_status", "library", "owner", "deleted_at")
    list_filter = ("reading_status", "ownership_status", "deleted_at", OwnerFilter)
    search_fields = ("title", "author", "notes")
    filter_horizontal = ("categories",)
    inlines = (LifecycleEventInline,)

    @admin.display(description="User", ordering="library__owner__username")
    def owner(self, book):
        return book.library.owner.username

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("library__owner")


@admin.register(LifecycleEvent)
class LifecycleEventAdmin(admin.ModelAdmin):
    list_display = ("book", "event_type", "happened_at", "actor")
    list_filter = ("event_type",)
    search_fields = ("book__title", "detail")
