"""PawConnect application package.

Heavy imports happen inside ``create_app`` so that pure-Python helpers such as
``app.constants`` and ``app.services.rules`` can be imported (and unit-tested)
without Flask extensions being loaded.
"""


def create_app(config_name=None):
    import os

    from flask import Flask, render_template

    from config import get_config

    config_class = get_config(config_name)
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_class)
    if hasattr(config_class, "validate"):
        config_class.validate()

    from app.extensions import csrf, db, login_manager

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # SQLite (used by the automated tests) needs foreign keys switched on.
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        from sqlalchemy import event
        from sqlalchemy.engine import Engine

        @event.listens_for(Engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _record):  # pragma: no cover
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    # Import models so SQLAlchemy knows every table.
    from app import models  # noqa: F401

    @login_manager.user_loader
    def load_user(user_id):
        try:
            user = db.session.get(models.User, int(user_id))
        except (TypeError, ValueError):
            return None
        # A suspended or deactivated account loses access at once, even in a browser that is still signed in.
        return user if user is not None and user.is_active else None

    # Upload folders
    for category in ("animal_reports", "animals", "medical_documents", "verification_documents"):
        os.makedirs(os.path.join(app.config["UPLOAD_FOLDER"], category), exist_ok=True)

    from app.routes import register_blueprints
    from app.template_utils import register_template_utils

    register_blueprints(app)
    register_template_utils(app)
    register_error_handlers(app, render_template)
    register_security_headers(app)
    register_cli(app)
    return app


def register_security_headers(app):
    """Cheap protections that never get in the way: no content-type guessing, no framing by other sites."""

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response


def register_error_handlers(app, render_template):
    from app.extensions import db

    def _page(code, title, message):
        try:
            return render_template("errors/error.html", code=code, title=title, message=message), code
        except Exception:  # noqa: BLE001 - the error page itself must never fail (e.g. database is down)
            from markupsafe import escape

            html = (
                f"<!doctype html><meta charset='utf-8'><title>{escape(title)}</title>"
                "<body style='font-family:system-ui,sans-serif;max-width:520px;margin:14vh auto;padding:0 20px'>"
                f"<h1>{code} - {escape(title)}</h1><p>{escape(message)}</p><p><a href='/'>Back to home</a></p></body>"
            )
            return html, code

    @app.errorhandler(400)
    def bad_request(_error):
        return _page(400, "Bad request", "The request could not be understood. Please go back and try again.")

    @app.errorhandler(403)
    def forbidden(_error):
        return _page(403, "Access denied", "You do not have permission to open this page.")

    @app.errorhandler(404)
    def not_found(_error):
        return _page(404, "Page not found", "The page you are looking for does not exist or was moved.")

    @app.errorhandler(413)
    def too_large(_error):
        return _page(413, "File too large", "The uploaded file is larger than the allowed limit.")

    @app.errorhandler(405)
    def method_not_allowed(_error):
        return _page(405, "Action not allowed", "That action is not available on this page.")

    @app.errorhandler(500)
    def server_error(_error):
        try:
            db.session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return _page(500, "Something went wrong", "An unexpected error occurred. Nothing was saved. Please try again.")

    try:  # CSRF failures get a friendly page too
        from flask_wtf.csrf import CSRFError

        @app.errorhandler(CSRFError)
        def csrf_error(_error):
            return _page(400, "Session expired", "Your form session expired. Please reload the page and try again.")
    except ImportError:  # pragma: no cover
        pass


def register_cli(app):
    import click

    @app.cli.command("send-vaccination-reminders")
    def send_vaccination_reminders():
        """Create notifications for vaccinations that are due soon."""
        from app.services import medical_service

        count = medical_service.send_vaccination_due_notifications()
        click.echo(f"Created {count} vaccination reminder notification(s).")
