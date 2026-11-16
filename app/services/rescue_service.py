"""Rescue reports: submission, assignment, acceptance, progress and completion."""
import uuid

from flask import current_app
from sqlalchemy import case, or_
from sqlalchemy.orm import joinedload, selectinload

from app import constants as C
from app.extensions import db
from app.models import AnimalReport, RescueActivity, RescueAssignment, User
from app.services import animal_service, audit, notifications, rules, uploads
from app.services.common import ServiceError, like_pattern, link_for, require, transaction
from app.utils import timeutil
from app.utils import validators as V
from app.utils.timeutil import local_today, utcnow


def _report_link(report):
    return link_for("reports.detail", report_id=report.id)


def log_activity(report, actor, activity_type, note=None, old_status=None, new_status=None):
    activity = RescueActivity(
        report=report, actor_id=getattr(actor, "id", None), activity_type=activity_type,
        old_status=old_status, new_status=new_status, note=V.clean_text(note),
    )
    db.session.add(activity)
    return activity


def _apply_status(report, new_status, actor, note=None, activity_type="status_changed", notify_reporter=True):
    """Validated status change + timeline entry + reporter notification (no commit)."""
    old_status = report.status
    require(rules.can_transition_report(old_status, new_status),
            f"A report cannot move from '{old_status}' to '{new_status}'.")
    report.status = new_status
    if new_status in (C.REPORT_CLOSED, C.REPORT_REJECTED, C.REPORT_RESCUED):
        report.closed_at = utcnow() if new_status != C.REPORT_RESCUED else report.closed_at
    log_activity(report, actor, activity_type, note, old_status, new_status)
    if notify_reporter and report.reporter_id:
        notifications.notify(
            report.reporter_id, "Rescue status updated",
            f"Your report {report.report_code} is now '{new_status}'.", C.NOTIFY_RESCUE, _report_link(report),
        )


# -------------------------------------------------------------- submission
def validate_report_data(data):
    """Server-side validation of the public report form. Returns cleaned values."""
    cleaned = {}
    name = V.clean_text(data.get("reporter_name"), 100)
    require(name, "Please enter your name.")
    cleaned["reporter_name"] = name

    phone = V.clean_text(data.get("reporter_phone"), 20)
    require(phone and V.is_valid_phone(phone), "Please enter a valid contact phone number.")
    cleaned["reporter_phone"] = phone

    email = V.normalize_email(data.get("reporter_email"))
    require(not email or V.is_valid_email(email), "Please enter a valid e-mail address or leave it blank.")
    cleaned["reporter_email"] = email or None

    require(data.get("animal_type") in C.ANIMAL_TYPES, "Please choose the type of animal.")
    cleaned["animal_type"] = data["animal_type"]

    description = V.clean_text(data.get("animal_description"))
    require(description and len(description) >= 10, "Please describe the animal (at least 10 characters).")
    cleaned["animal_description"] = description

    cleaned["approximate_age"] = V.clean_text(data.get("approximate_age"), 50)
    require(data.get("animal_condition") in C.ANIMAL_CONDITIONS, "Please choose the animal's condition.")
    cleaned["animal_condition"] = data["animal_condition"]
    require(data.get("emergency_level") in C.EMERGENCY_LEVELS, "Please choose the emergency level.")
    cleaned["emergency_level"] = data["emergency_level"]

    try:
        count = int(data.get("animal_count") or 1)
    except (TypeError, ValueError):
        raise ServiceError("Number of animals must be a whole number.")
    require(1 <= count <= 50, "Number of animals must be between 1 and 50.")
    cleaned["animal_count"] = count

    location_name = V.clean_text(data.get("location_name"), 150)
    require(location_name, "Please enter the location name.")
    cleaned["location_name"] = location_name
    address = V.clean_text(data.get("address"))
    require(address, "Please enter the address or landmark.")
    cleaned["address"] = address

    try:
        cleaned["latitude"], cleaned["longitude"] = V.parse_coordinates(data.get("latitude"), data.get("longitude"))
    except ValueError as error:
        raise ServiceError(str(error))
    cleaned["additional_info"] = V.clean_text(data.get("additional_info"))
    return cleaned


