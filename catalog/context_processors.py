from django.db.models import Q

from .models import Book


def library_navigation(request):
    if not request.user.is_authenticated:
        return {}
    active = Book.objects.active().filter(library__owner=request.user)
    return {
        "navigation_counts": {
            "all": active.count(),
            "queue": active.filter(
                reading_status__in=(Book.ReadingStatus.QUEUED, Book.ReadingStatus.READING)
            ).count(),
            "wishlist": active.filter(
                Q(reading_status=Book.ReadingStatus.INTERESTED)
                | Q(ownership_status=Book.OwnershipStatus.WANTED)
            ).count(),
            "read": active.filter(reading_status=Book.ReadingStatus.READ).count(),
            "loaned": active.filter(ownership_status=Book.OwnershipStatus.LOANED).count(),
            "trash": Book.objects.trashed().filter(library__owner=request.user).count(),
        }
    }
