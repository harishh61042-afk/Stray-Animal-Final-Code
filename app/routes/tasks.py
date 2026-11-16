"""Volunteer tasks: created and coordinated by administrators and rescuers, accepted and carried out by volunteers."""
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.orm import selectinload

from app import constants as C
from app.extensions import db
from app.forms import first_error, form_data
from app.forms.animals import ConfirmForm
from app.forms.tasks import TaskAssignForm, TaskCompleteForm, TaskForm, TaskProgressForm, TaskReasonForm
from app.models import Animal, AnimalReport, ShelterProfile, User, VolunteerProfile, VolunteerTask, VolunteerTaskAssignment
from app.services import animal_service, volunteer_service
from app.services.common import ServiceError, like_pattern
from app.utils import timeutil
from app.utils.pagination import ListPagination
from app.utils.permissions import approved_volunteer_required, redirect_back, roles_required

bp = Blueprint("tasks", __name__, url_prefix="/tasks")

MANAGER_ROLES = (C.ROLE_ADMIN, C.ROLE_RESCUER)
CLOSED_TASK_STATUSES = (C.TASK_COMPLETED, C.TASK_CANCELLED)
WORKING_STATUSES = (C.TA_ASSIGNED, C.TA_ACCEPTED, C.TA_IN_PROGRESS)


def _actor():
    return current_user._get_current_object()


def _offset():
    return current_app.config.get("DISPLAY_UTC_OFFSET_MINUTES", timeutil.DEFAULT_OFFSET_MINUTES)


def _short(text, length=45):
    text = text or ""
    return text if len(text) <= length else text[: length - 1].rstrip() + "…"


# ------------------------------------------------------------------ the task form
def _assignable_volunteers(task=None):
    """Approved, active volunteers (not already on ``task``) a manager can assign."""
    query = User.query.join(VolunteerProfile, VolunteerProfile.user_id == User.id).filter(
        User.role == C.ROLE_VOLUNTEER, User.status == C.ACCOUNT_ACTIVE,
        VolunteerProfile.application_status == C.APPLICATION_APPROVED,
    )
    if task is not None:
        taken = [a.volunteer_id for a in task.active_assignments]
        if taken:
            query = query.filter(User.id.notin_(taken))
    return query.order_by(User.full_name, User.id).limit(300).all()


def _fill_choices(form, task=None, with_volunteers=False):
    """Fill the drop-downs of the task form; returns the assignable volunteers (empty unless asked for)."""
    reports = AnimalReport.query.filter(AnimalReport.status.in_(C.OPEN_REPORT_STATUSES)).order_by(
        AnimalReport.id.desc()).limit(100).all()
    if task is not None and task.report is not None and task.report not in reports:
        reports.append(task.report)
    form.report_id.choices = [("", "Not linked to a report")] + [
        (r.id, f"{r.report_code} · {r.animal_type} · {_short(r.location_name, 40)}") for r in reports]

    animals = Animal.query.filter(Animal.status != C.ANIMAL_ADOPTED).order_by(Animal.id.desc()).limit(100).all()
    if task is not None and task.animal is not None and task.animal not in animals:
        animals.append(task.animal)
    form.animal_id.choices = [("", "Not linked to an animal")] + [
        (a.id, f"{a.animal_code} · {a.display_name} ({a.animal_type})") for a in animals]

    shelters = list(animal_service.verified_shelters())
    if task is not None and task.shelter is not None and task.shelter not in shelters:
        shelters.append(task.shelter)
    form.shelter_id.choices = [("", "Not linked to a shelter")] + [(s.id, s.shelter_name) for s in shelters]

    volunteers = _assignable_volunteers(task) if with_volunteers else []
    form.volunteer_ids.choices = [(v.id, v.full_name) for v in volunteers]
    return volunteers


