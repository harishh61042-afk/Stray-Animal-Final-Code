"""Rescue coordination: incoming reports, assignment, acceptance, progress notes and completion."""
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import constants as C
from app.extensions import db
from app.forms import first_error, form_data
from app.forms.animals import AnimalForm, fill_registration_choices
from app.forms.rescue import AssignForm, CompleteForm, NoteForm, RespondForm, StatusForm
from app.models import AnimalReport, RescueAssignment, User
from app.services import rescue_service
from app.services.common import ServiceError
from app.utils.permissions import redirect_back, roles_required
from app.utils.timeutil import from_local, local_today

bp = Blueprint("rescue", __name__, url_prefix="/rescue")


def _actor():
    return current_user._get_current_object()


def _to_report(report_id):
    return redirect_back(url_for("reports.detail", report_id=report_id))


# --------------------------------------------------------------------- pages
@bp.route("/")
@roles_required(C.ROLE_ADMIN, C.ROLE_RESCUER)
def manage():
    """Incoming reports, most urgent first. Administrators can assign rescuers straight from the list."""
    q = (request.args.get("q") or "").strip()
    # a search (e.g. from the top bar) looks through every report, not only the open ones
    status = request.args.get("status") or ("all" if q else "open")
    if status not in ("open", "all") + C.REPORT_STATUSES:
        status = "open"
    emergency = request.args.get("emergency", "")
    animal_type = request.args.get("type", "")
    page = request.args.get("page", 1, type=int)

    triage = status == "open" or status in C.OPEN_REPORT_STATUSES  # urgent + oldest first while work is open
    query = rescue_service.search_reports(
        q=q, status=None if status == "all" else status, emergency=emergency, animal_type=animal_type,
        priority_first=triage)
    pagination = query.paginate(page=page, per_page=current_app.config["PER_PAGE"], error_out=False)
    counts = rescue_service.status_counts()
    is_admin = current_user.role == C.ROLE_ADMIN
    return render_template(
        "rescue/manage.html", pagination=pagination, q=q, status=status, emergency=emergency, animal_type=animal_type,
        counts=counts, open_total=sum(counts[s] for s in C.OPEN_REPORT_STATUSES), is_admin=is_admin,
        rescuers=rescue_service.available_rescuers() if is_admin else [],
        workload=rescue_service.rescuer_workload() if is_admin else {},
    )


@bp.route("/my-cases")
@roles_required(C.ROLE_RESCUER)
def my_cases():
    """The rescuer's open assignments: the ones waiting for a reply and the ones in progress."""
    assignments = rescue_service.assignments_for(current_user, active=True).all()
    waiting = [a for a in assignments if a.status == C.ASSIGNMENT_ASSIGNED]
    in_progress = [a for a in assignments if a.status == C.ASSIGNMENT_ACCEPTED]
    return render_template("rescue/my_cases.html", waiting=waiting, in_progress=in_progress)


@bp.route("/history")
@roles_required(C.ROLE_RESCUER)
def history():
    page = request.args.get("page", 1, type=int)
    pagination = rescue_service.assignments_for(current_user, active=False).paginate(
        page=page, per_page=current_app.config["PER_PAGE"], error_out=False)
    totals = {
        status: count for status, count in db.session.query(RescueAssignment.status, db.func.count(RescueAssignment.id))
        .filter(RescueAssignment.rescuer_id == current_user.id).group_by(RescueAssignment.status).all()
    }
    return render_template("rescue/history.html", pagination=pagination, totals=totals)


@bp.route("/<int:report_id>/register-animal", methods=["GET", "POST"])
@roles_required(C.ROLE_ADMIN, C.ROLE_RESCUER)
def register_animal(report_id):
    """Create the permanent animal record for an animal that was rescued from this report."""
    report = db.get_or_404(AnimalReport, report_id)
    user = _actor()
    if not rescue_service.can_work_on(report, user):
        abort(403)
    if report.status not in (C.REPORT_IN_PROGRESS, C.REPORT_RESCUED):
        flash("An animal can be registered once its rescue is in progress or finished.", "warning")
        return redirect(url_for("reports.detail", report_id=report.id))

    is_admin = user.role == C.ROLE_ADMIN
    form = AnimalForm()
    fill_registration_choices(form)
    if request.method == "GET":
        _prefill_from_report(form, report)

    if form.validate_on_submit():
        data = form_data(form)
        if not is_admin:  # only administrators may exceed a shelter's capacity
            data.pop("capacity_override", None)
            data.pop("override_reason", None)
            data.pop("veterinarian_id", None)
        try:
            animal = rescue_service.register_rescued_animal(report, user, data, request.files.getlist(form.images.name))
        except ServiceError as error:
            flash(str(error), "danger")
        else:
            flash(f"{animal.display_name} was registered as {animal.animal_code}.", "success")
            return redirect(url_for("animals.detail", animal_id=animal.id))
    elif request.method == "POST":
        flash("Please fix the highlighted fields and try again.", "danger")
    return render_template("rescue/register_animal.html", form=form, report=report, is_admin=is_admin,
                           registering=True, registered=len(list(report.animals)))