def create_report(data, image_file=None, reporter=None):
    """Save a new rescue report (guests allowed) and alert the administrators."""
    cleaned = validate_report_data(data)
    saved_image = None
    try:
        with transaction():
            saved_image = uploads.save_upload(image_file, C.UPLOAD_ANIMAL_REPORTS, "image")
            report = AnimalReport(
                report_code="TMP-" + uuid.uuid4().hex[:20], reporter_id=getattr(reporter, "id", None),
                status=C.REPORT_PENDING, image_filename=saved_image, **cleaned,
            )
            db.session.add(report)
            db.session.flush()
            report.report_code = V.format_code("RPT", local_today().year, report.id)
            log_activity(report, reporter, "report_submitted", "Report submitted", None, C.REPORT_PENDING)
            notifications.notify_admins(
                f"New rescue report ({report.emergency_level})",
                f"{report.report_code}: {report.animal_type} - {report.animal_condition} at {report.location_name}.",
                C.NOTIFY_RESCUE, _report_link(report),
            )
            if reporter is not None:
                notifications.notify(
                    reporter, "Report received",
                    f"Thank you! Your report {report.report_code} was received and will be reviewed shortly.",
                    C.NOTIFY_RESCUE, _report_link(report),
                )
            audit.log_action("report_submitted", "AnimalReport", report.id, report.report_code, user=reporter)
    except Exception:
        if saved_image:
            uploads.delete_upload(C.UPLOAD_ANIMAL_REPORTS, saved_image)
        raise
    return report


def find_report_for_tracking(code, contact):
    """Guest tracking: a report is returned only if code AND phone/e-mail match."""
    code = (code or "").strip().upper()
    contact = (contact or "").strip().lower()
    if not code or not contact:
        return None
    report = AnimalReport.query.filter_by(report_code=code).first()
    if report is None:
        return None
    phone_digits = "".join(ch for ch in contact if ch.isdigit())
    stored_digits = "".join(ch for ch in (report.reporter_phone or "") if ch.isdigit())
    matches_phone = bool(phone_digits) and len(phone_digits) >= 6 and phone_digits[-10:] == stored_digits[-10:]
    matches_email = bool(report.reporter_email) and contact == report.reporter_email.lower()
    return report if (matches_phone or matches_email) else None


# ------------------------------------------------------------- admin actions
def update_status(report, new_status, actor, note=None):
    """Administrator changes a report's status (validated transitions only)."""
    require(getattr(actor, "role", None) == C.ROLE_ADMIN, "Only an administrator can change a report's status directly.")
    if new_status == C.REPORT_REJECTED:
        require(V.clean_text(note), "Please give a reason for rejecting the report.")
    require(new_status != C.REPORT_ASSIGNED, "Use 'Assign rescuer' to move a report to Assigned.")
    with transaction():
        if new_status in (C.REPORT_UNDER_REVIEW, C.REPORT_CLOSED, C.REPORT_REJECTED):
            cancel_active_assignment(report, actor, "Report status changed by administrator")
        _apply_status(report, new_status, actor, note)
        if new_status == C.REPORT_REJECTED:
            report.rejection_reason = V.clean_text(note)
        audit.log_action("report_status_changed", "AnimalReport", report.id, f"{report.report_code} -> {new_status}", user=actor)
    return report


def cancel_active_assignment(report, actor, note):
    assignment = report.active_assignment
    if assignment is None:
        return None
    assignment.status = C.ASSIGNMENT_CANCELLED
    assignment.responded_at = utcnow()
    assignment.response_note = V.clean_text(note)
    notifications.notify(
        assignment.rescuer_id, "Rescue case withdrawn",
        f"Case {report.report_code} is no longer assigned to you.", C.NOTIFY_RESCUE, _report_link(report),
    )
    return assignment


