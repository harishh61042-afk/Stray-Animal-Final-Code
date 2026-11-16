"""Helpers for writing CSV files that spreadsheet programs open safely.

A cell that starts with ``=``, ``+``, ``-`` or ``@`` can be run as a formula by Excel / LibreOffice / Google Sheets
("CSV injection"). Text coming from users (names, notes, addresses...) is therefore prefixed with an apostrophe
when it starts like a formula. Numbers, dates and booleans are written as they are.
"""
from datetime import date, datetime

from app.utils.timeutil import DEFAULT_OFFSET_MINUTES, to_local

_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r", "\n")


def neutralise(text):
    """Return ``text`` with a leading apostrophe when a spreadsheet could read it as a formula."""
    if text and text[0] in _FORMULA_STARTS:
        return "'" + text
    return text


def safe_cell(value, offset_minutes=DEFAULT_OFFSET_MINUTES):
    """Convert one value to what goes into the CSV file."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, datetime):  # check before ``date``: a datetime is also a date
        return to_local(value, offset_minutes).strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.isoformat()
    return neutralise(str(value))
