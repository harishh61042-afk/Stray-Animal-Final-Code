"""Administrator pages: accounts, verifications, analytics, CSV exports, activity log, contact inbox and notices.

Every route needs the administrator role (``roles_required(C.ROLE_ADMIN)``); the role is read from the signed-in
account, never from the request. All changes are POST requests with a CSRF token.
"""
from flask import Blueprint, Response, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import constants as C
from app.extensions import db
from app.forms.admin import AdminUserForm, ContactStatusForm, NotificationForm, UserStatusForm, VerificationForm
from app.forms.animals import ConfirmForm
from app.models import ContactMessage, User
from app.services import admin_service, reporting, user_service
from app.services.common import ServiceError
from app.utils.permissions import redirect_back, roles_required

bp = Blueprint("admin", __name__, url_prefix="/admin")

AUDIT_PER_PAGE = 25


def _page():
    return request.args.get("page", 1, type=int)


# ------------------------------------------------------------------ accounts
@bp.route("/users")
@roles_required(C.ROLE_ADMIN)
def users():
    q = request.args.get("q", "").strip()
    role = request.args.get("role", "")
    status = request.args.get("status", "")
    verification = request.args.get("verification", "")
    pagination = admin_service.user_query(q, role, status, verification).paginate(
        page=_page(), per_page=current_app.config["PER_PAGE"], error_out=False)
    return render_template("admin/users.html", pagination=pagination, counts=admin_service.user_counts(),
                           q=q, role=role, status=status, verification=verification)


@bp.route("/users/new", methods=["GET", "POST"])
@roles_required(C.ROLE_ADMIN)
def user_create():
    form = AdminUserForm()
    if request.method == "GET" and request.args.get("role") in C.ALL_ROLES:
        form.role.data = request.args["role"]
    if form.validate_on_submit():
        try:
            user, temporary = user_service.admin_create_user(dict(form.data), current_user)
        except ServiceError as error:
            flash(str(error), "danger")
        else:
            if temporary:
                flash(f"Account created for {user.full_name}. Temporary password (shown only now, please note it): "
                      f"{temporary}", "success")
            else:
                flash(f"Account created for {user.full_name}.", "success")
            return redirect(url_for("admin.user_detail", user_id=user.id))
    return render_template("admin/user_form.html", form=form)


@bp.route("/users/<int:user_id>")
@roles_required(C.ROLE_ADMIN)
def user_detail(user_id):
    account = db.get_or_404(User, user_id)
    return render_template(
        "admin/user_detail.html", account=account, profile=account.role_profile,
        profile_rows=admin_service.profile_rows(account), summary=admin_service.user_summary(account),
        activity=admin_service.describe_entries(admin_service.user_activity(account)),
        status_form=UserStatusForm(data={"status": account.status}), is_self=account.id == current_user.id)


@bp.route("/users/<int:user_id>/status", methods=["POST"])
@roles_required(C.ROLE_ADMIN)
def set_status(user_id):
    account = db.get_or_404(User, user_id)
    form = UserStatusForm()
    if form.validate_on_submit():
        try:
            user_service.set_account_status(account, form.status.data, current_user, form.reason.data)
            flash(f"{account.full_name}'s account is now {form.status.data}.", "success")
        except ServiceError as error:
            flash(str(error), "danger")
    else:
        flash("That request was not valid. Please try again.", "danger")
    return redirect_back(url_for("admin.user_detail", user_id=account.id))


@bp.route("/users/<int:user_id>/reset-password", methods=["POST"])
@roles_required(C.ROLE_ADMIN)
def reset_password(user_id):
    account = db.get_or_404(User, user_id)
    if not ConfirmForm().validate_on_submit():
        flash("That request was not valid. Please try again.", "danger")
    elif account.id == current_user.id:
        flash("Use \"Change password\" in your account menu to change your own password.", "warning")
    else:
        try:
            temporary = user_service.admin_reset_password(account, current_user)
        except ServiceError as error:
            flash(str(error), "danger")
        else:
            flash(f"Temporary password for {account.full_name} (shown only now, please note it): {temporary}. "
                  "They must choose a new password when they sign in.", "success")
    return redirect(url_for("admin.user_detail", user_id=account.id))


# -------------------------------------------------------------- verification
@bp.route("/verifications")
@roles_required(C.ROLE_ADMIN)
def verifications():
    status = request.args.get("status", C.VERIFY_PENDING)
    role = request.args.get("role", "")
    q = request.args.get("q", "").strip()
    pagination = admin_service.verification_query(status, role, q).paginate(
        page=_page(), per_page=current_app.config["PER_PAGE"], error_out=False)
    cards = [{"user": u, "profile": u.role_profile, "rows": admin_service.profile_rows(u)} for u in pagination.items]
    return render_template("admin/verifications.html", pagination=pagination, cards=cards,
                           counts=admin_service.verification_counts(), status=status, role=role, q=q)


