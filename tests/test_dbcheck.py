"""The console help for MySQL start-up problems: it explains the common errors and never prints the password."""
import pytest

from app.utils import dbcheck


class FakeDriverError(Exception):
    """Looks like a PyMySQL error: the first argument is the MySQL error number."""


class FakeWrapper(Exception):
    """Looks like a SQLAlchemy error that wraps the driver error in ``.orig``."""

    def __init__(self, original):
        super().__init__("wrapped")
        self.orig = original


@pytest.fixture(autouse=True)
def database_settings(monkeypatch):
    monkeypatch.setenv("DB_HOST", "db.example.test")
    monkeypatch.setenv("DB_PORT", "3307")
    monkeypatch.setenv("DB_USER", "paw_user")
    monkeypatch.setenv("DB_NAME", "paw_db")
    monkeypatch.setenv("DB_PASSWORD", "TopSecret-Do-Not-Print")


# ------------------------------------------------------------------ finding the MySQL error number
def test_the_error_number_is_found_in_a_driver_error():
    assert dbcheck.mysql_error_code(FakeDriverError(1045, "Access denied")) == 1045


def test_the_error_number_is_found_inside_a_wrapped_error():
    assert dbcheck.mysql_error_code(FakeWrapper(FakeDriverError(2003, "Can't connect"))) == 2003


@pytest.mark.parametrize("error", [ValueError("plain message"), FakeDriverError("text first", 5), Exception()])
def test_other_errors_have_no_number(error):
    assert dbcheck.mysql_error_code(error) is None


# ------------------------------------------------------------------ the explanation
def test_wrong_password_is_explained():
    text = dbcheck.explain(FakeWrapper(FakeDriverError(1045, "Access denied")))
    assert "MySQL error 1045" in text
    assert "DB_PASSWORD" in text and "DB_USER" in text


def test_server_not_running_is_explained():
    for number in (2002, 2003):
        text = dbcheck.explain(FakeDriverError(number, "Can't connect"))
        assert "MySQL is running" in text and "Services" in text


def test_missing_database_points_to_init_db():
    assert "python init_db.py" in dbcheck.explain(FakeDriverError(1049, "Unknown database"))


def test_the_explanation_names_the_server_user_and_database_but_never_the_password():
    text = dbcheck.explain(FakeDriverError(1045, "Access denied"))
    assert "db.example.test:3307" in text
    assert "paw_user" in text and "paw_db" in text
    assert "TopSecret-Do-Not-Print" not in text


def test_an_unknown_problem_still_gets_general_advice():
    text = dbcheck.explain(ValueError("something odd"))
    assert "MySQL error" not in text
    assert "DB_* values" in text


def test_defaults_are_used_when_nothing_is_set(monkeypatch):
    for name in ("DB_HOST", "DB_PORT", "DB_USER", "DB_NAME"):
        monkeypatch.delenv(name)
    text = dbcheck.explain(FakeDriverError(1049, "Unknown database"))
    assert "127.0.0.1:3306" in text and "root" in text and "pawconnect_db" in text