def assign_rescuer(report, rescuer, actor, deadline=None, instructions=None):
    """Administrator assigns (or reassigns) a verified rescuer to a report."""
    require(getattr(actor, "role", None) == C.ROLE_ADMIN, "Only an administrator can assign rescuers.")
    require(rescuer is not None and rescuer.role == C.ROLE_RESCUER, "Please choose a rescuer.")
    require(rescuer.is_verified and rescuer.is_active, "That rescuer account is not verified / active.")
    require(report.status in (C.REPORT_PENDING, C.REPORT_UNDER_REVIEW, C.REPORT_ASSIGNED, C.REPORT_IN_PROGRESS),
            "This report can no longer be assigned.")
    if deadline is not None:
        require(deadline > utcnow(), "The deadline must be in the future.")
    with transaction():
        if report.active_assignment is not None:  # reassignment
            cancel_active_assignment(report, actor, "Reassigned to another rescuer")
            if report.status in (C.REPORT_ASSIGNED, C.REPORT_IN_PROGRESS):
                _apply_status(report, C.REPORT_UNDER_REVIEW, actor, "Reassignment", "reassigned", notify_reporter=False)
        assignment = RescueAssignment(
            report=report, rescuer_id=rescuer.id, assigned_by=actor.id, status=C.ASSIGNMENT_ASSIGNED,
            deadline=deadline, instructions=V.clean_text(instructions),
        )
        db.session.add(assignment)
        _apply_status(report, C.REPORT_ASSIGNED, actor, f"Assigned to {rescuer.full_name}", "assigned")
        notifications.notify(
            rescuer, "New rescue case assigned",
            f"{report.report_code}: {report.animal_type} ({report.emergency_level}) at {report.location_name}. Please accept or decline.",
            C.NOTIFY_RESCUE, _report_link(report),
        )
        audit.log_action("rescuer_assigned", "AnimalReport", report.id, f"{report.report_code} -> {rescuer.full_name}", user=actor)
    return assignment


# ----------------------------------------------------------- rescuer actions
def respond_to_assignment(assignment, actor, accept, note=None):
    """The assigned rescuer accepts or declines the case."""
    require(assignment.rescuer_id == getattr(actor, "id", None), "This case is not assigned to you.")
    require(assignment.status == C.ASSIGNMENT_ASSIGNED, "This assignment has already been answered.")
    report = assignment.report
    if not accept:
        require(V.clean_text(note), "Please tell the administrator why you cannot take this case.")
    with transaction():
        assignment.responded_at = utcnow()
        assignment.response_note = V.clean_text(note)
        if accept:
            assignment.status = C.ASSIGNMENT_ACCEPTED
            _apply_status(report, C.REPORT_IN_PROGRESS, actor, "Rescuer accepted the case", "accepted")
            notifications.notify_admins(
                "Rescue case accepted", f"{actor.full_name} accepted {report.report_code}.", C.NOTIFY_RESCUE, _report_link(report))
        else:
            assignment.status = C.ASSIGNMENT_REJECTED
            _apply_status(report, C.REPORT_UNDER_REVIEW, actor, f"Declined by rescuer: {V.clean_text(note)}", "rejected", notify_reporter=False)
            notifications.notify_admins(
                "Rescue case declined",
                f"{actor.full_name} declined {report.report_code}: {V.clean_text(note)}. Please assign another rescuer.",
                C.NOTIFY_RESCUE, _report_link(report))
        audit.log_action("assignment_accepted" if accept else "assignment_declined", "AnimalReport", report.id, report.report_code, user=actor)
    return assignment


def _may_work_on(report, actor):
    """Admin, or a rescuer who has an accepted / completed assignment on the report."""
    if getattr(actor, "role", None) == C.ROLE_ADMIN:
        return True
    return any(
        a.rescuer_id == getattr(actor, "id", None) and a.status in (C.ASSIGNMENT_ACCEPTED, C.ASSIGNMENT_COMPLETED)
        for a in report.assignments
    )


def add_note(report, actor, note):
    note = V.clean_text(note)
    require(note, "Please write a note first.")
    viewer_ok = _may_work_on(report, actor) or any(a.rescuer_id == getattr(actor, "id", None) for a in report.assignments)
    require(viewer_ok, "You are not allowed to add notes to this report.")
    with transaction():
        log_activity(report, actor, "note", note)
        audit.log_action("rescue_note_added", "AnimalReport", report.id, report.report_code, user=actor)
    return report


