"""Pure-Python validation helpers (no Flask / database needed)."""
import re
import uuid

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")
PHONE_ALLOWED_RE = re.compile(r"^[0-9+\-()\s]+$")


def is_valid_email(value):
    return bool(value) and len(value) <= 120 and bool(EMAIL_RE.match(value.strip()))


def normalize_email(value):
    return (value or "").strip().lower()


def is_valid_phone(value):
    """Accept 7-15 digits with optional ``+``, spaces, dashes and brackets."""
    if not value or not PHONE_ALLOWED_RE.match(value.strip()):
        return False
    digits = re.sub(r"\D", "", value)
    return 7 <= len(digits) <= 15


def is_valid_latitude(value):
    try:
        return -90.0 <= float(value) <= 90.0
    except (TypeError, ValueError):
        return False


def is_valid_longitude(value):
    try:
        return -180.0 <= float(value) <= 180.0
    except (TypeError, ValueError):
        return False


def parse_coordinates(lat, lng):
    """Return ``(lat, lng)`` as floats, ``(None, None)`` when both are empty.

    Raises ``ValueError`` when only one is given or a value is out of range.
    """
    lat = (str(lat).strip() if lat is not None else "")
    lng = (str(lng).strip() if lng is not None else "")
    if not lat and not lng:
        return None, None
    if not lat or not lng:
        raise ValueError("Please provide both latitude and longitude.")
    if not is_valid_latitude(lat):
        raise ValueError("Latitude must be a number between -90 and 90.")
    if not is_valid_longitude(lng):
        raise ValueError("Longitude must be a number between -180 and 180.")
    return float(lat), float(lng)


def password_problems(password):
    """Return a list of reasons the password is too weak (empty list = OK)."""
    problems = []
    password = password or ""
    if len(password) < 8:
        problems.append("Password must be at least 8 characters long.")
    if not re.search(r"[A-Za-z]", password):
        problems.append("Password must contain at least one letter.")
    if not re.search(r"\d", password):
        problems.append("Password must contain at least one number.")
    if len(password) > 128:
        problems.append("Password must be at most 128 characters long.")
    return problems


# --------------------------------------------------------------------- files
def detect_file_type(header):
    """Identify a file from its first bytes. Returns an extension or ``None``.

    Checking the real content (not just the file name) stops someone
    uploading a script renamed to ``.jpg``.
    """
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "webp"
    if header.startswith(b"%PDF-"):
        return "pdf"
    return None


def file_extension(filename):
    if not filename or "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].lower()


def unique_filename(extension):
    """Random, collision-proof file name such as ``3f9c...e1.jpg``."""
    extension = extension.lower().lstrip(".")
    if extension == "jpeg":
        extension = "jpg"
    return f"{uuid.uuid4().hex}.{extension}"


def format_code(prefix, year, number):
    """``format_code('RPT', 2026, 42) -> 'RPT-2026-00042'``."""
    return f"{prefix}-{year}-{number:05d}"


def clean_text(value, max_length=None):
    """Strip whitespace; return ``None`` for empty input; optionally clip."""
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    if max_length:
        value = value[:max_length]
    return value
