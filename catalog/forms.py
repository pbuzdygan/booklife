from __future__ import annotations

import base64
import binascii

from django import forms
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile

from .models import Book, Category
from .storage import MAX_ATTACHMENTS_PER_BOOK, available_attachments, prepare_attachment, prepare_cover


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        files = data if isinstance(data, (list, tuple)) else ([data] if data else [])
        return [super().clean(item, initial) for item in files]


class BookForm(forms.ModelForm):
    version = forms.IntegerField(widget=forms.HiddenInput, required=False)
    isbn_cover_data = forms.CharField(
        required=False,
        max_length=2 * 1024 * 1024,
        widget=forms.HiddenInput,
    )
    new_categories = forms.CharField(
        required=False,
        max_length=500,
        label="New categories",
        help_text="Separate new category names with commas.",
    )
    cover = forms.FileField(
        required=False,
        label="Cover",
        help_text="Choose a JPEG, PNG, or WebP image up to 10 MB. It will be cropped and reduced.",
        widget=forms.FileInput(
            attrs={"accept": "image/jpeg,image/png,image/webp", "capture": "environment"}
        ),
    )
    clear_cover = forms.BooleanField(required=False, label="Remove the current cover")
    attachments = MultipleFileField(
        required=False,
        label="Attachments",
        help_text="Up to 10 files per book. PDF, UTF-8 TXT, JPEG, PNG, or WebP; 10 MB each.",
        widget=MultipleFileInput(
            attrs={"accept": ".pdf,.txt,image/jpeg,image/png,image/webp"}
        ),
    )

    class Meta:
        model = Book
        fields = (
            "title",
            "author",
            "reading_status",
            "ownership_status",
            "shelf_location",
            "rating",
            "page_count",
            "finished_on",
            "notes",
            "categories",
        )
        widgets = {
            "title": forms.TextInput(attrs={"autofocus": True, "autocomplete": "off"}),
            "author": forms.TextInput(attrs={"autocomplete": "off"}),
            "finished_on": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 6}),
            "categories": forms.CheckboxSelectMultiple(),
        }
        help_texts = {
            "shelf_location": "Optional detail such as “Living room · shelf 2”.",
            "rating": "Available after a book is read or abandoned.",
        }

    def __init__(self, *args, library, **kwargs):
        super().__init__(*args, **kwargs)
        self.library = library
        self.fields["categories"].queryset = library.categories.order_by("name")
        self.fields["version"].initial = self.instance.version if self.instance.pk else 0
        for name, field in self.fields.items():
            if name not in {"categories", "version", "clear_cover"}:
                field.widget.attrs.setdefault("class", "form-control")

    def clean_cover(self):
        upload = self.cleaned_data.get("cover")
        if upload:
            return prepare_cover(upload)

        data_url = self.cleaned_data.get("isbn_cover_data", "")
        if not data_url:
            return None
        prefix = "data:image/jpeg;base64,"
        if not data_url.startswith(prefix):
            raise ValidationError("The fetched cover could not be verified. Fetch it again or choose a file.")
        try:
            content = base64.b64decode(data_url.removeprefix(prefix), validate=True)
        except (binascii.Error, ValueError):
            raise ValidationError("The fetched cover could not be verified. Fetch it again or choose a file.") from None
        return prepare_cover(ContentFile(content, name="isbn-cover.jpg"))

    def clean_attachments(self):
        uploads = self.cleaned_data.get("attachments", [])
        existing_count = len(available_attachments(self.instance)) if self.instance.pk else 0
        if existing_count + len(uploads) > MAX_ATTACHMENTS_PER_BOOK:
            raise ValidationError(f"Keep no more than {MAX_ATTACHMENTS_PER_BOOK} attachments per book.")
        return [prepare_attachment(upload) for upload in uploads]

    def clean_new_categories(self):
        value = self.cleaned_data.get("new_categories", "")
        names = []
        seen = set()
        for raw_name in value.split(","):
            name = " ".join(raw_name.split())
            if not name:
                continue
            if len(name) > 80:
                raise ValidationError("Each category must be 80 characters or fewer.")
            lowered = name.casefold()
            if lowered not in seen:
                names.append(name)
                seen.add(lowered)
        if len(names) > 10:
            raise ValidationError("Add no more than 10 categories at once.")
        return names

    def save(self, commit=True):
        book = super().save(commit=commit)
        if commit:
            selected = list(self.cleaned_data.get("categories", []))
            for name in self.cleaned_data.get("new_categories", []):
                category = self.library.categories.filter(name__iexact=name).first()
                if category is None:
                    category = Category.objects.create(library=self.library, name=name)
                selected.append(category)
            book.categories.set(selected)
        return book


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ("name",)
        widgets = {"name": forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"})}

    def __init__(self, *args, library, **kwargs):
        super().__init__(*args, **kwargs)
        self.library = library

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if not name:
            raise ValidationError("Enter a category name.")
        if self.library.categories.filter(name__iexact=name).exists():
            raise ValidationError("A category with this name already exists.")
        return name

    def save(self, commit=True):
        self.instance.library = self.library
        return super().save(commit=commit)