def _prefill_from_links(form):
    """``/tasks/new?report_id=..`` / ``?animal_id=..`` / ``?shelter_id=..`` start the form from that record."""
    report = db.session.get(AnimalReport, request.args.get("report_id", type=int) or 0)
    animal = db.session.get(Animal, request.args.get("animal_id", type=int) or 0)
    shelter = db.session.get(ShelterProfile, request.args.get("shelter_id", type=int) or 0)
    if animal is not None and shelter is None:
        shelter = animal.shelter
    if report is not None:
        form.report_id.data = report.id
        form.task_type.data = "Rescue Assistance"
        form.title.data = f"Help with rescue {report.report_code}"
        form.location_name.data = report.location_name
        form.address.data = report.address
        if report.latitude is not None and report.longitude is not None:
            form.latitude.data, form.longitude.data = f"{report.latitude:.6f}", f"{report.longitude:.6f}"
    if animal is not None:
        form.animal_id.data = animal.id
        if not form.title.data:
            form.title.data = f"Help with {animal.display_name}"
    if shelter is not None:
        form.shelter_id.data = shelter.id
        if not form.location_name.data:
            form.location_name.data = shelter.shelter_name
            form.address.data = ", ".join(part for part in (shelter.address, shelter.city) if part)
            if shelter.latitude is not None and shelter.longitude is not None:
                form.latitude.data, form.longitude.data = f"{shelter.latitude:.6f}", f"{shelter.longitude:.6f}"


def _links_exist(form):
    """The linked records must exist (the drop-downs only list the most recent ones)."""
    ok = True
    for field, model, label in ((form.animal_id, Animal, "animal"), (form.shelter_id, ShelterProfile, "shelter"),
                                (form.report_id, AnimalReport, "rescue report")):
        if field.data and db.session.get(model, field.data) is None:
            field.errors.append(f"That {label} does not exist.")
            ok = False
    return ok


def _task_data(form):
    """Form values for the service; the deadline typed in local time is stored as UTC."""
    data = form_data(form, "volunteer_ids")
    data["due_at"] = timeutil.from_local(form.due_at.data, _offset()) if form.due_at.data else None
    return data


@bp.route("/new", methods=["GET", "POST"])
@roles_required(*MANAGER_ROLES)
def new():
    user = _actor()
    form = TaskForm()
    volunteers = _fill_choices(form, with_volunteers=True)
    if request.method == "GET":
        _prefill_from_links(form)
    if form.validate_on_submit() and _links_exist(form):
        try:
            task = volunteer_service.create_task(user, _task_data(form), volunteer_ids=form.volunteer_ids.data or [])
        except ServiceError as error:
            flash(str(error), "danger")
        else:
            flash(f"Task '{task.title}' was created.", "success")
            return redirect(url_for("tasks.detail", task_id=task.id))
    return render_template("tasks/form.html", form=form, task=None, volunteers=volunteers)


@bp.route("/<int:task_id>/edit", methods=["GET", "POST"])
@roles_required(*MANAGER_ROLES)
def edit(task_id):
    task = db.get_or_404(VolunteerTask, task_id)
    user = _actor()
    if not volunteer_service.can_edit_task(user, task):
        abort(403)
    if task.status in CLOSED_TASK_STATUSES:
        flash(f"A {task.status.lower()} task cannot be edited.", "warning")
        return redirect(url_for("tasks.detail", task_id=task.id))
    form = TaskForm(obj=task)
    del form.volunteer_ids  # volunteers are assigned from the task page
    _fill_choices(form, task=task)
    if request.method == "GET":
        form.due_at.data = timeutil.to_local(task.due_at, _offset())
    if form.validate_on_submit() and _links_exist(form):
        try:
            volunteer_service.update_task(task, user, _task_data(form))
        except ServiceError as error:
            flash(str(error), "danger")
        else:
            flash("The task was updated.", "success")
            return redirect(url_for("tasks.detail", task_id=task.id))
    return render_template("tasks/form.html", form=form, task=task, volunteers=[])


# ------------------------------------------------------------------ coordination list
@bp.route("/")
@roles_required(*MANAGER_ROLES)
def manage():
    user = _actor()
    q = (request.args.get("q") or "").strip()
    status = request.args.get("status", "")
    task_type = request.args.get("type", "")
    scope = "mine" if request.args.get("scope") == "mine" else "all"
    page = request.args.get("page", 1, type=int)

    base = VolunteerTask.query
    if scope == "mine":
        base = base.filter(VolunteerTask.created_by == user.id)
    counts = dict(base.with_entities(VolunteerTask.status, db.func.count(VolunteerTask.id)).group_by(
        VolunteerTask.status).order_by(None).all())
    overdue = base.filter(
        VolunteerTask.due_at.isnot(None), VolunteerTask.due_at < timeutil.utcnow(),
        VolunteerTask.status.notin_(CLOSED_TASK_STATUSES)).count()

    query = base
    if status in C.TASK_STATUSES:
        query = query.filter(VolunteerTask.status == status)
    if task_type in C.TASK_TYPES:
        query = query.filter(VolunteerTask.task_type == task_type)
    if q:
        pattern = like_pattern(q)
        query = query.filter(db.or_(
            VolunteerTask.title.ilike(pattern, escape="\\"), VolunteerTask.description.ilike(pattern, escape="\\"),
            VolunteerTask.location_name.ilike(pattern, escape="\\"),
        ))
    closed_last = db.case((VolunteerTask.status.in_(CLOSED_TASK_STATUSES), 1), else_=0)
    pagination = query.options(selectinload(VolunteerTask.assignments)).order_by(
        closed_last, VolunteerTask.due_at.is_(None), VolunteerTask.due_at, VolunteerTask.id.desc(),
    ).paginate(page=page, per_page=current_app.config["PER_PAGE"], error_out=False)
    return render_template(
        "tasks/manage.html", pagination=pagination, counts=counts, overdue=overdue, q=q, status=status, task_type=task_type,
        scope=scope, can_edit_any=user.role == C.ROLE_ADMIN,
        volunteers_ready=VolunteerProfile.query.filter_by(application_status=C.APPLICATION_APPROVED).count(),
    )


