"""Blueprint registry. Each module listed here defines ``bp`` (a Flask Blueprint)."""
import importlib

BLUEPRINT_MODULES = (
    "public", "auth", "account", "notifications", "files", "dashboard",
    "reports", "rescue", "maps", "animals", "medical", "shelters",
    "adoption", "volunteers", "tasks", "admin",
)


def register_blueprints(app):
    for name in BLUEPRINT_MODULES:
        module = importlib.import_module(f"app.routes.{name}")
        app.register_blueprint(module.bp)