def complete_rescue(report, actor, completion_details, rescued=True):
    """Record the rescue result. ``rescued=False`` closes the case (animal not found / not rescuable)."""
    require(_may_work_on(report, actor), "Only the assigned rescuer or an administrator can complete this rescue.")
    require(report.status == C.REPORT_IN_PROGRESS, "Only a rescue that is in progress can be completed.")
    details = V.clean_text(completion_details)
    require(details, "Please describe the outcome of the rescue.")
    with transaction():
        assignment = report.active_assignment
        if assignment is not None:
            assignment.status = C.ASSIGNMENT_COMPLETED
            assignment.completed_at = utcnow()
            assignment.completion_details = details
        target = C.REPORT_RESCUED if rescued else C.REPORT_CLOSED
        _apply_status(report, target, actor, details, "completed")
        if not rescued:
            report.closed_at = utcnow()
        notifications.notify_admins(
            "Rescue completed" if rescued else "Rescue case closed",
            f"{report.report_code}: {details[:140]}", C.NOTIFY_RESCUE, _report_link(report))
        audit.log_action("rescue_completed", "AnimalReport", report.id, f"{report.report_code} rescued={rescued}", user=actor)
    return report


def register_rescued_animal(report, actor, data, image_files=None):
    """Create the permanent animal record for a rescued animal and link it to the report."""
    require(report.status in (C.REPORT_IN_PROGRESS, C.REPORT_RESCUED), "Animals can only be registered for a report that is in progress or rescued.")
    require(_may_work_on(report, actor), "Only the assigned rescuer or an administrator can register the animal.")
    animal = animal_service.create_animal(data, actor, report=report, image_files=image_files)
    with transaction():
        log_activity(report, actor, "animal_registered", f"Animal registered: {animal.display_name} ({animal.animal_code})")
        if report.reporter_id:
            notifications.notify(
                report.reporter_id, "Your rescued animal is safe",
                f"The animal from report {report.report_code} has been registered as {animal.animal_code}.",
                C.NOTIFY_RESCUE, _report_link(report))
    return animal


# --------------------------------------------------------------------- access
def can_view_report(user, report):
    """Who may open the full report details page."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if user.role == C.ROLE_ADMIN:
        return True
    if report.reporter_id == user.id:
        return True
    if user.role == C.ROLE_RESCUER and user.is_verified:
        return True
    return False


def can_work_on(report, user):
    """True for an administrator or the rescuer who accepted the case (may add notes, complete, register animals)."""
    return _may_work_on(report, user)


def can_see_reporter_contact(user, report):
    """The reporter's phone / e-mail: administrators, the reporter, and a rescuer who has been given the case."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if user.role == C.ROLE_ADMIN or (report.reporter_id is not None and report.reporter_id == user.id):
        return True
    return user.role == C.ROLE_RESCUER and any(
        a.rescuer_id == user.id and a.status in (C.ASSIGNMENT_ASSIGNED, C.ASSIGNMENT_ACCEPTED, C.ASSIGNMENT_COMPLETED)
        for a in report.assignments
    )


# ------------------------------------------------------------------- lookups
def _priority_rank():
    """SQL ordering key: Critical first, Low last."""
    return case(*[(AnimalReport.emergency_level == level, rank) for level, rank in C.EMERGENCY_RANK.items()], else_=99)


def available_rescuers():
    """Verified, active rescuers an administrator can assign cases to."""
    return User.query.filter_by(
        role=C.ROLE_RESCUER, status=C.ACCOUNT_ACTIVE, verification_status=C.VERIFY_VERIFIED
    ).order_by(User.full_name).all()


def rescuer_workload():
    """``{rescuer_id: cases waiting for a reply or in progress}``."""
    rows = (
        db.session.query(RescueAssignment.rescuer_id, db.func.count(RescueAssignment.id))
        .filter(RescueAssignment.status.in_(C.ACTIVE_ASSIGNMENT_STATUSES))
        .group_by(RescueAssignment.rescuer_id)
        .all()
    )
    return {rescuer_id: count for rescuer_id, count in rows}


def status_counts():
    """``{report status: number of reports}`` (every status is present, even with 0)."""
    rows = db.session.query(AnimalReport.status, db.func.count(AnimalReport.id)).group_by(AnimalReport.status).all()
    counts = {status: 0 for status in C.REPORT_STATUSES}
    counts.update({status: count for status, count in rows})
    return counts


