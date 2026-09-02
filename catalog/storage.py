from __future__ import annotations

import io
import logging
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import Attachment, Book


logger = logging.getLogger(__name__)

COVER_SIZE = (480, 720)
COVER_MAX_BYTES = 10 * 1024 * 1024
ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024
TEXT_ATTACHMENT_MAX_BYTES = 2 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_ATTACHMENTS_PER_BOOK = 10
SAFE_STORED_NAME = re.compile(r"^[0-9a-f]{32}\.(?:jpg|jpeg|png|webp|pdf|txt)$")


@dataclass(frozen=True)
class PreparedAttachment:
    upload: object
    original_name: str
    extension: str
    content_type: str
    size: int


def _data_subdirectory(name: str) -> Path:
    directory = settings.DATA_DIR / name
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    return directory


def _stored_path(directory_name: str, stored_filename: str) -> Path | None:
    if not SAFE_STORED_NAME.fullmatch(stored_filename):
        return None
    return _data_subdirectory(directory_name) / stored_filename


def _normalise_uploaded_name(name: str) -> str:
    basename = Path(name.replace("\\", "/")).name
    cleaned = "".join(character for character in basename if character.isprintable()).strip()
    return cleaned[:160] or "attachment"


def prepare_cover(upload) -> bytes:
    if upload.size > COVER_MAX_BYTES:
        raise ValidationError("The cover must be 10 MB or smaller.")

    try:
        upload.seek(0)
        with Image.open(upload) as opened:
            if opened.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValidationError("Use a JPEG, PNG, or WebP cover image.")
            if opened.width * opened.height > MAX_IMAGE_PIXELS:
                raise ValidationError("The cover image has too many pixels.")
            opened.load()
            image = ImageOps.exif_transpose(opened)
            if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
                rgba = image.convert("RGBA")
                flattened = Image.new("RGB", rgba.size, "white")
                flattened.paste(rgba, mask=rgba.getchannel("A"))
                image = flattened
            else:
                image = image.convert("RGB")
            image = ImageOps.fit(image, COVER_SIZE, method=Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=82, optimize=True, progressive=True)
            return output.getvalue()
    except ValidationError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError):
        raise ValidationError("The selected cover is not a valid supported image.") from None
    finally:
        upload.seek(0)


def save_cover(content: bytes) -> str:
    stored_filename = f"{uuid.uuid4().hex}.jpg"
    path = _stored_path("covers", stored_filename)
    if path is None:
        raise ValueError("Could not create a safe cover filename.")
    try:
        with path.open("xb") as handle:
            handle.write(content)
        os.chmod(path, 0o600)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return stored_filename


def cover_path(stored_filename: str) -> Path | None:
    path = _stored_path("covers", stored_filename)
    return path if path and path.is_file() else None


def delete_cover(stored_filename: str) -> None:
    path = _stored_path("covers", stored_filename)
    if path:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Could not remove an obsolete cover file: %s", exc)


def prepare_attachment(upload) -> PreparedAttachment:
    if upload.size > ATTACHMENT_MAX_BYTES:
        raise ValidationError("Each attachment must be 10 MB or smaller.")

    original_name = _normalise_uploaded_name(upload.name)
    extension = Path(original_name).suffix.lower()
    upload.seek(0)
    header = upload.read(16)
    upload.seek(0)

    detected = None
    # Browsers and mobile gallery applications do not always preserve a useful
    # filename. Detect binary formats from their contents and assign Booklife's
    # own safe extension instead of trusting the client-provided name or MIME
    # type. Text remains extension-gated because it has no unique signature.
    if header.startswith(b"%PDF-"):
        detected = (".pdf", "application/pdf")
    elif header.startswith(b"\xff\xd8\xff"):
        detected = (".jpg", "image/jpeg")
    elif header.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = (".png", "image/png")
    elif header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        detected = (".webp", "image/webp")
    elif extension == ".txt" and upload.size <= TEXT_ATTACHMENT_MAX_BYTES:
        try:
            upload.read().decode("utf-8")
        except (UnicodeDecodeError, OSError):
            detected = None
        else:
            detected = (".txt", "text/plain")
        finally:
            upload.seek(0)

    if detected is None:
        raise ValidationError("Use a PDF, UTF-8 TXT, JPEG, PNG, or WebP attachment.")

    if detected[1].startswith("image/"):
        try:
            with Image.open(upload) as image:
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise ValidationError("The attachment image has too many pixels.")
                image.verify()
        except ValidationError:
            raise
        except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError):
            raise ValidationError("The attachment is not a valid image.") from None
        finally:
            upload.seek(0)

    return PreparedAttachment(upload, original_name, detected[0], detected[1], upload.size)


def save_attachment(book: Book, prepared: PreparedAttachment) -> Attachment:
    stored_filename = f"{uuid.uuid4().hex}{prepared.extension}"
    path = _stored_path("attachments", stored_filename)
    if path is None:
        raise ValueError("Could not create a safe attachment filename.")
    try:
        prepared.upload.seek(0)
        with path.open("xb") as handle:
            for chunk in prepared.upload.chunks():
                handle.write(chunk)
        os.chmod(path, 0o600)
        return Attachment.objects.create(
            book=book,
            original_name=prepared.original_name,
            stored_filename=stored_filename,
            content_type=prepared.content_type,
            size=prepared.size,
        )
    except Exception:
        path.unlink(missing_ok=True)
        raise


def attachment_path(attachment: Attachment) -> Path | None:
    path = _stored_path("attachments", attachment.stored_filename)
    return path if path and path.is_file() else None


def available_attachments(book: Book) -> list[Attachment]:
    return [attachment for attachment in book.attachments.all() if attachment_path(attachment)]


def delete_attachment_file(stored_filename: str) -> None:
    path = _stored_path("attachments", stored_filename)
    if path:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Could not remove an obsolete attachment file: %s", exc)
