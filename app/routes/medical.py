"""Veterinary records: medical files, examinations, vaccinations and due reminders."""
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import constants as C
from app.extensions import db
from app.forms import first_error, form_data
from app.forms.animals import ConfirmForm, veterinarian_choices
from app.forms.medical import OTHER_VACCINE, MedicalRecordForm, VaccinationForm
from app.models import Animal, MedicalRecord, Vaccination
from app.services import animal_service, medical_service, stats
from app.services.common import ServiceError, like_pattern
from app.utils.permissions import redirect_back, roles_required
from app.utils.timeutil import local_today

bp = Blueprint("medical", __name__, url_prefix="/medical")

LIST_ROLES = (C.ROLE_ADMIN, C.ROLE_VETERINARIAN, C.ROLE_SHELTER)
FILE_ROLES = (C.ROLE_ADMIN, C.ROLE_VETERINARIAN, C.ROLE_SHELTER, C.ROLE_RESCUER)
WRITE_ROLES = (C.ROLE_ADMIN, C.ROLE_VETERINARIAN)
DUE_WINDOWS = (7, 14, 30, 60)


def _actor():
    return current_user._get_current_object()


def _can_write(user, animal):
    return medical_service.can_manage_medical(user, animal) and not animal.is_adopted


def _writable_animal(animal_id):
    """``(animal, None)`` when the user may add records, otherwise ``(animal, response)`` to return at once."""
    animal = db.get_or_404(Animal, animal_id)
    user = _actor()
    if animal.is_adopted:
        flash("This animal has been adopted, so its medical file is closed.", "warning")
        return animal, redirect(url_for("medical.animal_profile", animal_id=animal.id))
    if not medical_service.can_manage_medical(user, animal):
        if user.role == C.ROLE_VETERINARIAN and animal.veterinarian_id is None:
            flash("Take over this animal's case first, then you can add examinations and vaccinations.", "info")
            return animal, redirect(url_for("medical.animal_profile", animal_id=animal.id))
        abort(403)
    return animal, None


# ------------------------------------------------------------------- overview
@bp.route("/")
@roles_required(*LIST_ROLES)
def index():
    """Medical overview of the animals in the user's care: health, vaccinations and the latest examination."""
    user = _actor()
    q = (request.args.get("q") or "").strip()
    medical = request.args.get("medical", "")
    vaccination = request.args.get("vaccination", "")
    exam = request.args.get("exam", "")
    page = request.args.get("page", 1, type=int)
    scope = "all" if request.args.get("scope") == "all" else "mine"

    base = animal_service.visible_animals_query(user, scope).filter(Animal.status != C.ANIMAL_ADOPTED)
    kpis = {
        "total": base.count(),
        "critical": base.filter(Animal.medical_status == C.MEDICAL_CRITICAL).count(),
        "treatment": base.filter(Animal.medical_status.in_((C.MEDICAL_TREATMENT, C.MEDICAL_RECOVERING))).count(),
        "vaccine": base.filter(Animal.vaccination_status.in_((C.VACC_NONE, C.VACC_DUE))).count(),
    }
    query = base
    if q:
        pattern = like_pattern(q)
        query = query.filter(db.or_(
            Animal.name.ilike(pattern, escape="\\"), Animal.animal_code.ilike(pattern, escape="\\"),
            Animal.breed.ilike(pattern, escape="\\")))
    if medical in C.MEDICAL_STATUSES:
        query = query.filter(Animal.medical_status == medical)
    if vaccination in C.VACCINATION_STATUSES:
        query = query.filter(Animal.vaccination_status == vaccination)
    if exam == "none":
        query = query.filter(~Animal.medical_records.any())
    urgency = db.case((Animal.medical_status == C.MEDICAL_CRITICAL, 0), (Animal.medical_status == C.MEDICAL_TREATMENT, 1), else_=2)
    pagination = query.order_by(urgency, Animal.updated_at.desc(), Animal.id.desc()).paginate(
        page=page, per_page=current_app.config["PER_PAGE"], error_out=False)

    latest, due = {}, {}
    for animal in pagination.items:
        if animal.medical_records:
            latest[animal.id] = max(animal.medical_records, key=lambda r: (r.examination_date, r.id))
        due[animal.id] = medical_service.next_vaccination_due(animal)
    return render_template(
        "medical/index.html", pagination=pagination, kpis=kpis, latest=latest, due=due, q=q, medical=medical,
        vaccination=vaccination, exam=exam, scope=scope, today=local_today(),
    )


