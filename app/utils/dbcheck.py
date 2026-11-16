"""Plain-English help for the most common MySQL start-up problems.

Used by ``init_db.py`` and ``run.py`` on the console. The web pages never show database details to visitors.
"""
import os

_HINTS = {
    1045: "MySQL did not accept the user name or password. Check DB_USER and DB_PASSWORD in your .env file "
          "(they must be the ones you use to sign in to MySQL).",
    1044: "This MySQL user is not allowed to use the database. Use a user with enough rights (for example root), "
          "or create the database yourself and grant the user access to it.",
    1049: "The database does not exist yet. Run:  python init_db.py",
    1130: "MySQL does not allow connections from this computer for that user.",
    1142: "This MySQL user is not allowed to create tables. Use a user with more rights (for example root).",
    1227: "This MySQL user is not allowed to create the database. Use a user with more rights (for example root).",
    2002: "Cannot reach the MySQL server. Make sure MySQL is running (on Windows: open Services and start the MySQL service).",
    2003: "Cannot reach the MySQL server. Make sure MySQL is running (on Windows: open Services and start the MySQL service).",
    2005: "The MySQL host name in DB_HOST is not known. Use 127.0.0.1 when MySQL runs on this computer.",
    2013: "The connection to MySQL was lost. Make sure MySQL is running and try again.",
}


def mysql_error_code(error):
    """The numeric MySQL error code inside a SQLAlchemy / PyMySQL exception (or ``None``)."""
    original = getattr(error, "orig", None) or error
    arguments = getattr(original, "args", ())
    if arguments and isinstance(arguments[0], int):
        return arguments[0]
    return None


def explain(error):
    """A short, helpful explanation of a database error (the password is never printed)."""
    code = mysql_error_code(error)
    where = f"{os.environ.get('DB_HOST', '127.0.0.1')}:{os.environ.get('DB_PORT', '3306')}"
    user = os.environ.get("DB_USER", "root")
    name = os.environ.get("DB_NAME", "pawconnect_db")
    hint = _HINTS.get(code)
    if hint is None:
        hint = "Check the DB_* values in your .env file and that the MySQL server is running."
    detail = f" (MySQL error {code})" if code else ""
    return f"Could not use the database{detail}.\n  Server: {where}   User: {user}   Database: {name}\n  {hint}"