def search_reports(q=None, status=None, emergency=None, animal_type=None, reporter_id=None, priority_first=False):
    """Filtered query of reports.

    ``status`` may be ``"open"`` (every unfinished report), one real status, or empty for all reports.
    ``priority_first`` lists the most urgent (then oldest) reports first - the order for triage.
    """
    query = AnimalReport.query.options(selectinload(AnimalReport.assignments).joinedload(RescueAssignment.rescuer))
    if reporter_id is not None:
        query = query.filter(AnimalReport.reporter_id == reporter_id)
    if status == "open":
        query = query.filter(AnimalReport.status.in_(C.OPEN_REPORT_STATUSES))
    elif status in C.REPORT_STATUSES:
        query = query.filter(AnimalReport.status == status)
    if emergency in C.EMERGENCY_LEVELS:
        query = query.filter(AnimalReport.emergency_level == emergency)
    if animal_type in C.ANIMAL_TYPES:
        query = query.filter(AnimalReport.animal_type == animal_type)
    q = (q or "").strip()
    if q:
        pattern = like_pattern(q)
        query = query.filter(or_(
            AnimalReport.report_code.ilike(pattern, escape="\\"),
            AnimalReport.location_name.ilike(pattern, escape="\\"),
            AnimalReport.address.ilike(pattern, escape="\\"),
            AnimalReport.animal_description.ilike(pattern, escape="\\"),
        ))
    if priority_first:
        return query.order_by(_priority_rank(), AnimalReport.created_at.asc(), AnimalReport.id.asc())
    return query.order_by(AnimalReport.created_at.desc(), AnimalReport.id.desc())


def assignments_for(rescuer, active=True):
    """A rescuer's assignments: the ones waiting for a reply / in progress, or the finished ones."""
    query = (
        RescueAssignment.query.join(AnimalReport, RescueAssignment.report_id == AnimalReport.id)
        .options(joinedload(RescueAssignment.report))
        .filter(RescueAssignment.rescuer_id == rescuer.id)
    )
    if active:
        waiting_first = case((RescueAssignment.status == C.ASSIGNMENT_ASSIGNED, 0), else_=1)
        return query.filter(RescueAssignment.status.in_(C.ACTIVE_ASSIGNMENT_STATUSES)).order_by(
            waiting_first, _priority_rank(), RescueAssignment.assigned_at.asc())
    finished = db.func.coalesce(RescueAssignment.completed_at, RescueAssignment.responded_at, RescueAssignment.assigned_at)
    return query.filter(~RescueAssignment.status.in_(C.ACTIVE_ASSIGNMENT_STATUSES)).order_by(finished.desc(), RescueAssignment.id.desc())


# ------------------------------------------------------- progress and timelines
PROGRESS_LABELS = ("Received", "Under review", "Rescuer assigned", "Rescue in progress", "Rescued")
_PROGRESS_POSITION = {
    C.REPORT_PENDING: 0, C.REPORT_UNDER_REVIEW: 1, C.REPORT_ASSIGNED: 2, C.REPORT_IN_PROGRESS: 3, C.REPORT_RESCUED: 4,
}
_PUBLIC_TITLES = {
    C.REPORT_PENDING: "Report received",
    C.REPORT_UNDER_REVIEW: "Being reviewed by the rescue team",
    C.REPORT_ASSIGNED: "A rescuer has been assigned",
    C.REPORT_IN_PROGRESS: "Rescue in progress",
    C.REPORT_RESCUED: "The animal was rescued",
    C.REPORT_CLOSED: "Case closed",
    C.REPORT_REJECTED: "The report could not be accepted",
}
_ACTIVITY_LOOK = {
    "report_submitted": ("bi-megaphone", "green"),
    "assigned": ("bi-person-check", "blue"),
    "reassigned": ("bi-arrow-repeat", "amber"),
    "accepted": ("bi-hand-thumbs-up", "green"),
    "rejected": ("bi-x-circle", "amber"),
    "completed": ("bi-check2-circle", "green"),
    "animal_registered": ("bi-heart-pulse", "green"),
    "note": ("bi-chat-left-text", "gray"),
    "status_changed": ("bi-arrow-right-circle", "blue"),
}
_STATUS_TONES = {C.REPORT_REJECTED: "coral", C.REPORT_CLOSED: "gray", C.REPORT_RESCUED: "green"}