# ---------------------------------------------------------------- medical file
@bp.route("/animal/<int:animal_id>")
@roles_required(*FILE_ROLES)
def animal_profile(animal_id):
    animal = db.get_or_404(Animal, animal_id)
    user = _actor()
    if not medical_service.can_view_medical(user, animal):
        abort(403)
    by_date = sorted(animal.medical_records, key=lambda r: (r.examination_date, r.id))
    weights = [r for r in by_date if r.weight_kg]
    chart = None
    if len(weights) >= 2:
        chart = {
            "type": "line", "labels": [f"{r.examination_date:%d %b %Y}" for r in weights],
            "datasets": [{"label": "Weight (kg)", "data": [r.weight_kg for r in weights], "color": "#1f9d63"}],
            "legend": False, "unit": " kg", "integer": False,
        }
    return render_template(
        "medical/animal_profile.html", animal=animal, records=list(reversed(by_date)),
        vaccinations=sorted(animal.vaccinations, key=lambda v: (v.vaccination_date, v.id), reverse=True),
        chart=chart, latest_weight=weights[-1] if weights else None, next_due=medical_service.next_vaccination_due(animal),
        can_write=_can_write(user, animal), can_claim=animal_service.can_claim_animal(user, animal),
        can_open_animal=animal_service.can_view_animal(user, animal), today=local_today(),
    )


@bp.route("/animal/<int:animal_id>/add", methods=["GET", "POST"])
@roles_required(*WRITE_ROLES)
def add_record(animal_id):
    animal, blocked = _writable_animal(animal_id)
    if blocked:
        return blocked
    user = _actor()
    is_admin = user.role == C.ROLE_ADMIN
    form = MedicalRecordForm()
    if is_admin:
        form.veterinarian_id.choices = veterinarian_choices("Choose the examining veterinarian")
    else:
        del form.veterinarian_id  # a veterinarian always examines as themselves
    if request.method == "GET":
        form.medical_status.data = animal.medical_status
        if is_admin:
            form.veterinarian_id.data = animal.veterinarian_id

    if form.validate_on_submit():
        try:
            medical_service.add_medical_record(animal, user, form_data(form), form.document.data)
        except ServiceError as error:
            flash(str(error), "danger")
        else:
            flash("The examination was saved and the medical status updated.", "success")
            return redirect(url_for("medical.animal_profile", animal_id=animal.id))
    elif request.method == "POST":
        flash("Please fix the highlighted fields and try again.", "danger")
    return render_template("medical/record_form.html", form=form, animal=animal, record=None, is_admin=is_admin)


@bp.route("/record/<int:record_id>")
@roles_required(*FILE_ROLES)
def record_detail(record_id):
    record = db.get_or_404(MedicalRecord, record_id)
    animal = record.animal
    user = _actor()
    if not medical_service.can_view_medical(user, animal):
        abort(403)
    return render_template("medical/record_detail.html", record=record, animal=animal, can_write=_can_write(user, animal))


@bp.route("/record/<int:record_id>/edit", methods=["GET", "POST"])
@roles_required(*WRITE_ROLES)
def edit_record(record_id):
    record = db.get_or_404(MedicalRecord, record_id)
    animal = record.animal
    user = _actor()
    if not _can_write(user, animal):
        abort(403)
    form = MedicalRecordForm(obj=record)
    del form.veterinarian_id  # the examining veterinarian of an existing record does not change
    if form.validate_on_submit():
        try:
            medical_service.update_medical_record(record, user, form_data(form), form.document.data)
        except ServiceError as error:
            flash(str(error), "danger")
        else:
            flash("The medical record was updated.", "success")
            return redirect(url_for("medical.record_detail", record_id=record.id))
    elif request.method == "POST":
        flash("Please fix the highlighted fields and try again.", "danger")
    return render_template("medical/record_form.html", form=form, animal=animal, record=record, is_admin=False)


# ---------------------------------------------------------------- unassigned
@bp.route("/unassigned")
@roles_required(C.ROLE_ADMIN, C.ROLE_VETERINARIAN)
def unassigned():
    """Animals that have no veterinarian yet. A veterinarian can take a case; an administrator assigns one."""
    q = (request.args.get("q") or "").strip()
    page = request.args.get("page", 1, type=int)
    query = stats.unassigned_animals_query()
    if q:
        pattern = like_pattern(q)
        query = query.filter(db.or_(
            Animal.name.ilike(pattern, escape="\\"), Animal.animal_code.ilike(pattern, escape="\\"),
            Animal.breed.ilike(pattern, escape="\\")))
    pagination = query.order_by(Animal.created_at.asc(), Animal.id.asc()).paginate(
        page=page, per_page=current_app.config["PER_PAGE"], error_out=False)
    return render_template("medical/unassigned.html", pagination=pagination, q=q)


