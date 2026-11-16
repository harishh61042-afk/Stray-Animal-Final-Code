"""Application configuration for PawConnect.

All secrets and database credentials come from environment variables
(normally loaded from the ``.env`` file). Nothing sensitive is hard-coded.
"""
import os
from datetime import timedelta
from urllib.parse import quote_plus

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def build_database_uri():
    """Build the SQLAlchemy URI for MySQL from the DB_* environment variables.

    ``DATABASE_URL`` (a complete SQLAlchemy URI) wins when it is set.
    The user name and password are URL-quoted so special characters such as
    ``@`` or ``#`` in a password cannot break the connection string.
    """
    full_uri = os.environ.get("DATABASE_URL")
    if full_uri:
        return full_uri
    user = quote_plus(os.environ.get("DB_USER", "root"))
    password = quote_plus(os.environ.get("DB_PASSWORD", ""))
    host = os.environ.get("DB_HOST", "127.0.0.1")
    port = os.environ.get("DB_PORT", "3306")
    name = os.environ.get("DB_NAME", "pawconnect_db")
    credentials = f"{user}:{password}" if password else user
    return f"mysql+pymysql://{credentials}@{host}:{port}/{name}?charset=utf8mb4"


class Config:
    """Settings shared by every environment."""

    APP_NAME = "PawConnect"
    # A missing SECRET_KEY is tolerated only in development (see DevelopmentConfig).
    SECRET_KEY = os.environ.get("SECRET_KEY")

    SQLALCHEMY_DATABASE_URI = build_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}

    # Sessions / cookies
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", False)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.environ.get("SESSION_HOURS", "8")))
    REMEMBER_COOKIE_DURATION = timedelta(days=7)
    REMEMBER_COOKIE_HTTPONLY = True

    # CSRF (Flask-WTF)
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 60 * 60 * 8

    # Uploads
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER") or os.path.join(BASE_DIR, "uploads")
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", "8")) * 1024 * 1024
    MAX_IMAGES_PER_UPLOAD = 6

    # Display / behaviour
    DISPLAY_UTC_OFFSET_MINUTES = int(os.environ.get("DISPLAY_UTC_OFFSET_MINUTES", "330"))  # IST
    PER_PAGE = 10
    NOTIFICATION_POLL_SECONDS = 30
    USE_LOCAL_VENDOR = _env_bool("USE_LOCAL_VENDOR", False)

    # Security hardening
    MAX_FAILED_LOGINS = 5
    LOCKOUT_MINUTES = 15
    PASSWORD_HASH_METHOD = "pbkdf2:sha256"

    # Default administrator created by init_db.py (development values only!)
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@pawconnect.test")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@12345")
    ADMIN_NAME = os.environ.get("ADMIN_NAME", "PawConnect Administrator")

    # Contact details shown in the footer / contact page
    CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "help@pawconnect.test")
    CONTACT_PHONE = os.environ.get("CONTACT_PHONE", "+91 90000 00000")
    CONTACT_ADDRESS = os.environ.get("CONTACT_ADDRESS", "PawConnect Rescue Desk, India")

    DEBUG = False
    TESTING = False


class DevelopmentConfig(Config):
    DEBUG = _env_bool("FLASK_DEBUG", False)
    SECRET_KEY = Config.SECRET_KEY or "dev-only-secret-key-change-me"


class ProductionConfig(Config):
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", True)

    @classmethod
    def validate(cls):
        if not cls.SECRET_KEY:
            raise RuntimeError("SECRET_KEY must be set in the environment for production use.")


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = "testing-secret-key"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False
    PASSWORD_HASH_METHOD = "pbkdf2:sha256:1000"  # fast hashing keeps the test suite quick
    MAX_FAILED_LOGINS = 3
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads", "_test")


CONFIG_BY_NAME = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config(name=None):
    name = (name or os.environ.get("FLASK_CONFIG", "development")).lower()
    return CONFIG_BY_NAME.get(name, DevelopmentConfig)