def _stamp(value):
    offset = current_app.config.get("DISPLAY_UTC_OFFSET_MINUTES", timeutil.DEFAULT_OFFSET_MINUTES)
    return timeutil.format_datetime(value, offset) if value else ""


def _look(activity, public=False):
    """``(icon, tone)`` for one timeline entry."""
    icon, tone = _ACTIVITY_LOOK.get(activity.activity_type, _ACTIVITY_LOOK["status_changed"])
    if public and activity.activity_type in ("rejected", "reassigned"):
        icon, tone = "bi-search", "blue"  # a declined / reassigned case simply goes back to review
    if activity.new_status == C.REPORT_CLOSED:
        icon = "bi-archive"
    return icon, _STATUS_TONES.get(activity.new_status, tone)


def progress_steps(report):
    """The five-step progress bar: ``[{label, state}]`` with state ``done`` / ``current`` / ``todo``.

    Rejected reports, and reports closed without a rescue, highlight nothing (the page shows a notice instead).
    """
    if report.status in _PROGRESS_POSITION:
        current = _PROGRESS_POSITION[report.status]
    elif report.status == C.REPORT_CLOSED and any(a.new_status == C.REPORT_RESCUED for a in report.activities):
        current = len(PROGRESS_LABELS) - 1
    else:
        current = None
    steps = []
    for index, label in enumerate(PROGRESS_LABELS):
        if current is None or index > current:
            state = "todo"
        elif index < current or index == len(PROGRESS_LABELS) - 1:
            state = "done"
        else:
            state = "current"
        steps.append({"label": label, "state": state})
    return steps


def public_timeline(report):
    """What the reporter (or a guest who tracks the report) may see: status changes only.

    No staff names, no internal notes and no one else's contact details. Newest entry first.
    """
    items = []
    for activity in report.activities:
        if activity.activity_type == "note":
            continue
        text = None
        if activity.activity_type == "animal_registered":
            title = "The animal was registered in our records"
        elif activity.new_status:
            title = _PUBLIC_TITLES.get(activity.new_status, activity.new_status)
            if activity.new_status == C.REPORT_REJECTED and report.rejection_reason:
                text = report.rejection_reason
        else:
            continue
        icon, tone = _look(activity, public=True)
        items.append({"title": title, "text": text, "time": _stamp(activity.created_at), "icon": icon, "tone": tone})
    items.reverse()
    return items


def staff_timeline(report):
    """Full activity log for administrators and rescuers (who did what, with notes). Newest first."""
    items = []
    for activity in report.activities:
        icon, tone = _look(activity)
        who = activity.actor.full_name if activity.actor is not None else "Guest reporter"
        if activity.activity_type == "note":
            title = f"Note from {who}"
        elif activity.old_status and activity.new_status:
            title = f"{activity.old_status} → {activity.new_status}"
        elif activity.new_status:
            title = activity.new_status
        else:
            title = activity.activity_type.replace("_", " ").capitalize()
        text = activity.note or ""
        if activity.activity_type != "note":
            text = f"{who}: {text}" if text else who
        items.append({"title": title, "text": text, "time": _stamp(activity.created_at), "icon": icon, "tone": tone})
    items.reverse()
    return items


def map_markers(reports):
    """Reports that have coordinates, as plain dicts for the Leaflet map (no contact details)."""
    from flask import url_for  # local import keeps the service importable without a request context

    markers = []
    for report in reports:
        if not report.has_location:
            continue
        markers.append({
            "id": report.id,
            "code": report.report_code,
            "lat": report.latitude,
            "lng": report.longitude,
            "level": report.emergency_level,
            "color": C.EMERGENCY_COLORS.get(report.emergency_level, "#1f9d63"),
            "status": report.status,
            "title": f"{report.animal_type} - {report.animal_condition}",
            "place": report.location_name,
            "url": url_for("reports.detail", report_id=report.id),
        })
    return markers