# ------------------------------------------------------------------ one task
@bp.route("/<int:task_id>")
@roles_required()
def detail(task_id):
    task = db.get_or_404(VolunteerTask, task_id)
    user = _actor()
    if not volunteer_service.can_view_task(user, task):
        abort(403)
    is_manager = volunteer_service.can_manage_tasks(user)
    can_edit = volunteer_service.can_edit_task(user, task)
    is_open = task.status not in CLOSED_TASK_STATUSES
    mine = next((a for a in task.assignments if a.volunteer_id == user.id), None) if user.role == C.ROLE_VOLUNTEER else None
    is_volunteer = user.role == C.ROLE_VOLUNTEER and user.is_approved_volunteer
    can_join = bool(
        is_volunteer and is_open and task.open_slots > 0
        and (mine is None or mine.status in C.INACTIVE_TASK_ASSIGNMENT_STATUSES))
    volunteers = _assignable_volunteers(task) if (is_manager and is_open and task.open_slots > 0) else []
    markers = []
    if task.has_location:
        markers = [{"lat": task.latitude, "lng": task.longitude, "title": task.title,
                    "subtitle": task.location_name or task.address or task.task_type}]
    return render_template(
        "tasks/detail.html", task=task, mine=mine, is_manager=is_manager, can_edit=can_edit, is_open=is_open,
        can_join=can_join, volunteers=volunteers, markers=markers,
        assignments=sorted(task.assignments, key=lambda a: (not a.is_active, a.id)),
        can_remove=can_edit or user.role == C.ROLE_ADMIN,
    )


# ------------------------------------------------------------------ the volunteer's own work
@bp.route("/available")
@approved_volunteer_required
def available():
    user = _actor()
    q = (request.args.get("q") or "").strip()
    task_type = request.args.get("type", "")
    tasks = volunteer_service.open_tasks_for(user)
    if q:
        needle = q.lower()
        tasks = [t for t in tasks if needle in " ".join(filter(None, (t.title, t.description, t.location_name, t.address))).lower()]
    if task_type in C.TASK_TYPES:
        tasks = [t for t in tasks if t.task_type == task_type]
    pagination = ListPagination(tasks, request.args.get("page", 1, type=int), current_app.config["PER_PAGE"])
    return render_template("tasks/available.html", pagination=pagination, q=q, task_type=task_type)


def _my_assignments(user, statuses):
    return VolunteerTaskAssignment.query.join(VolunteerTask, VolunteerTaskAssignment.task_id == VolunteerTask.id).filter(
        VolunteerTaskAssignment.volunteer_id == user.id, VolunteerTaskAssignment.status.in_(statuses))


@bp.route("/mine")
@approved_volunteer_required
def mine():
    user = _actor()
    page = request.args.get("page", 1, type=int)
    waiting_first = db.case((VolunteerTaskAssignment.status == C.TA_ASSIGNED, 0), else_=1)
    pagination = _my_assignments(user, WORKING_STATUSES).options(selectinload(VolunteerTaskAssignment.task)).order_by(
        waiting_first, VolunteerTask.due_at.is_(None), VolunteerTask.due_at, VolunteerTaskAssignment.id.desc(),
    ).paginate(page=page, per_page=current_app.config["PER_PAGE"], error_out=False)
    return render_template("tasks/mine.html", pagination=pagination, summary=volunteer_service.volunteer_summary(user))


