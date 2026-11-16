"""Route protection: sign-in, role and verification checks.

Usage (put the route decorator first, then the permission decorator)::

    @bp.route("/admin/users")
    @admin_required
    def users():
        ...

Every check is made on the server, so changing a URL never grants access to
another role's pages.
"""
from functools import wraps
from urllib.parse import urljoin, urlparse

from flask import abort, flash, jsonify, redirect, request, url_for
from flask_login import current_user

from app import constants as C

_PASSWORD_PAGES = ("account.change_password", "auth.logout")


def is_safe_redirect(target):
    """Only allow redirects to pages on this same site (blocks open redirects)."""
    if not target:
        return False
    host = urlparse(request.host_url)
    test = urlparse(urljoin(request.host_url, target))
    return test.scheme in ("http", "https") and host.netloc == test.netloc


def redirect_back(default_url):
    """Redirect to the safe ``next`` value of the submitted form / query string, otherwise to ``default_url``."""
    target = request.form.get("next") or request.args.get("next")
    if target and is_safe_redirect(target):
        return redirect(target)
    return redirect(default_url)


def wants_json():
    """True for requests made by our own JavaScript (fetch / XHR)."""
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _to_login():
    if wants_json():
        return jsonify(error="Please sign in to continue."), 401
    flash("Please sign in to continue.", "warning")
    target = request.full_path if request.query_string else request.path
    return redirect(url_for("auth.login", next=target))


def roles_required(*roles, verified=True):
    """Allow only signed-in users with one of ``roles``.

    * no ``roles``  -> any signed-in user
    * ``verified``  -> rescuers / veterinarians / shelters must be verified by
      an administrator first (otherwise they are sent to the "pending" page)
    """

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return _to_login()
            if current_user.must_change_password and request.endpoint not in _PASSWORD_PAGES:
                flash("Please choose a new password before continuing.", "warning")
                return redirect(url_for("account.change_password"))
            if roles and current_user.role not in roles:
                abort(403)
            if verified and not current_user.is_verified:
                return redirect(url_for("account.pending"))
            return view(*args, **kwargs)

        return wrapped

    return decorator


def login_required(view):
    """Any signed-in user (verified or not)."""
    return roles_required(verified=False)(view)


def admin_required(view):
    return roles_required(C.ROLE_ADMIN)(view)


def approved_volunteer_required(view):
    """Volunteers whose application an administrator has approved."""

    @wraps(view)
    @roles_required(C.ROLE_VOLUNTEER)
    def wrapped(*args, **kwargs):
        if not current_user.is_approved_volunteer:
            flash("Your volunteer application must be approved before you can use this page.", "warning")
            return redirect(url_for("volunteers.my_application"))
        return view(*args, **kwargs)

    return wrapped
