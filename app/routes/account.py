"""Account pages for any signed-in user: profile, password and the "waiting for verification" page."""
from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user

from app import constants as C
from app.forms import form_data
from app.forms.account import ChangePasswordForm, ProfileForm
from app.services import user_service
from app.services.common import ServiceError
from app.utils.permissions import login_required

bp = Blueprint("account", __name__, url_prefix="/account")

PERSONAL_FIELDS = ("full_name", "phone", "date_of_birth", "bio")
ADDRESS_FIELDS = ("address", "city", "state", "pincode")


def _editable_fields(user):
    """Names of the form fields this user may change.

    Shelters keep their address, capacity and location on the shelter page, so only personal details are
    editable here for them (this also stops the personal address overwriting the shelter address).
    """
    if user.role == C.ROLE_SHELTER:
        return set(PERSONAL_FIELDS)
    fields = set(PERSONAL_FIELDS) | set(ADDRESS_FIELDS)
    fields |= set(user_service.ROLE_PROFILE_FIELDS.get(user.role, ()))
    return fields


def _initial_values(user):
    """Current values of the user's details, used to pre-fill the form."""
    values = {"full_name": user.full_name, "phone": user.phone}
    general = user.profile
    if general is not None:
        values.update(address=general.address, city=general.city, state=general.state, pincode=general.pincode,
                      date_of_birth=general.date_of_birth, bio=general.bio)
    role_profile = user.role_profile
    if role_profile is not None and user.role != C.ROLE_SHELTER:
        for name in user_service.ROLE_PROFILE_FIELDS.get(user.role, ()):
            values[name] = getattr(role_profile, name, None)
    return values


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = current_user._get_current_object()
    form = ProfileForm(data=_initial_values(user))
    if form.validate_on_submit():
        allowed = _editable_fields(user)
        payload = {name: value for name, value in form_data(form).items() if name in allowed}
        try:
            user_service.update_profile(user, payload)
            flash("Your profile has been updated.", "success")
            return redirect(url_for("account.profile"))
        except ServiceError as error:
            flash(str(error), "danger")
    return render_template("account/profile.html", form=form, role_profile=user.role_profile,
                           editable=_editable_fields(user))


@bp.route("/password", methods=["GET", "POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        try:
            user_service.change_password(current_user._get_current_object(), form.current_password.data,
                                         form.new_password.data)
            flash("Your password has been changed.", "success")
            return redirect(url_for("dashboard.index"))
        except ServiceError as error:
            flash(str(error), "danger")
    return render_template("account/change_password.html", form=form)


@bp.route("/pending")
@login_required
def pending():
    """Shown to rescuers, veterinarians and shelters until an administrator verifies them."""
    if not current_user.needs_verification or current_user.is_verified:
        return redirect(url_for("dashboard.index"))
    return render_template("account/pending.html", role_profile=current_user.role_profile)
