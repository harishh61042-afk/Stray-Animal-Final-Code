"""Small helpers shared by every service module."""
from contextlib import contextmanager

from flask import url_for

from app.extensions import db


class ServiceError(Exception):
    """A business rule was broken. The message is safe to show to the user."""


@contextmanager
def transaction():
    """Commit everything inside the ``with`` block or roll everything back.

    Services that change several tables (e.g. completing an adoption) wrap the
    work in this so the database never ends up half-updated.
    """
    try:
        yield db.session
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def link_for(endpoint, **values):
    """``url_for`` that returns ``None`` outside a request instead of raising.

    Used for notification links, because notifications can also be created from
    scripts (seed data, CLI) where no request exists.
    """
    try:
        return url_for(endpoint, **values)
    except Exception:  # noqa: BLE001 - deliberately forgiving
        return None


def like_pattern(text):
    """``%text%`` for a case-insensitive "contains" search, with LIKE wildcards in ``text`` escaped.

    Use it as ``column.ilike(like_pattern(q), escape="\\\\")``.
    """
    text = (text or "").strip()
    for char in ("\\", "%", "_"):
        text = text.replace(char, "\\" + char)
    return f"%{text}%"


def require(condition, message):
    """Raise :class:`ServiceError` with ``message`` unless ``condition`` holds."""
    if not condition:
        raise ServiceError(message)
