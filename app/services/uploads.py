"""Safe file uploads: extension + real-content checks, unique names, size limit."""
import os

from flask import current_app

from app import constants as C
from app.services.common import ServiceError
from app.utils import validators as V

IMAGE_KINDS = ("png", "jpg", "gif", "webp")
DOCUMENT_KINDS = ("pdf", "png", "jpg")


def upload_root(category):
    if category not in C.UPLOAD_CATEGORIES:
        raise ServiceError("Unknown upload category.")
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], category)
    os.makedirs(path, exist_ok=True)
    return path


def has_file(file_storage):
    """True when the user actually chose a file in a ``<input type=file>``."""
    return bool(file_storage and getattr(file_storage, "filename", ""))


def _check_and_get_extension(file_storage, kind):
    allowed_ext = C.ALLOWED_IMAGE_EXTENSIONS if kind == "image" else C.ALLOWED_DOCUMENT_EXTENSIONS
    allowed_real = IMAGE_KINDS if kind == "image" else DOCUMENT_KINDS
    extension = V.file_extension(file_storage.filename)
    if extension not in allowed_ext:
        raise ServiceError(f"'{file_storage.filename}' is not an allowed file type. Allowed: {', '.join(allowed_ext)}.")
    header = file_storage.stream.read(16)
    file_storage.stream.seek(0)
    real_type = V.detect_file_type(header)
    if real_type not in allowed_real:
        raise ServiceError(f"'{file_storage.filename}' does not look like a valid {kind} file.")
    if {extension, real_type} <= {"jpg", "jpeg"} or extension == real_type:
        return real_type
    raise ServiceError(f"'{file_storage.filename}' has a file extension that does not match its content.")


def save_upload(file_storage, category, kind="image"):
    """Validate and store one uploaded file; returns the stored file name.

    Returns ``None`` when no file was chosen. ``kind`` is ``"image"`` or ``"document"``.
    """
    if not has_file(file_storage):
        return None
    real_type = _check_and_get_extension(file_storage, kind)
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size == 0:
        raise ServiceError("The uploaded file is empty.")
    if size > current_app.config["MAX_CONTENT_LENGTH"]:
        limit_mb = current_app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
        raise ServiceError(f"The file is too large. Maximum size is {limit_mb} MB.")
    filename = V.unique_filename(real_type)
    file_storage.save(os.path.join(upload_root(category), filename))
    return filename


def save_uploads(files, category, kind="image", limit=None):
    """Store several files; empty inputs are skipped. Cleans up if one is invalid."""
    chosen = [f for f in (files or []) if has_file(f)]
    limit = limit or current_app.config.get("MAX_IMAGES_PER_UPLOAD", 6)
    if len(chosen) > limit:
        raise ServiceError(f"You can upload at most {limit} files at once.")
    saved = []
    try:
        for file_storage in chosen:
            saved.append(save_upload(file_storage, category, kind))
    except ServiceError:
        for name in saved:
            delete_upload(category, name)
        raise
    return saved


def resolve_upload(category, filename):
    """Absolute path of a stored file, or ``None`` if missing / unsafe."""
    if category not in C.UPLOAD_CATEGORIES or not filename:
        return None
    if os.path.basename(filename) != filename:  # blocks ../ tricks
        return None
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], category, filename)
    return path if os.path.isfile(path) else None


def delete_upload(category, filename):
    path = resolve_upload(category, filename)
    if path:
        try:
            os.remove(path)
        except OSError:  # pragma: no cover - best effort cleanup
            pass
