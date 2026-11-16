#!/usr/bin/env python3
"""Create the PawConnect database, its tables and the default administrator.

    python init_db.py             create whatever is missing (safe to run again and again)
    python init_db.py --seed      ...and add sample accounts and demo data (development only)
    python init_db.py --reset     DELETE every PawConnect table first, then start again (asks first)

The MySQL connection comes from the DB_* values in the .env file (see .env.example).
"""
import argparse
import re
import sys

DEFAULT_ADMIN_PASSWORD = "Admin@12345"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Create the PawConnect database, tables and default administrator.")
    parser.add_argument("--seed", action="store_true",
                        help="also add sample accounts and demo data (for development and demonstrations only)")
    parser.add_argument("--reset", action="store_true", help="delete every PawConnect table first (all data is lost)")
    parser.add_argument("--yes", action="store_true", help="do not ask for confirmation with --reset")
    parser.add_argument("--skip-create-database", action="store_true",
                        help="do not run CREATE DATABASE (use it when the database already exists)")
    return parser.parse_args(argv)


def create_database_if_needed(uri):
    """Run ``CREATE DATABASE IF NOT EXISTS`` on a MySQL server. Other databases (SQLite) need nothing."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    url = make_url(uri)
    if not url.drivername.startswith("mysql"):
        return
    name = url.database or ""
    if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", name):
        raise SystemExit("DB_NAME may only contain letters, digits and underscores (at most 64 characters).")
    engine = create_engine(url.set(database=None))
    try:
        with engine.connect() as connection:
            connection.execute(text(f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
            connection.commit()
    finally:
        engine.dispose()


def ensure_admin(app):
    """Create the default administrator when there is none. Returns the account and whether it is new."""
    from app import constants as C
    from app.extensions import db
    from app.models import User
    from app.utils.validators import normalize_email

    existing = User.query.filter_by(role=C.ROLE_ADMIN).order_by(User.id).first()
    if existing is not None:
        return existing, False
    email = normalize_email(app.config["ADMIN_EMAIL"])
    password = app.config["ADMIN_PASSWORD"]
    if len(password) < 8:
        raise SystemExit("ADMIN_PASSWORD in .env must have at least 8 characters.")
    if User.query.filter_by(email=email).first() is not None:
        raise SystemExit(f"{email} is already used by a non-administrator account. Change ADMIN_EMAIL in .env.")
    admin = User(email=email, full_name=app.config["ADMIN_NAME"], role=C.ROLE_ADMIN, status=C.ACCOUNT_ACTIVE,
                 verification_status=C.VERIFY_NOT_REQUIRED, must_change_password=False)
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    return admin, True


def main(argv=None):
    args = parse_args(argv)
    try:
        from sqlalchemy.exc import SQLAlchemyError

        from app import create_app
        from app.extensions import db
        from app.utils.dbcheck import explain
    except ImportError as error:
        print(f"A required Python package is missing ({error}).")
        print("Activate the virtual environment, then run:  pip install -r requirements.txt")
        return 1

    app = create_app()
    if args.reset and not args.yes:
        answer = input("This DELETES every PawConnect table and all of its data. Type YES to continue: ")
        if answer.strip() != "YES":
            print("Nothing was changed.")
            return 1

    try:
        if not args.skip_create_database:
            create_database_if_needed(app.config["SQLALCHEMY_DATABASE_URI"])
        with app.app_context():
            if args.reset:
                db.drop_all()
                print("All PawConnect tables were deleted.")
            db.create_all()
            table_count = len(db.metadata.tables)
            admin, created = ensure_admin(app)
            sample_accounts = []
            if args.seed:
                from database.seed_data import SAMPLE_PASSWORD, seed

                sample_accounts = seed()
    except SQLAlchemyError as error:
        print(explain(error))
        return 1

    print(f"The database is ready ({table_count} tables).")
    if created:
        using_default = app.config["ADMIN_PASSWORD"] == DEFAULT_ADMIN_PASSWORD
        print("\nDefault administrator created - DEVELOPMENT CREDENTIALS, change the password after signing in:")
        print(f"    E-mail:    {admin.email}")
        print(f"    Password:  {DEFAULT_ADMIN_PASSWORD if using_default else '(the ADMIN_PASSWORD from your .env file)'}")
    else:
        print(f"The administrator account already exists ({admin.email}); it was not changed.")
    if args.seed:
        if sample_accounts:
            print(f"\nSample accounts - DEVELOPMENT ONLY, shared password: {SAMPLE_PASSWORD}")
            for role, email, name in sample_accounts:
                print(f"    {role:<13} {email:<34} {name}")
        else:
            print("\nSample data was already present, so nothing was added.")
    print("\nNext step:  python run.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
