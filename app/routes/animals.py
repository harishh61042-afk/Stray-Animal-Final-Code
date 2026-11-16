"""Animal records: staff list, details, registration, care stage, shelter placement and photos."""
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import constants as C
from app.extensions import db
from app.forms import first_error, form_data
from app.forms.animals import (
    AnimalForm, AssignShelterForm, AssignVetForm, ConfirmForm, DischargeForm, ImagesForm, RehabForm,
    StatusChangeForm, WithdrawForm, fill_registration_choices, shelter_choices, veterinarian_choices,
)
from app.models import AdoptionApplication, Animal, AnimalImage, User
from app.services import animal_service, medical_service, rules
from app.services.common import ServiceError, like_pattern
from app.utils.permissions import redirect_back, roles_required

bp = Blueprint("animals", __name__, url_prefix="/animals")

STAFF_ROLES = (C.ROLE_ADMIN, C.ROLE_RESCUER, C.ROLE_VETERINARIAN, C.ROLE_SHELTER)
LIST_HEADINGS = {
    C.ROLE_ADMIN: ("Animals", "Every animal in the PawConnect records"),
    C.ROLE_RESCUER: ("Animals I rescued", "Animals you registered or rescued"),
    C.ROLE_VETERINARIAN: ("Assigned animals", "Animals under your medical care"),
    C.ROLE_SHELTER: ("Our animals", "Animals currently housed at your shelter"),
}


def _actor():
    return current_user._get_current_object()


def _animal_or_403(animal_id, allowed):
    """Load the animal and stop with 403 unless ``allowed(user, animal)`` says yes."""
    animal = db.get_or_404(Animal, animal_id)
    if not allowed(_actor(), animal):
        abort(403)
    return animal


def _back(animal):
    return redirect_back(url_for("animals.detail", animal_id=animal.id))


def _perform(animal, form, action, message):
    """Validate a small POST form, run ``action`` and flash the outcome; always returns to the animal page."""
    if not form.validate_on_submit():
        flash(first_error(form), "danger")
        return _back(animal)
    try:
        action()
    except ServiceError as error:
        flash(str(error), "danger")
    else:
        flash(message() if callable(message) else message, "success")
    return _back(animal)


# --------------------------------------------------------------------- pages
@bp.route("/")
@roles_required(*STAFF_ROLES)
def index():
    """The animals a staff member works with. Filters: status, type, medical status, shelter (admin) and a search."""
    user = _actor()
    q = (request.args.get("q") or "").strip()
    status = request.args.get("status", "")
    animal_type = request.args.get("type", "")
    medical = request.args.get("medical", "")
    shelter_id = request.args.get("shelter_id", type=int)
    page = request.args.get("page", 1, type=int)
    scope = "all" if request.args.get("scope") == "all" else "mine"
    is_admin = user.role == C.ROLE_ADMIN

    base = animal_service.visible_animals_query(user, scope)
    counts = dict(base.with_entities(Animal.status, db.func.count(Animal.id)).group_by(Animal.status).order_by(None).all())

    query = base
    if q:
        pattern = like_pattern(q)
        query = query.filter(db.or_(
            Animal.name.ilike(pattern, escape="\\"), Animal.animal_code.ilike(pattern, escape="\\"),
            Animal.breed.ilike(pattern, escape="\\"), Animal.color.ilike(pattern, escape="\\"),
            Animal.rescue_location.ilike(pattern, escape="\\"),
        ))
    if status in C.ANIMAL_STATUSES:
        query = query.filter(Animal.status == status)
    if animal_type in C.ANIMAL_TYPES:
        query = query.filter(Animal.animal_type == animal_type)
    if medical in C.MEDICAL_STATUSES:
        query = query.filter(Animal.medical_status == medical)
    if shelter_id and is_admin:
        query = query.filter(Animal.shelter_id == shelter_id)
    pagination = query.order_by(Animal.updated_at.desc(), Animal.id.desc()).paginate(
        page=page, per_page=current_app.config["PER_PAGE"], error_out=False)

    heading, subtitle = LIST_HEADINGS[user.role]
    if user.role == C.ROLE_VETERINARIAN and scope == "all":
        heading, subtitle = "All animals", "Every animal; open one to take the case if it has no veterinarian yet"
    return render_template(
        "animals/index.html", pagination=pagination, counts=counts, total=sum(counts.values()), q=q, status=status,
        animal_type=animal_type, medical=medical, shelter_id=shelter_id or "", scope=scope, heading=heading,
        subtitle=subtitle, is_admin=is_admin, can_add=is_admin or user.role == C.ROLE_SHELTER,
        shelter_options=[(s.id, s.shelter_name) for s in animal_service.verified_shelters()] if is_admin else [],
    )


