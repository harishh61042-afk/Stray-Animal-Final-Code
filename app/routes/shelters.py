"""Shelters: public directory and pages, shelter profile, admissions and the administrator's list."""
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import constants as C
from app.extensions import db
from app.forms import form_data
from app.forms.shelters import ShelterProfileForm
from app.models import Animal, ShelterAdmission, ShelterProfile
from app.services import animal_service, shelter_service
from app.services.common import ServiceError
from app.utils.permissions import roles_required

bp = Blueprint("shelters", __name__, url_prefix="/shelters")

ADMISSION_STATES = ("current", "past", "all")


def _actor():
    return current_user._get_current_object()


# -------------------------------------------------------------------- public
@bp.route("/directory")
def directory():
    """Verified shelters with their free places; open to everyone."""
    q = (request.args.get("q") or "").strip()
    city = request.args.get("city", "")
    with_space = request.args.get("space") == "1"
    page = request.args.get("page", 1, type=int)

    query = shelter_service.directory_query(q, city, with_space)
    pagination = query.paginate(page=page, per_page=current_app.config["PER_PAGE"], error_out=False)
    counts = animal_service.occupancy_counts()
    return render_template(
        "shelters/directory.html", pagination=pagination, counts=counts, adoptable=shelter_service.adoptable_counts(),
        markers=shelter_service.map_markers(query.all(), counts), cities=shelter_service.directory_cities(),
        q=q, city=city, with_space=with_space,
    )


@bp.route("/<int:shelter_id>")
def detail(shelter_id):
    shelter = db.get_or_404(ShelterProfile, shelter_id)
    if not shelter_service.can_view_shelter(current_user, shelter):
        abort(404)  # unverified shelters are not public, and we do not reveal that they exist
    listed = Animal.query.filter(Animal.shelter_id == shelter.id, Animal.status == C.ANIMAL_AVAILABLE)
    animals = listed.order_by(Animal.available_since.desc(), Animal.id.desc()).limit(12).all()
    signed_in = current_user.is_authenticated
    adopted_total = ShelterAdmission.query.filter(
        ShelterAdmission.shelter_id == shelter.id, ShelterAdmission.discharge_reason == "Adopted").count()
    return render_template(
        "shelters/detail.html", shelter=shelter, animals=animals, listed_total=listed.count(), adopted_total=adopted_total,
        used=shelter.current_count, markers=shelter_service.map_markers([shelter]),
        can_edit=signed_in and (current_user.role == C.ROLE_ADMIN or current_user.id == shelter.user_id),
        is_admin=signed_in and current_user.role == C.ROLE_ADMIN,
    )


# ------------------------------------------------------------------ administrator
@bp.route("/")
@roles_required(C.ROLE_ADMIN)
def index():
    q = (request.args.get("q") or "").strip()
    verification = request.args.get("verification", "")
    page = request.args.get("page", 1, type=int)
    pagination = shelter_service.admin_query(q, verification).paginate(
        page=page, per_page=current_app.config["PER_PAGE"], error_out=False)
    counts = animal_service.occupancy_counts()
    verified = [s for s in ShelterProfile.query.all() if s.is_verified]
    totals = {
        "shelters": ShelterProfile.query.count(), "verified": len(verified),
        "capacity": sum(s.capacity for s in verified), "housed": sum(counts.get(s.id, 0) for s in verified),
    }
    return render_template(
        "shelters/index.html", pagination=pagination, counts=counts, adoptable=shelter_service.adoptable_counts(),
        totals=totals, q=q, verification=verification,
    )


def _edit_profile(shelter, own):
    form = ShelterProfileForm(obj=shelter)
    if own:
        del form.registration_number  # set when the shelter registered; only an administrator changes it
    if form.validate_on_submit():
        try:
            shelter_service.update_shelter(shelter, form_data(form), _actor())
        except ServiceError as error:
            flash(str(error), "danger")
        else:
            flash("The shelter profile was saved.", "success")
            return redirect(url_for("shelters.my_profile") if own else url_for("shelters.detail", shelter_id=shelter.id))
    elif request.method == "POST":
        flash("Please fix the highlighted fields and try again.", "danger")
    return render_template("shelters/edit.html", form=form, shelter=shelter, own=own, used=shelter.current_count)


@bp.route("/<int:shelter_id>/edit", methods=["GET", "POST"])
@roles_required(C.ROLE_ADMIN)
def edit(shelter_id):
    return _edit_profile(db.get_or_404(ShelterProfile, shelter_id), own=False)


# --------------------------------------------------------------- the shelter itself
@bp.route("/my-profile", methods=["GET", "POST"])
@roles_required(C.ROLE_SHELTER, verified=False)
def my_profile():
    shelter = _actor().shelter_profile
    if shelter is None:
        flash("Your shelter profile is missing. Please contact an administrator.", "danger")
        return redirect(url_for("account.profile"))
    return _edit_profile(shelter, own=True)


@bp.route("/admissions")
@roles_required(C.ROLE_SHELTER, C.ROLE_ADMIN)
def admissions():
    """Who entered and left the shelter. A shelter also sees the animals that are waiting for a place."""
    user = _actor()
    state = request.args.get("state", "current")
    state = state if state in ADMISSION_STATES else "current"
    q = (request.args.get("q") or "").strip()
    page = request.args.get("page", 1, type=int)
    is_admin = user.role == C.ROLE_ADMIN

    shelter = None
    if is_admin:
        shelter_id = request.args.get("shelter_id", type=int)
        shelter = db.session.get(ShelterProfile, shelter_id) if shelter_id else None
    else:
        shelter = user.shelter_profile
        if shelter is None:
            flash("Your shelter profile is missing. Please contact an administrator.", "danger")
            return redirect(url_for("account.profile"))

    pagination = shelter_service.admissions_query(shelter, state, q).paginate(
        page=page, per_page=current_app.config["PER_PAGE"], error_out=False)
    waiting, waiting_total = [], 0
    if not is_admin:
        waiting_query = shelter_service.awaiting_placement_query()
        waiting_total = waiting_query.count()
        waiting = waiting_query.limit(6).all()
    return render_template(
        "shelters/admissions.html", pagination=pagination, counts=shelter_service.admission_counts(shelter), state=state,
        q=q, shelter=shelter, is_admin=is_admin, waiting=waiting, waiting_total=waiting_total,
        shelter_options=[(s.id, s.shelter_name) for s in animal_service.verified_shelters()] if is_admin else [],
    )
