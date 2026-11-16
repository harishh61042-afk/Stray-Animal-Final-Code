"""Volunteers: a volunteer's own application, the volunteer directory and the administrator's approval queue."""
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import constants as C
from app.extensions import db
from app.forms import first_error, form_data
from app.forms.volunteers import VolunteerApplicationForm, VolunteerReviewForm
from app.models import User, VolunteerProfile, VolunteerTaskAssignment
from app.services import volunteer_service
from app.services.common import ServiceError, like_pattern
from app.utils.permissions import redirect_back, roles_required

bp = Blueprint("volunteers", __name__, url_prefix="/volunteers")

DIRECTORY_ROLES = (C.ROLE_ADMIN, C.ROLE_RESCUER)
WORKING_STATUSES = (C.TA_ASSIGNED, C.TA_ACCEPTED, C.TA_IN_PROGRESS)


def _actor():
    return current_user._get_current_object()


def _volunteer_query():
    """Volunteer accounts joined with their application (``VolunteerProfile``)."""
    return User.query.join(VolunteerProfile, VolunteerProfile.user_id == User.id).filter(User.role == C.ROLE_VOLUNTEER)


def _search(query, q):
    if not q:
        return query
    pattern = like_pattern(q)
    return query.filter(db.or_(
        User.full_name.ilike(pattern, escape="\\"), User.email.ilike(pattern, escape="\\"),
        VolunteerProfile.skills.ilike(pattern, escape="\\"), VolunteerProfile.availability.ilike(pattern, escape="\\"),
    ))


def _work_stats(volunteer_ids):
    """``{user_id: {"completed", "hours", "active"}}`` for the volunteers shown on one page."""
    stats = {vid: {"completed": 0, "hours": 0.0, "active": 0} for vid in volunteer_ids}
    if not volunteer_ids:
        return stats
    rows = db.session.query(
        VolunteerTaskAssignment.volunteer_id, VolunteerTaskAssignment.status, db.func.count(VolunteerTaskAssignment.id),
        db.func.coalesce(db.func.sum(VolunteerTaskAssignment.hours_spent), 0),
    ).filter(VolunteerTaskAssignment.volunteer_id.in_(volunteer_ids)).group_by(
        VolunteerTaskAssignment.volunteer_id, VolunteerTaskAssignment.status).all()
    for volunteer_id, status, count, hours in rows:
        if status == C.TA_COMPLETED:
            stats[volunteer_id]["completed"] += count
            stats[volunteer_id]["hours"] += float(hours or 0)
        elif status in WORKING_STATUSES:
            stats[volunteer_id]["active"] += count
    return stats


# ------------------------------------------------------------ the volunteer's own application
def _render_application(form):
    user = _actor()
    profile = user.volunteer_profile
    if profile is None:
        abort(404)
    summary = volunteer_service.volunteer_summary(user) if profile.is_approved else None
    return render_template(
        "volunteers/my_application.html", form=form, profile=profile, summary=summary,
        can_edit=profile.application_status != C.APPLICATION_APPROVED,
    )


@bp.route("/my-application")
@roles_required(C.ROLE_VOLUNTEER)
def my_application():
    profile = _actor().volunteer_profile
    if profile is None:
        abort(404)
    return _render_application(VolunteerApplicationForm(obj=profile))


@bp.route("/my-application/resubmit", methods=["POST"])
@roles_required(C.ROLE_VOLUNTEER)
def resubmit():
    form = VolunteerApplicationForm()
    if form.validate_on_submit():
        try:
            volunteer_service.resubmit_application(_actor(), form_data(form))
        except ServiceError as error:
            flash(str(error), "danger")
        else:
            flash("Your application was saved and sent. An administrator will review it soon.", "success")
            return redirect(url_for("volunteers.my_application"))
    return _render_application(form)