@bp.route("/new", methods=["GET", "POST"])
@roles_required(C.ROLE_ADMIN, C.ROLE_SHELTER)
def new():
    """Register an animal directly (for example one handed in at a shelter). Rescuers register from a report."""
    user = _actor()
    is_admin = user.role == C.ROLE_ADMIN
    own_shelter = None if is_admin else user.shelter_profile
    if not is_admin and own_shelter is None:
        flash("Your shelter profile is incomplete. Please contact an administrator.", "danger")
        return redirect(url_for(C.ROLE_DASHBOARD_ENDPOINT[user.role]))

    form = AnimalForm()
    fill_registration_choices(form)
    if form.validate_on_submit():
        data = form_data(form)
        if not is_admin:  # a shelter registers into its own premises, and only an administrator may exceed capacity
            for key in ("capacity_override", "override_reason", "veterinarian_id"):
                data.pop(key, None)
            data["shelter_id"] = own_shelter.id
        try:
            animal = animal_service.create_animal(data, user, image_files=request.files.getlist(form.images.name))
        except ServiceError as error:
            flash(str(error), "danger")
        else:
            flash(f"{animal.display_name} was registered as {animal.animal_code}.", "success")
            return redirect(url_for("animals.detail", animal_id=animal.id))
    elif request.method == "POST":
        flash("Please fix the highlighted fields and try again.", "danger")
    return render_template("animals/form.html", form=form, animal=None, registering=True, is_admin=is_admin,
                           own_shelter=own_shelter, can_set_medical=True)


@bp.route("/<int:animal_id>")
@roles_required(*STAFF_ROLES)
def detail(animal_id):
    animal = db.get_or_404(Animal, animal_id)
    user = _actor()
    if not animal_service.can_view_animal(user, animal):
        if animal.is_available:  # a listed animal always has a public page
            return redirect(url_for("public.animal_detail", animal_id=animal.id))
        abort(403)

    perms = {
        "edit": animal_service.can_edit_animal(user, animal),
        "status": animal_service.can_manage_status(user, animal),
        "place": animal_service.can_place_animal(user, animal),
        "assign_vet": animal_service.can_assign_veterinarian(user, animal),
        "claim": animal_service.can_claim_animal(user, animal),
        "medical_view": medical_service.can_view_medical(user, animal),
        "medical_write": medical_service.can_manage_medical(user, animal) and not animal.is_adopted,
    }
    latest_record, recent_vaccinations = None, []
    if perms["medical_view"]:
        if animal.medical_records:
            latest_record = max(animal.medical_records, key=lambda r: (r.examination_date, r.id))
        recent_vaccinations = sorted(animal.vaccinations, key=lambda v: (v.vaccination_date, v.id), reverse=True)[:4]
    active_applications = None
    if user.role in (C.ROLE_ADMIN, C.ROLE_SHELTER):
        active_applications = AdoptionApplication.query.filter(
            AdoptionApplication.animal_id == animal.id,
            AdoptionApplication.status.in_(C.ACTIVE_ADOPTION_STATUSES)).count()
    shelter_options = shelter_choices() if perms["place"] and user.role in (C.ROLE_ADMIN, C.ROLE_RESCUER) else []
    markers = []
    if animal.has_location:
        markers = [{"lat": animal.latitude, "lng": animal.longitude, "title": animal.display_name,
                    "subtitle": animal.rescue_location or "Where the animal was found", "color": "#e0614d"}]
    return render_template(
        "animals/detail.html", animal=animal, perms=perms, is_admin=user.role == C.ROLE_ADMIN,
        status_options=[s for s in rules.allowed_animal_transitions(animal.status)
                        if s not in (C.ANIMAL_AVAILABLE, C.ANIMAL_ADOPTED, animal.status)],
        history=list(reversed(animal.status_history)), latest_record=latest_record,
        recent_vaccinations=recent_vaccinations,
        admission=next((a for a in animal.admissions if a.discharged_at is None), None),
        shelter_options=shelter_options, vet_options=veterinarian_choices() if perms["assign_vet"] else [],
        active_applications=active_applications, markers=markers,
        discharge_reasons=[r for r in C.DISCHARGE_REASONS if r != "Adopted"],
        report_link=bool(animal.report_id) and user.role in (C.ROLE_ADMIN, C.ROLE_RESCUER),
        max_images=current_app.config.get("MAX_IMAGES_PER_UPLOAD", 6),
    )


