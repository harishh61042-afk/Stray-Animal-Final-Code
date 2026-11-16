"""CSV export safety: text a spreadsheet could run as a formula is neutralised, other values keep their meaning."""
from datetime import date, datetime

import pytest

from app.utils.csvsafe import neutralise, safe_cell


# ------------------------------------------------------------------ neutralise
@pytest.mark.parametrize("text", [
    "=SUM(A1:A9)", "+91 90000 10001", "-2+3", "@cmd", "\tindented", "\rreturn", "\nnewline",
    '=cmd|" /C calc"!A0',
])
def test_text_that_starts_like_a_formula_gets_a_leading_apostrophe(text):
    assert neutralise(text) == "'" + text


@pytest.mark.parametrize("text", ["Ravi Kumar", "Bruno (dog)", "5 Park Road", "a=b", "x+y", "", "email@pawconnect.test"])
def test_ordinary_text_is_left_alone(text):
    assert neutralise(text) == text


# ------------------------------------------------------------------ safe_cell
def test_missing_values_become_empty_cells():
    assert safe_cell(None) == ""


def test_booleans_are_written_as_yes_and_no():
    assert safe_cell(True) == "Yes"
    assert safe_cell(False) == "No"


def test_numbers_stay_numbers():  # a negative number must not get an apostrophe
    assert safe_cell(7) == 7
    assert safe_cell(-3) == -3
    assert safe_cell(4.5) == 4.5


def test_a_stored_utc_time_is_written_in_local_time():
    stored = datetime(2026, 11, 15, 4, 30, 59)  # naive UTC, as the database keeps it
    assert safe_cell(stored) == "2026-11-15 10:00"  # India: UTC+05:30
    assert safe_cell(stored, offset_minutes=0) == "2026-11-15 04:30"
    assert safe_cell(datetime(2026, 11, 15, 20, 0), offset_minutes=330) == "2026-11-16 01:30"  # next day


def test_a_plain_date_is_written_as_iso_text():
    assert safe_cell(date(2026, 11, 15)) == "2026-11-15"


def test_text_is_neutralised_inside_safe_cell():
    assert safe_cell("=1+1") == "'=1+1"
    assert safe_cell("+91 90000 10001") == "'+91 90000 10001"
    assert safe_cell("Happy Tails") == "Happy Tails"


def test_other_objects_are_written_as_text():
    assert safe_cell(object.__name__) == "object"
    assert safe_cell(["a", "b"]) == "['a', 'b']"
