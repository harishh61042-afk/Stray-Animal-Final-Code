"""Rescue reports: the public report form, tracking by report ID, and the report details page."""
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user

from app import constants as C
from app.extensions import db
from app.forms import form_data
from app.forms.rescue import ReportForm, TrackForm
from app.models import AnimalReport
from app.services import rescue_service, rules
from app.services.common import ServiceError
from app.utils import ratelimit
from app.utils.permissions import login_required

bp = Blueprint("reports", __name__)

# statuses an administrator may choose directly (assigning goes through "Assign rescuer", completing through the rescuer)
DIRECT_STATUSES = (C.REPORT_UNDER_REVIEW, C.REPORT_CLOSED, C.REPORT_REJECTED)


@bp.route("/report", methods=["GET", "POST"])
def new():
    """Anyone can report an animal - no account needed."""
    initial = {}
    if current_user.is_authenticated:
        initial = {
            "reporter_name": current_user.full_name,
            "reporter_phone": current_user.phone or "",
            "reporter_email": current_user.email,
        }
    form = ReportForm(data=initial)
    if form.validate_on_submit():
        if form.website.data:  # the hidden "website" field is only ever filled in by bots
            flash("Your report could not be submitted. Please try again.", "danger")
        else:
            reporter = current_user._get_current_object() if current_user.is_authenticated else None
            try:
                report = rescue_service.create_report(form_data(form), request.files.get(form.image.name), reporter=reporter)
            except ServiceError as error:
                flash(str(error), "danger")
            else:
                session["last_report_code"] = report.report_code
                return redirect(url_for("reports.submitted", code=report.report_code))
    elif request.method == "POST":
        flash("Please fix the highlighted fields and send the report again.", "danger")
    return render_template("reports/new.html", form=form, levels=C.EMERGENCY_LEVELS)


@bp.route("/report/submitted/<code>")
def submitted(code):
    """Confirmation page - only shown to the browser that has just submitted this report."""
    if session.get("last_report_code") != code:
        abort(404)
    report = AnimalReport.query.filter_by(report_code=code).first_or_404()
    return render_template("reports/submitted.html", report=report)


@bp.route("/track", methods=["GET", "POST"])
def track():
    """Follow a report with its ID plus the phone number or e-mail that was given when reporting."""
    form = TrackForm()
    report = None
    if request.method == "GET" and request.args.get("code"):
        form.code.data = request.args.get("code", "")[:30]
    if form.validate_on_submit():
        key = request.remote_addr or "unknown"
        if ratelimit.track_limiter.blocked(key):
            flash("Too many attempts. Please wait a few minutes before trying again.", "warning")
        else:
            report = rescue_service.find_report_for_tracking(form.code.data, form.contact.data)
            if report is None:
                ratelimit.track_limiter.hit(key)
                flash("We could not find a report with that ID and contact. Please check the ID on your confirmation "
                      "and use the same phone number or e-mail you gave when you reported.", "warning")
    return render_template(
        "reports/track.html", form=form, report=report,
        steps=rescue_service.progress_steps(report) if report else [],
        timeline=rescue_service.public_timeline(report) if report else [],
    )


@bp.route("/reports/mine")
@login_required
def mine():
    """Reports submitted by the signed-in user."""
    status = request.args.get("status", "")
    page = request.args.get("page", 1, type=int)
    query = rescue_service.search_reports(status=status or None, reporter_id=current_user.id)
    pagination = query.paginate(page=page, per_page=current_app.config["PER_PAGE"], error_out=False)
    counts = {
        name: count for name, count in db.session.query(AnimalReport.status, db.func.count(AnimalReport.id))
        .filter(AnimalReport.reporter_id == current_user.id).group_by(AnimalReport.status).all()
    }
    return render_template("reports/mine.html", pagination=pagination, status=status, counts=counts,
                           total=sum(counts.values()), statuses=C.REPORT_STATUSES)


@bp.route("/reports/<int:report_id>")
@login_required
def detail(report_id):
    report = db.get_or_404(AnimalReport, report_id)
    user = current_user._get_current_object()
    if not rescue_service.can_view_report(user, report):
        abort(403)

    is_admin = user.role == C.ROLE_ADMIN
    is_staff = is_admin or user.role == C.ROLE_RESCUER
    can_work = rescue_service.can_work_on(report, user)
    involved = can_work or any(a.rescuer_id == user.id for a in report.assignments)
    assignment = report.active_assignment or report.latest_assignment
    awaiting_reply = next(
        (a for a in report.assignments if a.rescuer_id == user.id and a.status == C.ASSIGNMENT_ASSIGNED), None)
    can_assign = is_admin and report.status in C.OPEN_REPORT_STATUSES

    context = {
        "report": report,
        "assignment": assignment,
        "awaiting_reply": awaiting_reply,
        "is_admin": is_admin,
        "is_staff": is_staff,
        "show_contact": rescue_service.can_see_reporter_contact(user, report),
        "can_assign": can_assign,
        "can_note": involved,
        "can_complete": can_work and report.status == C.REPORT_IN_PROGRESS,
        "can_register_animal": can_work and report.status in (C.REPORT_IN_PROGRESS, C.REPORT_RESCUED),
        "status_options": [s for s in rules.allowed_report_transitions(report.status) if s in DIRECT_STATUSES] if is_admin else [],
        "rescuers": rescue_service.available_rescuers() if can_assign else [],
        "workload": rescue_service.rescuer_workload() if can_assign else {},
        "steps": rescue_service.progress_steps(report),
        "timeline": rescue_service.staff_timeline(report) if is_staff else rescue_service.public_timeline(report),
        "animals": list(report.animals),
    }
    return render_template("reports/detail.html", **context)