@bp.route("/<int:animal_id>/edit", methods=["GET", "POST"])
@roles_required(*STAFF_ROLES)
def edit(animal_id):
    animal = _animal_or_403(animal_id, animal_service.can_edit_animal)
    user = _actor()
    is_admin = user.role == C.ROLE_ADMIN
    form = AnimalForm(obj=animal)
    # placement, status and photos have their own actions on the animal page
    for name in ("status", "shelter_id", "veterinarian_id", "capacity_override", "override_reason", "images"):
        delattr(form, name)
    if not is_admin:  # the medical status follows the veterinarian's records
        delattr(form, "medical_status")
    if request.method == "GET" and animal.age_months is not None:
        form.age_years.data, form.age_extra_months.data = divmod(animal.age_months, 12)

    if form.validate_on_submit():
        try:
            animal_service.update_animal(animal, form_data(form), user)
        except ServiceError as error:
            flash(str(error), "danger")
        else:
            flash(f"{animal.display_name} was updated.", "success")
            return redirect(url_for("animals.detail", animal_id=animal.id))
    elif request.method == "POST":
        flash("Please fix the highlighted fields and try again.", "danger")
    return render_template("animals/form.html", form=form, animal=animal, registering=False, is_admin=is_admin,
                           own_shelter=None, can_set_medical=is_admin)


# ------------------------------------------------------------------- actions
@bp.route("/<int:animal_id>/status", methods=["POST"])
@roles_required(*STAFF_ROLES)
def change_status(animal_id):
    animal = _animal_or_403(animal_id, animal_service.can_manage_status)
    form = StatusChangeForm()
    return _perform(
        animal, form, lambda: animal_service.change_status(animal, form.status.data, _actor(), form.note.data),
        lambda: f"{animal.display_name} is now '{animal.status}'.")


@bp.route("/<int:animal_id>/mark-available", methods=["POST"])
@roles_required(*STAFF_ROLES)
def mark_available(animal_id):
    animal = _animal_or_403(animal_id, animal_service.can_manage_status)
    return _perform(
        animal, ConfirmForm(), lambda: animal_service.mark_available_for_adoption(animal, _actor()),
        lambda: f"{animal.display_name} is now listed for adoption.")


@bp.route("/<int:animal_id>/withdraw", methods=["POST"])
@roles_required(*STAFF_ROLES)
def withdraw(animal_id):
    animal = _animal_or_403(animal_id, animal_service.can_manage_status)
    form = WithdrawForm()
    return _perform(
        animal, form, lambda: animal_service.withdraw_from_adoption(animal, _actor(), form.note.data),
        lambda: f"{animal.display_name} was taken off the adoption list.")