@bp.route("/history")
@approved_volunteer_required
def history():
    user = _actor()
    page = request.args.get("page", 1, type=int)
    pagination = _my_assignments(user, (C.TA_COMPLETED, C.TA_DECLINED, C.TA_CANCELLED)).options(
        selectinload(VolunteerTaskAssignment.task)).order_by(
        VolunteerTaskAssignment.completed_at.desc(), VolunteerTaskAssignment.responded_at.desc(), VolunteerTaskAssignment.id.desc(),
    ).paginate(page=page, per_page=current_app.config["PER_PAGE"], error_out=False)
    return render_template("tasks/history.html", pagination=pagination, summary=volunteer_service.volunteer_summary(user))


# ------------------------------------------------------------------ actions (POST)
def _viewable_task(task_id):
    task = db.get_or_404(VolunteerTask, task_id)
    if not volunteer_service.can_view_task(_actor(), task):
        abort(403)
    return task


def _back(task):
    return redirect_back(url_for("tasks.detail", task_id=task.id))


def _perform(task, form, action, message):
    """Validate a small POST form, run ``action`` and flash the outcome; always returns to the task."""
    if not form.validate_on_submit():
        flash(first_error(form), "danger")
        return _back(task)
    try:
        action()
    except ServiceError as error:
        flash(str(error), "danger")
    else:
        flash(message, "success")
    return _back(task)


@bp.route("/<int:task_id>/accept", methods=["POST"])
@approved_volunteer_required
def accept(task_id):
    task = _viewable_task(task_id)
    return _perform(task, ConfirmForm(), lambda: volunteer_service.accept_task(task, _actor()),
                    "You accepted the task. Thank you for helping!")


@bp.route("/<int:task_id>/decline", methods=["POST"])
@approved_volunteer_required
def decline(task_id):
    task = _viewable_task(task_id)
    form = TaskReasonForm()
    return _perform(task, form, lambda: volunteer_service.decline_task(task, _actor(), form.reason.data),
                    "You declined the task. The coordinator was told.")


@bp.route("/<int:task_id>/progress", methods=["POST"])
@approved_volunteer_required
def progress(task_id):
    task = _viewable_task(task_id)
    form = TaskProgressForm()
    return _perform(
        task, form, lambda: volunteer_service.update_progress(task, _actor(), form.progress_percent.data, form.note.data),
        "Your progress was saved.")


@bp.route("/<int:task_id>/complete", methods=["POST"])
@approved_volunteer_required
def complete(task_id):
    task = _viewable_task(task_id)
    form = TaskCompleteForm()
    return _perform(
        task, form, lambda: volunteer_service.complete_task(task, _actor(), form.notes.data, form.hours.data),
        "Task marked as completed. Thank you!")


@bp.route("/<int:task_id>/assign", methods=["POST"])
@roles_required(*MANAGER_ROLES)
def assign(task_id):
    task = db.get_or_404(VolunteerTask, task_id)
    form = TaskAssignForm()
    form.volunteer_id.choices = []
    volunteer = db.session.get(User, form.volunteer_id.data) if form.volunteer_id.data else None

    def run():
        volunteer_service.assign_volunteer(task, volunteer, _actor())

    if volunteer is None and form.volunteer_id.data:
        flash("That volunteer does not exist.", "danger")
        return _back(task)
    return _perform(task, form, run, f"{volunteer.full_name if volunteer else 'The volunteer'} was assigned and has been notified.")


@bp.route("/<int:task_id>/cancel", methods=["POST"])
@roles_required(*MANAGER_ROLES)
def cancel(task_id):
    task = db.get_or_404(VolunteerTask, task_id)
    if not volunteer_service.can_edit_task(_actor(), task):
        abort(403)
    form = TaskReasonForm()
    return _perform(task, form, lambda: volunteer_service.cancel_task(task, _actor(), form.reason.data),
                    "The task was cancelled and the volunteers were told.")


@bp.route("/<int:task_id>/assignments/<int:assignment_id>/remove", methods=["POST"])
@roles_required(*MANAGER_ROLES)
def remove_volunteer(task_id, assignment_id):
    task = db.get_or_404(VolunteerTask, task_id)
    assignment = db.get_or_404(VolunteerTaskAssignment, assignment_id)
    if assignment.task_id != task.id:
        abort(404)
    if not (volunteer_service.can_edit_task(_actor(), task) or _actor().role == C.ROLE_ADMIN):
        abort(403)
    return _perform(task, ConfirmForm(), lambda: volunteer_service.remove_volunteer(task, assignment, _actor()),
                    "The volunteer was removed from the task.")
