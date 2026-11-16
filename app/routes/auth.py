"""Sign in, sign out and registration."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from app import constants as C
from app.forms import form_data
from app.forms.auth import SELF_REGISTER_ROLES, LoginForm, RegisterForm, VolunteerRegisterForm
from app.services import user_service
from app.services.common import ServiceError
from app.utils.permissions import is_safe_redirect, login_required

bp = Blueprint("auth", __name__)


def _after_login_url():
    target = request.args.get("next")
    return target if target and is_safe_redirect(target) else url_for("dashboard.index")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    form = LoginForm()
    if form.validate_on_submit():
        try:
            user = user_service.authenticate(form.email.data, form.password.data)
        except ServiceError as error:
            flash(str(error), "danger")
        else:
            login_user(user, remember=bool(form.remember.data))
            flash(f"Welcome back, {user.first_name}!", "success")
            return redirect(_after_login_url())
    return render_template("auth/login.html", form=form, next_url=request.args.get("next", ""))


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("public.home"))


def _registered(user):
    if user.needs_verification:
        flash("Account created. An administrator must verify your details before you get full access. "
              "You can sign in now to follow the status.", "success")
    elif user.role == C.ROLE_VOLUNTEER:
        flash("Thank you for applying! You can sign in now; an administrator will review your application.", "success")
    else:
        flash("Your account has been created. Please sign in.", "success")
    return redirect(url_for("auth.login"))


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    form = RegisterForm()
    if request.method == "GET" and request.args.get("role") in SELF_REGISTER_ROLES:
        form.role.data = request.args["role"]
    if form.validate_on_submit():
        try:
            user = user_service.register_user(form_data(form), {"verification_document": form.verification_document.data})
        except ServiceError as error:
            flash(str(error), "danger")
        else:
            return _registered(user)
    return render_template("auth/register.html", form=form)


@bp.route("/register/volunteer", methods=["GET", "POST"])
def register_volunteer():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    form = VolunteerRegisterForm()
    if form.validate_on_submit():
        data = form_data(form)
        data["role"] = C.ROLE_VOLUNTEER  # decided by this page, never by the browser
        try:
            user = user_service.register_user(data)
        except ServiceError as error:
            flash(str(error), "danger")
        else:
            return _registered(user)
    return render_template("auth/register_volunteer.html", form=form)
