"""Start PawConnect on your own computer:   python run.py

Open http://127.0.0.1:5000/ in a browser afterwards. Stop the server with Ctrl+C.
"""
import os
import sys


def database_problem(app):
    """Return a plain-English description of what is wrong with the database, or ``None`` when it is ready."""
    from sqlalchemy import inspect
    from sqlalchemy.exc import SQLAlchemyError

    from app.extensions import db
    from app.utils.dbcheck import explain

    with app.app_context():
        try:
            tables = inspect(db.engine).get_table_names()
        except SQLAlchemyError as error:
            return explain(error)
    if "users" not in tables:
        return "The database has no PawConnect tables yet.\n  Run:  python init_db.py"
    return None


def main():
    try:
        from app import create_app
    except ImportError as error:
        print(f"A required Python package is missing ({error}).")
        print("Activate the virtual environment, then run:  pip install -r requirements.txt")
        return 1

    app = create_app()
    if "--skip-db-check" not in sys.argv:
        problem = database_problem(app)
        if problem:
            print("PawConnect cannot start yet.\n  " + problem)
            return 1

    host = os.environ.get("FLASK_RUN_HOST", "127.0.0.1")
    port = int(os.environ.get("FLASK_RUN_PORT", "5000"))
    print(f"PawConnect is running at http://{host}:{port}/   (press Ctrl+C to stop)")
    app.run(host=host, port=port, debug=bool(app.config.get("DEBUG")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
