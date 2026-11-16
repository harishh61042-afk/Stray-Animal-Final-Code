"""Time helpers. Timestamps are stored as naive UTC and shown in local time."""
from datetime import date, datetime, timedelta, timezone

DEFAULT_OFFSET_MINUTES = 330  # India Standard Time (no daylight saving)


def utcnow():
    """Current UTC time as a naive datetime (what the database stores)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_local(value, offset_minutes=DEFAULT_OFFSET_MINUTES):
    """Shift a naive-UTC datetime to local display time."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value + timedelta(minutes=offset_minutes)
    return value


def from_local(value, offset_minutes=DEFAULT_OFFSET_MINUTES):
    """Opposite of :func:`to_local`: a naive local datetime (e.g. typed into a ``datetime-local`` input) -> naive UTC."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value - timedelta(minutes=offset_minutes)
    return value


def local_today(offset_minutes=DEFAULT_OFFSET_MINUTES):
    """Today's date in the configured local time zone."""
    return (utcnow() + timedelta(minutes=offset_minutes)).date()


def format_datetime(value, offset_minutes=DEFAULT_OFFSET_MINUTES, fmt="%d %b %Y, %I:%M %p"):
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return to_local(value, offset_minutes).strftime(fmt)
    if isinstance(value, date):
        return value.strftime("%d %b %Y")
    return str(value)


def format_date(value, fmt="%d %b %Y"):
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.strftime(fmt)
    if isinstance(value, date):
        return value.strftime(fmt)
    return str(value)


def time_ago(value, now=None):
    """Human friendly relative time for a naive-UTC datetime ("5 minutes ago")."""
    if value is None:
        return "-"
    now = now or utcnow()
    seconds = int((now - value).total_seconds())
    if seconds < 0:
        return "just now"
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    if days < 30:
        return f"{days} day{'s' if days != 1 else ''} ago"
    months = days // 30
    if months < 12:
        return f"{months} month{'s' if months != 1 else ''} ago"
    years = months // 12
    return f"{years} year{'s' if years != 1 else ''} ago"


def month_start(value, months_back=0):
    """First day of the month ``months_back`` months before ``value``."""
    year, month = value.year, value.month - months_back
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)