# -------------------------------------------------------------- vaccinations
@bp.route("/vaccinations")
@roles_required(*LIST_ROLES)
def vaccinations():
    """Vaccinations that are due (or overdue), or the most recent doses given."""
    user = _actor()
    view = "recent" if request.args.get("view") == "recent" else "due"
    days = request.args.get("days", 14, type=int)
    days = days if days in DUE_WINDOWS else 14
    scope = "all" if request.args.get("scope") == "all" else "mine"
    page = request.args.get("page", 1, type=int)
    shelter = user.shelter_profile if user.role == C.ROLE_SHELTER else None
    own_cases = user.role == C.ROLE_VETERINARIAN and scope != "all"

    pagination = None
    if view == "due":
        items = medical_service.due_vaccinations(days, vet=user if own_cases else None)
        if user.role == C.ROLE_SHELTER:
            items = [v for v in items if shelter is not None and v.animal.shelter_id == shelter.id]
    else:
        query = Vaccination.query.join(Animal, Vaccination.animal_id == Animal.id)
        if own_cases:
            query = query.filter(Animal.veterinarian_id == user.id)
        elif user.role == C.ROLE_SHELTER:
            query = query.filter(Animal.shelter_id == (shelter.id if shelter is not None else -1))
        pagination = query.order_by(Vaccination.vaccination_date.desc(), Vaccination.id.desc()).paginate(
            page=page, per_page=current_app.config["PER_PAGE"], error_out=False)
        items = pagination.items
    today = local_today()
    return render_template(
        "medical/vaccinations.html", view=view, days=days, windows=DUE_WINDOWS, scope=scope, items=items, pagination=pagination,
        today=today, overdue=sum(1 for v in items if v.next_due_date and v.next_due_date < today) if view == "due" else 0,
        writable={v.id for v in items if _can_write(user, v.animal)},
    )


@bp.route("/animal/<int:animal_id>/vaccinations/add", methods=["GET", "POST"])
@roles_required(*WRITE_ROLES)
def add_vaccination(animal_id):
    animal, blocked = _writable_animal(animal_id)
    if blocked:
        return blocked
    form = VaccinationForm()
    if request.method == "GET":
        wanted = (request.args.get("vaccine") or "").strip()
        if wanted in C.COMMON_VACCINES and wanted != OTHER_VACCINE:
            form.vaccine_name.data = wanted
        elif wanted:  # a booster for a vaccine that is not in the standard list
            form.vaccine_name.data, form.custom_name.data = OTHER_VACCINE, wanted[:120]

    if form.validate_on_submit():
        data = {
            "vaccine_name": form.final_name(), "vaccination_date": form.vaccination_date.data,
            "next_due_date": form.next_due_date.data, "batch_number": form.batch_number.data, "notes": form.notes.data,
        }
        try:
            medical_service.add_vaccination(animal, _actor(), data)
        except ServiceError as error:
            flash(str(error), "danger")
        else:
            flash(f"{form.final_name()} was recorded for {animal.display_name}.", "success")
            return redirect(url_for("medical.animal_profile", animal_id=animal.id))
    elif request.method == "POST":
        flash("Please fix the highlighted fields and try again.", "danger")
    return render_template("medical/vaccination_form.html", form=form, animal=animal)


@bp.route("/vaccination/<int:vaccination_id>/delete", methods=["POST"])
@roles_required(*WRITE_ROLES)
def delete_vaccination(vaccination_id):
    vaccination = db.get_or_404(Vaccination, vaccination_id)
    animal = vaccination.animal
    if not _can_write(_actor(), animal):
        abort(403)
    form = ConfirmForm()
    if not form.validate_on_submit():
        flash(first_error(form), "danger")
    else:
        try:
            medical_service.delete_vaccination(vaccination, _actor())
        except ServiceError as error:
            flash(str(error), "danger")
        else:
            flash("The vaccination record was removed.", "success")
    return redirect_back(url_for("medical.animal_profile", animal_id=animal.id))