# ------------------------------------------------------------ the directory (administrators and rescuers)
@bp.route("/")
@roles_required(*DIRECTORY_ROLES)
def index():
    user = _actor()
    is_admin = user.role == C.ROLE_ADMIN
    q = (request.args.get("q") or "").strip()
    status = request.args.get("status", C.APPLICATION_APPROVED) if is_admin else C.APPLICATION_APPROVED
    page = request.args.get("page", 1, type=int)

    counts = dict(db.session.query(VolunteerProfile.application_status, db.func.count(VolunteerProfile.id)).group_by(
        VolunteerProfile.application_status).all())
    query = _search(_volunteer_query(), q)
    if status in C.VOLUNTEER_APPLICATION_STATUSES:
        query = query.filter(VolunteerProfile.application_status == status)
    pagination = query.order_by(User.full_name, User.id).paginate(
        page=page, per_page=current_app.config["PER_PAGE"], error_out=False)
    stats = _work_stats([volunteer.id for volunteer in pagination.items])
    working = db.session.query(db.func.count(db.func.distinct(VolunteerTaskAssignment.volunteer_id))).filter(
        VolunteerTaskAssignment.status.in_(WORKING_STATUSES)).scalar() or 0
    return render_template(
        "volunteers/index.html", pagination=pagination, stats=stats, counts=counts, working=working, q=q, status=status,
        is_admin=is_admin,
    )


@bp.route("/<int:user_id>")
@roles_required(*DIRECTORY_ROLES)
def detail(user_id):
    volunteer = db.get_or_404(User, user_id)
    profile = volunteer.volunteer_profile
    if volunteer.role != C.ROLE_VOLUNTEER or profile is None:
        abort(404)
    is_admin = _actor().role == C.ROLE_ADMIN
    if not is_admin and not profile.is_approved:
        abort(404)  # rescuers only see approved volunteers
    assignments = VolunteerTaskAssignment.query.filter_by(volunteer_id=volunteer.id).order_by(
        VolunteerTaskAssignment.assigned_at.desc(), VolunteerTaskAssignment.id.desc()).limit(12).all()
    return render_template(
        "volunteers/detail.html", volunteer=volunteer, profile=profile, is_admin=is_admin, assignments=assignments,
        summary=volunteer_service.volunteer_summary(volunteer),
    )


# ------------------------------------------------------------ approval queue (administrators)
@bp.route("/applications")
@roles_required(C.ROLE_ADMIN)
def applications():
    q = (request.args.get("q") or "").strip()
    status = request.args.get("status", C.APPLICATION_PENDING)
    page = request.args.get("page", 1, type=int)
    counts = dict(db.session.query(VolunteerProfile.application_status, db.func.count(VolunteerProfile.id)).group_by(
        VolunteerProfile.application_status).all())
    query = _search(_volunteer_query(), q)
    if status in C.VOLUNTEER_APPLICATION_STATUSES:
        query = query.filter(VolunteerProfile.application_status == status)
    oldest_first = status == C.APPLICATION_PENDING
    order = VolunteerProfile.applied_at.asc() if oldest_first else VolunteerProfile.applied_at.desc()
    pagination = query.order_by(order, User.id).paginate(page=page, per_page=current_app.config["PER_PAGE"], error_out=False)
    return render_template("volunteers/applications.html", pagination=pagination, counts=counts, q=q, status=status)


@bp.route("/<int:user_id>/review", methods=["POST"])
@roles_required(C.ROLE_ADMIN)
def review(user_id):
    profile = VolunteerProfile.query.filter_by(user_id=user_id).first_or_404()
    form = VolunteerReviewForm()
    default_url = url_for("volunteers.applications")
    if not form.validate_on_submit():
        flash(first_error(form), "danger")
        return redirect_back(default_url)
    approve = form.decision.data == "approve"
    try:
        volunteer_service.review_application(profile, _actor(), approve, form.note.data)
    except ServiceError as error:
        flash(str(error), "danger")
    else:
        name = profile.user.full_name
        flash(f"{name} was approved as a volunteer." if approve else f"The application of {name} was rejected.", "success")
    return redirect_back(default_url)