def _prefill_from_report(form, report):
    form.animal_type.data = report.animal_type if report.animal_type in C.ANIMAL_TYPES else "Other"
    form.rescue_date.data = local_today()
    form.rescue_location.data = report.location_name
    form.latitude.data = report.latitude
    form.longitude.data = report.longitude
    summary = f"{report.animal_condition}. {report.animal_description}" if report.animal_description else report.animal_condition
    form.health_condition.data = (summary or "")[:2000]
    form.status.data = C.ANIMAL_RESCUED


# ------------------------------------------------------------------- actions
@bp.route("/<int:report_id>/status", methods=["POST"])
@roles_required(C.ROLE_ADMIN)
def update_status(report_id):
    report = db.get_or_404(AnimalReport, report_id)
    form = StatusForm()
    if form.validate_on_submit():
        try:
            rescue_service.update_status(report, form.status.data, _actor(), form.note.data)
            flash(f"Report {report.report_code} is now '{report.status}'.", "success")
        except ServiceError as error:
            flash(str(error), "danger")
    else:
        flash(first_error(form), "danger")
    return _to_report(report_id)


@bp.route("/<int:report_id>/assign", methods=["POST"])
@roles_required(C.ROLE_ADMIN)
def assign(report_id):
    report = db.get_or_404(AnimalReport, report_id)
    form = AssignForm()
    if form.validate_on_submit():
        rescuer = db.session.get(User, form.rescuer_id.data)
        deadline = from_local(form.deadline.data) if form.deadline.data else None
        try:
            rescue_service.assign_rescuer(report, rescuer, _actor(), deadline, form.instructions.data)
            flash(f"{report.report_code} was assigned to {rescuer.full_name}. They have been notified.", "success")
        except ServiceError as error:
            flash(str(error), "danger")
    else:
        flash(first_error(form), "danger")
    return _to_report(report_id)


@bp.route("/assignment/<int:assignment_id>/respond", methods=["POST"])
@roles_required(C.ROLE_RESCUER)
def respond(assignment_id):
    assignment = db.get_or_404(RescueAssignment, assignment_id)
    if assignment.rescuer_id != current_user.id:
        abort(403)
    form = RespondForm()
    if form.validate_on_submit():
        accept = form.decision.data == "accept"
        try:
            rescue_service.respond_to_assignment(assignment, _actor(), accept, form.note.data)
            flash("You accepted the case. Good luck with the rescue!" if accept
                  else "You declined the case. The administrator has been told.", "success")
        except ServiceError as error:
            flash(str(error), "danger")
    else:
        flash(first_error(form), "danger")
    return _to_report(assignment.report_id)


@bp.route("/<int:report_id>/note", methods=["POST"])
@roles_required(C.ROLE_ADMIN, C.ROLE_RESCUER)
def add_note(report_id):
    report = db.get_or_404(AnimalReport, report_id)
    form = NoteForm()
    if form.validate_on_submit():
        try:
            rescue_service.add_note(report, _actor(), form.note.data)
            flash("Note added.", "success")
        except ServiceError as error:
            flash(str(error), "danger")
    else:
        flash(first_error(form), "danger")
    return _to_report(report_id)


@bp.route("/<int:report_id>/complete", methods=["POST"])
@roles_required(C.ROLE_ADMIN, C.ROLE_RESCUER)
def complete(report_id):
    report = db.get_or_404(AnimalReport, report_id)
    form = CompleteForm()
    if form.validate_on_submit():
        rescued = form.outcome.data == "rescued"
        try:
            rescue_service.complete_rescue(report, _actor(), form.details.data, rescued=rescued)
            if rescued:
                flash("Rescue recorded. You can now register the animal.", "success")
                return redirect(url_for("rescue.register_animal", report_id=report.id))
            flash("The case was closed.", "success")
        except ServiceError as error:
            flash(str(error), "danger")
    else:
        flash(first_error(form), "danger")
    return _to_report(report_id)