@bp.route("/users/<int:user_id>/verify", methods=["POST"])
@roles_required(C.ROLE_ADMIN)
def verify(user_id):
    account = db.get_or_404(User, user_id)
    form = VerificationForm()
    if form.validate_on_submit():
        approve = form.decision.data == "approve"
        try:
            user_service.verify_account(account, approve, current_user, form.note.data)
            flash(f"{account.full_name} was {'verified' if approve else 'not approved'}. They have been notified.",
                  "success" if approve else "info")
        except ServiceError as error:
            flash(str(error), "danger")
    else:
        flash("Please choose approve or reject.", "danger")
    return redirect_back(url_for("admin.verifications"))


# ------------------------------------------------------- analytics and export
@bp.route("/reports")
@roles_required(C.ROLE_ADMIN)
def reports():
    start, end = reporting.parse_range(request.args)
    return render_template("admin/reports.html", data=reporting.analytics(start, end), presets=reporting.presets(),
                           datasets=admin_service.EXPORT_DATASETS, start=start, end=end)


@bp.route("/export/<dataset>.csv")
@roles_required(C.ROLE_ADMIN)
def export_csv(dataset):
    if dataset not in admin_service.DATASET_KEYS:
        abort(404)
    start, end = reporting.parse_dates(request.args)
    text, count = admin_service.export_csv(dataset, start, end)
    admin_service.record_export(dataset, count, current_user, start, end)
    response = Response(text.encode("utf-8"), mimetype="text/csv")
    response.headers["Content-Disposition"] = f'attachment; filename="{admin_service.export_filename(dataset)}"'
    response.headers["Cache-Control"] = "no-store"
    return response


# ------------------------------------------------------------------ activity
@bp.route("/audit-log")
@roles_required(C.ROLE_ADMIN)
def audit_log():
    q = request.args.get("q", "").strip()
    action = request.args.get("action", "")
    kind = request.args.get("kind", "")
    user_id = request.args.get("user", type=int)
    pagination = admin_service.audit_query(q, action, kind, user_id).paginate(
        page=_page(), per_page=AUDIT_PER_PAGE, error_out=False)
    person = db.session.get(User, user_id) if user_id else None
    return render_template(
        "admin/audit_log.html", pagination=pagination, entries=admin_service.describe_entries(pagination.items),
        actions=admin_service.audit_action_choices(), kinds=admin_service.KIND_CHOICES, q=q, action=action, kind=kind,
        person=person)


# -------------------------------------------------------------------- inbox
@bp.route("/messages")
@roles_required(C.ROLE_ADMIN)
def messages():
    status = request.args.get("status", C.CONTACT_NEW)
    q = request.args.get("q", "").strip()
    pagination = admin_service.message_query(status, q).paginate(
        page=_page(), per_page=current_app.config["PER_PAGE"], error_out=False)
    return render_template("admin/messages.html", pagination=pagination, counts=admin_service.message_counts(),
                           status=status, q=q)


@bp.route("/messages/<int:message_id>/status", methods=["POST"])
@roles_required(C.ROLE_ADMIN)
def message_status(message_id):
    message = db.get_or_404(ContactMessage, message_id)
    form = ContactStatusForm()
    if form.validate_on_submit():
        try:
            admin_service.set_message_status(message, form.status.data, current_user)
            flash("The message was marked as " + form.status.data.lower() + ".", "success")
        except ServiceError as error:
            flash(str(error), "danger")
    else:
        flash("That request was not valid. Please try again.", "danger")
    return redirect_back(url_for("admin.messages"))


# ------------------------------------------------------------------- notices
@bp.route("/notifications/send", methods=["GET", "POST"])
@roles_required(C.ROLE_ADMIN)
def send_notification():
    form = NotificationForm()
    if form.validate_on_submit():
        try:
            count = admin_service.send_broadcast(
                current_user, form.target.data, form.title.data, form.message.data,
                role=form.role.data, email=form.user_email.data, link=form.link.data)
        except ServiceError as error:
            flash(str(error), "danger")
        else:
            flash(f"Your notice was sent to {count} {'person' if count == 1 else 'people'}. "
                  "It appears in their notifications.", "success")
            return redirect(url_for("admin.send_notification"))
    return render_template("admin/send_notification.html", form=form,
                           recent=admin_service.describe_entries(admin_service.recent_broadcasts()))
