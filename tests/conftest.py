"""Shared pytest fixtures.

Pure tests (test_rules, test_schema_sql, test_csvsafe, test_dbcheck, test_ratelimit) need nothing but Python.
All other tests run the real Flask application against an in-memory SQLite database. They need the packages from
requirements.txt and are skipped, with the reason shown, when those packages are not installed.

Every test gets its own brand-new application and empty database, so tests never influence each other.
"""
import pytest

REQUIRED_PACKAGES = ("sqlalchemy", "flask_sqlalchemy", "flask_login", "flask_wtf", "wtforms")


@pytest.fixture()
def app(tmp_path, monkeypatch):
    for package in REQUIRED_PACKAGES:
        pytest.importorskip(package, reason=f"'{package}' is not installed - run: pip install -r requirements.txt")

    from config import TestingConfig

    # Uploaded test files go to a temporary folder that pytest removes afterwards.
    monkeypatch.setattr(TestingConfig, "UPLOAD_FOLDER", str(tmp_path / "uploads"))

    from app import create_app
    from app.extensions import db
    from app.utils import ratelimit

    ratelimit.track_limiter.reset()
    application = create_app("testing")
    with application.app_context():
        db.create_all()
    yield application
    with application.app_context():
        db.session.remove()
        db.engine.dispose()
    ratelimit.track_limiter.reset()


@pytest.fixture()
def client(app):
    """A browser-like client that keeps its cookies between requests."""
    return app.test_client()
