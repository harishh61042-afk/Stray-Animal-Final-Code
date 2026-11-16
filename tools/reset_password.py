#!/usr/bin/env python3
"""Set a new password for one account from the command line.

Use it when nobody can sign in any more - for example when the only administrator forgot the password.

    python tools/reset_password.py                          asks for the e-mail address and the new password
    python tools/reset_password.py admin@pawconnect.test    asks only for the new password

The new password is kept exactly as typed (no forced change), a locked account is unlocked, and the reset is written
to the activity log. A suspended account stays suspended. The MySQL connection comes from the DB_* values in .env,
the same as for the website itself.
"""
import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main(argv):
    try:
        from app import create_app
        from app.extensions import db
        from app.models import User
        from app.services import audit
        from app.services.common import transaction
        from app.utils.dbcheck import explain
        from app.utils.validators import password_problems
    except ImportError as error:
        print(f"A required Python package is missing ({error}).")
        print("Activate the virtual environment, then run:  pip install -r requirements.txt")
        return 1

    email = (argv[0] if argv else input("E-mail address of the account: ")).strip().lower()
    app = create_app()
    with app.app_context():
        try:
            user = User.query.filter(db.func.lower(User.email) == email).first()
        except Exception as error:  # noqa: BLE001 - any database problem is explained in plain words
            print("The database could not be reached.\n  " + explain(error))
            return 1
        if user is None:
            print(f"There is no account with the e-mail address {email}.")
            return 1

        print(f"Account: {user.full_name} ({user.role_label}, {user.status})")
        password = getpass.getpass("New password: ")
        if password != getpass.getpass("Type it again: "):
            print("The two passwords are not the same. Nothing was changed.")
            return 1
        problems = password_problems(password)
        if problems:
            print("That password is too weak:\n  " + "\n  ".join(problems))
            return 1

        with transaction():
            user.set_password(password)
            user.must_change_password = False
            user.failed_login_attempts = 0
            user.locked_until = None
            audit.log_action("password_reset_by_command", "User", user.id, user.email)
    print("Done. The password was changed and the account is unlocked.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