@bp.route("/<int:animal_id>/assign-shelter", methods=["POST"])
@roles_required(*STAFF_ROLES)
def assign_shelter(animal_id):
    animal = _animal_or_403(animal_id, animal_service.can_place_animal)
    user = _actor()
    form = AssignShelterForm()
    if user.role == C.ROLE_SHELTER:  # a shelter can only admit an animal to its own premises
        if user.shelter_profile is None:
            abort(403)
        form.shelter_id.data = user.shelter_profile.id
    override = bool(form.capacity_override.data) and user.role == C.ROLE_ADMIN
    return _perform(
        animal, form,
        lambda: animal_service.assign_to_shelter(animal, form.shelter_id.data, user, override, form.override_reason.data),
        lambda: f"{animal.display_name} was admitted to {animal.shelter.shelter_name}.")


@bp.route("/<int:animal_id>/discharge", methods=["POST"])
@roles_required(*STAFF_ROLES)
def discharge(animal_id):
    animal = _animal_or_403(animal_id, animal_service.can_manage_status)
    form = DischargeForm()
    return _perform(
        animal, form, lambda: animal_service.discharge_from_shelter(animal, _actor(), form.reason.data),
        lambda: f"{animal.display_name} was discharged from the shelter.")


@bp.route("/<int:animal_id>/assign-vet", methods=["POST"])
@roles_required(C.ROLE_ADMIN)
def assign_vet(animal_id):
    animal = _animal_or_403(animal_id, animal_service.can_assign_veterinarian)
    form = AssignVetForm()

    def action():
        animal_service.assign_veterinarian(animal, db.session.get(User, form.veterinarian_id.data), _actor())

    return _perform(animal, form, action, lambda: f"{animal.veterinarian.full_name} now looks after {animal.display_name}.")


@bp.route("/<int:animal_id>/claim", methods=["POST"])
@roles_required(C.ROLE_VETERINARIAN)
def claim(animal_id):
    animal = _animal_or_403(animal_id, animal_service.can_view_animal)
    return _perform(
        animal, ConfirmForm(), lambda: animal_service.claim_animal(animal, _actor()),
        lambda: f"You are now the veterinarian of {animal.display_name}.")


@bp.route("/<int:animal_id>/rehabilitation", methods=["POST"])
@roles_required(*STAFF_ROLES)
def rehab(animal_id):
    animal = _animal_or_403(animal_id, animal_service.can_manage_status)
    form = RehabForm()
    return _perform(
        animal, form,
        lambda: animal_service.update_rehabilitation(animal, form.rehabilitation_status.data, form.rehabilitation_notes.data, _actor()),
        "Rehabilitation progress saved.")


@bp.route("/<int:animal_id>/images", methods=["POST"])
@roles_required(*STAFF_ROLES)
def add_images(animal_id):
    animal = _animal_or_403(animal_id, animal_service.can_edit_animal)
    form = ImagesForm()
    return _perform(
        animal, form, lambda: animal_service.add_images(animal, request.files.getlist(form.images.name), _actor()),
        "Photos added.")


def _image_and_animal(image_id):
    image = db.get_or_404(AnimalImage, image_id)
    return image, _animal_or_403(image.animal_id, animal_service.can_edit_animal)


@bp.route("/images/<int:image_id>/primary", methods=["POST"])
@roles_required(*STAFF_ROLES)
def set_primary_image(image_id):
    image, animal = _image_and_animal(image_id)
    return _perform(animal, ConfirmForm(), lambda: animal_service.set_primary_image(image, _actor()),
                    "The cover photo was changed.")


@bp.route("/images/<int:image_id>/delete", methods=["POST"])
@roles_required(*STAFF_ROLES)
def delete_image(image_id):
    image, animal = _image_and_animal(image_id)
    return _perform(animal, ConfirmForm(), lambda: animal_service.delete_image(image, _actor()), "The photo was removed.")
