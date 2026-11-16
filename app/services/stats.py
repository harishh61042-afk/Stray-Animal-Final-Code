"""Numbers shown on the public site and on the dashboards.

Everything is counted from the database - nothing here is a made-up figure. Queries use only portable
SQLAlchemy constructs (monthly buckets are made in Python), so they behave the same on MySQL and SQLite.
"""
from datetime import date, datetime, time, timedelta

from flask import current_app

from app import constants as C
from app.extensions import db
from app.models import (
    AdoptionApplication, AdoptionRecord, Animal, AnimalReport, AuditLog, ContactMessage, MedicalRecord,
    RescueAssignment, ShelterAdmission, ShelterProfile, User, VolunteerProfile, VolunteerTask,
    VolunteerTaskAssignment,
)
from app.services import animal_service, medical_service, rules, volunteer_service
from app.utils import timeutil
from app.utils.timeutil import local_today, month_start, to_local, utcnow

IN_CARE_STATUSES = (C.ANIMAL_RESCUED, C.ANIMAL_TREATMENT, C.ANIMAL_RECOVERING, C.ANIMAL_IN_SHELTER)
GREEN, TEAL, AMBER, CORAL, BLUE, VIOLET = "#1f9d63", "#0ea5a4", "#f59f00", "#e5484d", "#3b82f6", "#8b5cf6"
REPORT_STATUS_COLORS = {
    C.REPORT_PENDING: AMBER, C.REPORT_UNDER_REVIEW: BLUE, C.REPORT_ASSIGNED: VIOLET, C.REPORT_IN_PROGRESS: TEAL,
    C.REPORT_RESCUED: GREEN, C.REPORT_CLOSED: "#64748b", C.REPORT_REJECTED: CORAL,
}
ANIMAL_STATUS_COLORS = {
    C.ANIMAL_REPORTED: AMBER, C.ANIMAL_RESCUED: BLUE, C.ANIMAL_TREATMENT: CORAL, C.ANIMAL_RECOVERING: TEAL,
    C.ANIMAL_IN_SHELTER: VIOLET, C.ANIMAL_AVAILABLE: GREEN, C.ANIMAL_ADOPTED: "#64748b",
}
ADOPTION_STATUS_COLORS = {
    C.ADOPTION_PENDING: AMBER, C.ADOPTION_UNDER_REVIEW: BLUE, C.ADOPTION_APPROVED: TEAL,
    C.ADOPTION_REJECTED: CORAL, C.ADOPTION_COMPLETED: GREEN, C.ADOPTION_CANCELLED: "#64748b",
}


# ------------------------------------------------------------------ helpers
def _offset():
    return current_app.config.get("DISPLAY_UTC_OFFSET_MINUTES", timeutil.DEFAULT_OFFSET_MINUTES)


def pct_change(current, previous):
    """Percent change against the previous period, or ``None`` when there is nothing to compare with."""
    if not previous:
        return None
    return round((current - previous) * 100 / previous)


def percent(part, whole):
    return round(part * 100 / whole) if whole else 0


def group_counts(column, *conditions):
    """``{value: row count}`` for one column."""
    rows = db.session.query(column, db.func.count(column)).filter(*conditions).group_by(column).all()
    return {value: count for value, count in rows}


def month_keys(months=12):
    """``[(year, month), ...]`` for the last ``months`` calendar months (local time), oldest first."""
    today = local_today(_offset())
    return [(first.year, first.month) for first in (month_start(today, back) for back in range(months - 1, -1, -1))]


def monthly_series(column, months=12, conditions=(), value=None):
    """Rows (or the sum of ``value``) per calendar month for the last ``months`` months.

    Returns ``{"labels": [...], "values": [...]}`` with the oldest month first. Works with DateTime and Date columns.
    """
    offset = _offset()
    keys = month_keys(months)
    first_day = month_start(local_today(offset), months - 1)
    is_datetime = isinstance(column.type, db.DateTime)
    lower = datetime.combine(first_day, time.min) - timedelta(minutes=offset) if is_datetime else first_day
    query = db.session.query(column, value) if value is not None else db.session.query(column)
    totals = {}
    for row in query.filter(column >= lower, *conditions).all():
        stamp = row[0]
        if stamp is None:
            continue
        local = to_local(stamp, offset) if is_datetime else stamp
        key = (local.year, local.month)
        totals[key] = totals.get(key, 0) + ((row[1] or 0) if value is not None else 1)
    labels = []
    for index, (year, month) in enumerate(keys):
        name = date(year, month, 1).strftime("%b")
        labels.append(f"{name} '{str(year)[2:]}" if index == 0 or month == 1 else name)
    values = [round(totals.get(key, 0), 1) if value is not None else totals.get(key, 0) for key in keys]
    return {"labels": labels, "values": values}


def period_label(months=12):
    keys = month_keys(months)
    first, last = date(keys[0][0], keys[0][1], 1), date(keys[-1][0], keys[-1][1], 1)
    return f"{first.strftime('%b %Y')} - {last.strftime('%b %Y')}"


# ----------------------------------------------------------------- public site
def verified_shelter_count():
    return ShelterProfile.query.join(User, ShelterProfile.user_id == User.id).filter(
        User.status == C.ACCOUNT_ACTIVE, User.verification_status == C.VERIFY_VERIFIED).count()


def approved_volunteer_count():
    return VolunteerProfile.query.join(User, VolunteerProfile.user_id == User.id).filter(
        User.status == C.ACCOUNT_ACTIVE, VolunteerProfile.application_status == C.APPLICATION_APPROVED).count()


def public_overview():
    """Headline numbers for the home page."""
    return {
        "reports": AnimalReport.query.count(),
        "rescued": Animal.query.filter(Animal.status != C.ANIMAL_REPORTED).count(),
        "adopted": AdoptionRecord.query.count(),
        "available": Animal.query.filter(Animal.status == C.ANIMAL_AVAILABLE).count(),
        "volunteers": approved_volunteer_count(),
        "shelters": verified_shelter_count(),
    }


# ------------------------------------------------------------- activity feed
ACTIVITY_TITLES = {
    "report_submitted": "Submitted a rescue report", "report_status_changed": "Changed a report's status",
    "rescuer_assigned": "Assigned a rescuer", "assignment_accepted": "Accepted a rescue assignment",
    "rescue_completed": "Completed a rescue", "rescue_note_added": "Added a rescue note",
    "animal_registered": "Registered an animal", "animal_updated": "Updated an animal",
    "animal_status_changed": "Changed an animal's status", "animal_admitted": "Admitted an animal to a shelter",
    "animal_discharged": "Discharged an animal", "animal_photos_added": "Added animal photos",
    "animal_photo_deleted": "Removed an animal photo", "animal_cover_changed": "Changed a cover photo",
    "vet_assigned": "Assigned a veterinarian", "rehabilitation_updated": "Updated rehabilitation",
    "medical_record_added": "Added a medical record", "medical_record_updated": "Updated a medical record",
    "vaccination_added": "Recorded a vaccination", "vaccination_deleted": "Removed a vaccination",
    "adoption_applied": "Applied to adopt an animal", "adoption_under_review": "Started reviewing an application",
    "adoption_approved": "Approved an adoption", "adoption_rejected": "Rejected an adoption",
    "adoption_cancelled": "Cancelled an application", "adoption_completed": "Completed an adoption",
    "task_created": "Created a volunteer task", "task_updated": "Updated a volunteer task",
    "task_assigned": "Assigned a volunteer", "task_accepted": "Accepted a task", "task_declined": "Declined a task",
    "task_progress": "Updated task progress", "task_completed": "Completed a task", "task_cancelled": "Cancelled a task",
    "task_volunteer_removed": "Removed a volunteer from a task",
    "volunteer_application_submitted": "Applied to volunteer",
    "volunteer_application_reviewed": "Reviewed a volunteer application",
    "user_registered": "Registered an account", "account_verified": "Verified an account",
    "account_verification_rejected": "Rejected a verification", "account_status_changed": "Changed an account status",
    "account_locked": "Account locked after failed sign-ins", "password_changed": "Changed a password",
    "password_reset_by_admin": "Reset a password", "profile_updated": "Updated a profile",
    "contact_message_received": "Contact message received", "contact_message_status": "Updated a contact message",
    "user_created_by_admin": "Created an account", "notification_broadcast": "Sent a notice to users",
    "data_exported": "Exported data", "login": "Signed in", "shelter_updated": "Updated a shelter",
}
KIND_PREFIXES = (
    ("Rescue", ("report_", "rescue", "assignment_")), ("Adoption", ("adoption_",)),
    ("Animals", ("animal_", "rehabilitation_", "vet_")), ("Medical", ("medical_", "vaccination_")),
    ("Volunteers", ("task_", "volunteer_")), ("Accounts", ("user_", "account_", "password_", "profile_")),
)
KIND_TONES = {"Rescue": "primary", "Adoption": "success", "Animals": "info", "Medical": "danger",
              "Volunteers": "warning", "Accounts": "secondary", "System": "dark"}


def activity_kind(action):
    for kind, prefixes in KIND_PREFIXES:
        if action.startswith(prefixes):
            return kind
    return "System"


def recent_activity(limit=8):
    """Latest entries of the audit log (sign-ins are left out because they are noise)."""
    rows = AuditLog.query.filter(AuditLog.action != "login").order_by(
        AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).all()
    feed = []
    for row in rows:
        kind = activity_kind(row.action)
        feed.append({
            "who": row.user.full_name if row.user else "System",
            "title": ACTIVITY_TITLES.get(row.action) or row.action.replace("_", " ").capitalize(),
            "detail": row.description, "kind": kind, "tone": KIND_TONES[kind], "when": row.created_at,
        })
    return feed


def kinds_in(feed):
    return sorted({item["kind"] for item in feed})


# ----------------------------------------------------------------- administrator
def top_shelters(limit=3):
    counts = animal_service.occupancy_counts()
    rows = [{"shelter": shelter, "count": counts.get(shelter.id, 0),
             "percent": rules.occupancy_percent(shelter.capacity, counts.get(shelter.id, 0))}
            for shelter in animal_service.verified_shelters()]
    rows.sort(key=lambda row: (-row["percent"], row["shelter"].shelter_name))
    return rows[:limit]


def admin_dashboard():
    reports = monthly_series(AnimalReport.created_at, 12)
    animals = monthly_series(Animal.created_at, 12)
    adoptions = monthly_series(AdoptionRecord.adoption_date, 12)
    volunteer_signups = monthly_series(VolunteerProfile.applied_at, 12)

    open_query = AnimalReport.query.filter(AnimalReport.status.in_(C.OPEN_REPORT_STATUSES))
    open_reports = open_query.count()
    critical = open_query.filter(AnimalReport.emergency_level == C.EMERGENCY_CRITICAL).count()
    animal_status = group_counts(Animal.status)
    total_animals = sum(animal_status.values())
    in_care = sum(animal_status.get(status, 0) for status in IN_CARE_STATUSES)
    available = animal_status.get(C.ANIMAL_AVAILABLE, 0)
    adopted_total = AdoptionRecord.query.count()
    volunteers = approved_volunteer_count()
    pending_volunteers = VolunteerProfile.query.filter_by(application_status=C.APPLICATION_PENDING).count()

    kpis = [
        {"label": "Open reports", "value": open_reports, "icon": "bi-life-preserver", "tone": "coral",
         "series": reports["values"][-8:], "hint": f"{critical} critical" if critical else "None critical",
         "href": "rescue.manage"},
        {"label": "Animals in care", "value": in_care, "icon": "bi-heart-pulse", "tone": "teal",
         "series": animals["values"][-8:], "hint": f"{available} ready for adoption", "href": "animals.index"},
        {"label": "Adoptions completed", "value": adopted_total, "icon": "bi-balloon-heart", "tone": "green",
         "series": adoptions["values"][-8:], "delta": pct_change(adoptions["values"][-1], adoptions["values"][-2]),
         "hint": f"{adoptions['values'][-1]} this month", "href": "adoption.records"},
        {"label": "Approved volunteers", "value": volunteers, "icon": "bi-people", "tone": "blue",
         "series": volunteer_signups["values"][-8:],
         "hint": f"{pending_volunteers} application{'s' if pending_volunteers != 1 else ''} waiting",
         "href": "volunteers.index"},
    ]

    report_status = group_counts(AnimalReport.status)
    status_labels = [s for s in C.REPORT_STATUSES if report_status.get(s)]
    report_total = sum(report_status.values())
    type_counts = sorted(group_counts(Animal.animal_type).items(), key=lambda item: (-item[1], item[0]))[:6]
    top_count = type_counts[0][1] if type_counts else 0

    care_groups = (
        ("Adopted", [C.ANIMAL_ADOPTED], VIOLET), ("Available", [C.ANIMAL_AVAILABLE], GREEN),
        ("In care", list(IN_CARE_STATUSES), TEAL), ("Reported", [C.ANIMAL_REPORTED], AMBER),
    )
    care_dots = []
    for label, statuses, color in care_groups:
        value = sum(animal_status.get(status, 0) for status in statuses)
        care_dots.append({"label": label, "value": value, "pct": percent(value, total_animals), "color": color})

    today = local_today(_offset())
    attention = [
        {"label": "Reports waiting for review", "icon": "bi-inbox", "endpoint": "rescue.manage",
         "args": {"status": C.REPORT_PENDING}, "count": report_status.get(C.REPORT_PENDING, 0)},
        {"label": "Accounts waiting for verification", "icon": "bi-patch-check", "endpoint": "admin.verifications",
         "args": {}, "count": User.query.filter(User.verification_status == C.VERIFY_PENDING).count()},
        {"label": "Volunteer applications", "icon": "bi-person-lines-fill", "endpoint": "volunteers.applications",
         "args": {}, "count": pending_volunteers},
        {"label": "Adoption requests to review", "icon": "bi-balloon-heart", "endpoint": "adoption.manage", "args": {},
         "count": AdoptionApplication.query.filter(AdoptionApplication.status.in_(
             [C.ADOPTION_PENDING, C.ADOPTION_UNDER_REVIEW])).count()},
        {"label": "New contact messages", "icon": "bi-envelope", "endpoint": "admin.messages", "args": {},
         "count": ContactMessage.query.filter_by(status=C.CONTACT_NEW).count()},
        {"label": "Overdue vaccinations", "icon": "bi-shield-exclamation", "endpoint": "medical.vaccinations",
         "args": {}, "count": len([v for v in medical_service.due_vaccinations(within_days=0) if v.next_due_date < today])},
        {"label": "Overdue volunteer tasks", "icon": "bi-alarm", "endpoint": "tasks.manage", "args": {},
         "count": VolunteerTask.query.filter(
             VolunteerTask.due_at.isnot(None), VolunteerTask.due_at < utcnow(),
             VolunteerTask.status.notin_([C.TASK_COMPLETED, C.TASK_CANCELLED])).count()},
    ]
    feed = recent_activity(8)
    return {
        "period": period_label(12), "kpis": kpis, "open_reports": open_reports, "critical": critical,
        "report_total_12m": sum(reports["values"]),
        "activity_chart": {"type": "bar", "labels": reports["labels"], "datasets": [
            {"label": "Reports received", "data": reports["values"], "color": GREEN},
            {"label": "Animals registered", "data": animals["values"], "color": BLUE}], "legend": False},
        "adoption_chart": {"type": "line", "labels": adoptions["labels"], "datasets": [
            {"label": "Adoptions", "data": adoptions["values"], "color": BLUE}], "legend": False},
        "adopted_total": adopted_total, "adoptions_this_month": adoptions["values"][-1],
        "adoption_delta": pct_change(adoptions["values"][-1], adoptions["values"][-2]),
        "status_chart": {"type": "doughnut", "labels": status_labels, "datasets": [
            {"label": "Reports", "data": [report_status[s] for s in status_labels],
             "colors": [REPORT_STATUS_COLORS[s] for s in status_labels]}],
         "center": {"text": str(report_total), "title": "reports"}},
        "status_legend": [{"label": s, "value": report_status[s], "color": REPORT_STATUS_COLORS[s]} for s in status_labels],
        "report_total": report_total,
        "type_bars": [{"label": name, "value": count, "pct": percent(count, top_count)} for name, count in type_counts],
        "care_dots": care_dots, "care_score": percent(available + animal_status.get(C.ANIMAL_ADOPTED, 0), total_animals),
        "total_animals": total_animals, "attention": attention,
        "attention_total": sum(item["count"] for item in attention),
        "feed": feed, "feed_kinds": kinds_in(feed), "top_shelters": top_shelters(3),
    }


# --------------------------------------------------------------------- rescuer
def rescuer_dashboard(user):
    base = RescueAssignment.query.filter(RescueAssignment.rescuer_id == user.id)
    awaiting = base.filter(RescueAssignment.status == C.ASSIGNMENT_ASSIGNED).order_by(
        RescueAssignment.assigned_at.desc()).all()
    active = base.filter(RescueAssignment.status == C.ASSIGNMENT_ACCEPTED).order_by(
        RescueAssignment.assigned_at.desc()).all()
    completed = base.filter(RescueAssignment.status == C.ASSIGNMENT_COMPLETED).count()
    declined = base.filter(RescueAssignment.status == C.ASSIGNMENT_REJECTED).count()
    series = monthly_series(RescueAssignment.completed_at, 12, [
        RescueAssignment.rescuer_id == user.id, RescueAssignment.status == C.ASSIGNMENT_COMPLETED])
    open_total = AnimalReport.query.filter(AnimalReport.status.in_(C.OPEN_REPORT_STATUSES)).count()
    return {
        "awaiting": awaiting, "active": active, "completed": completed, "declined": declined,
        "overdue": sum(1 for item in awaiting + active if item.is_overdue), "open_total": open_total,
        "this_month": series["values"][-1], "delta": pct_change(series["values"][-1], series["values"][-2]),
        "series": series["values"],
        "chart": {"type": "bar", "labels": series["labels"], "datasets": [
            {"label": "Rescues completed", "data": series["values"], "color": GREEN}], "legend": False},
    }


# ------------------------------------------------------------------- volunteer
def volunteer_dashboard(user):
    summary = volunteer_service.volunteer_summary(user)
    current = VolunteerTaskAssignment.query.join(VolunteerTask, VolunteerTaskAssignment.task_id == VolunteerTask.id).filter(
        VolunteerTaskAssignment.volunteer_id == user.id,
        VolunteerTaskAssignment.status.in_([C.TA_ASSIGNED, C.TA_ACCEPTED, C.TA_IN_PROGRESS]),
    ).order_by(VolunteerTask.due_at.is_(None), VolunteerTask.due_at).all()
    hours = monthly_series(VolunteerTaskAssignment.completed_at, 12, [
        VolunteerTaskAssignment.volunteer_id == user.id, VolunteerTaskAssignment.status == C.TA_COMPLETED],
        value=VolunteerTaskAssignment.hours_spent)
    completed = monthly_series(VolunteerTaskAssignment.completed_at, 12, [
        VolunteerTaskAssignment.volunteer_id == user.id, VolunteerTaskAssignment.status == C.TA_COMPLETED])
    approved = user.is_approved_volunteer
    return {
        "summary": summary, "current": current, "approved": approved,
        "available_count": len(volunteer_service.open_tasks_for(user)) if approved else 0,
        "hours_series": hours["values"], "completed_series": completed["values"],
        "completed_this_month": completed["values"][-1],
        "chart": {"type": "bar", "labels": hours["labels"], "datasets": [
            {"label": "Hours volunteered", "data": hours["values"], "color": TEAL}], "legend": False, "integer": False},
    }


# ---------------------------------------------------------------- veterinarian
def unassigned_animals_query():
    """Animals that have no veterinarian yet (used by the dashboard and the 'unassigned' page)."""
    return Animal.query.filter(Animal.veterinarian_id.is_(None),
                               Animal.status.notin_([C.ANIMAL_ADOPTED, C.ANIMAL_REPORTED]))


def veterinarian_dashboard(user):
    today = local_today(_offset())
    mine = Animal.query.filter(Animal.veterinarian_id == user.id, Animal.status != C.ANIMAL_ADOPTED)
    records = monthly_series(MedicalRecord.examination_date, 12, [MedicalRecord.veterinarian_id == user.id])
    due = medical_service.due_vaccinations(within_days=14, vet=user)
    follow_ups = []
    horizon = today + timedelta(days=7)
    candidates = MedicalRecord.query.join(Animal, MedicalRecord.animal_id == Animal.id).filter(
        MedicalRecord.veterinarian_id == user.id, MedicalRecord.follow_up_date.isnot(None),
        MedicalRecord.follow_up_date <= horizon, Animal.status != C.ANIMAL_ADOPTED,
    ).order_by(MedicalRecord.follow_up_date).all()
    for record in candidates:  # a later examination of the same animal means the follow-up has happened
        if not any(other.examination_date > record.examination_date for other in record.animal.medical_records):
            follow_ups.append(record)
    return {
        "assigned": mine.count(),
        "critical": mine.filter(Animal.medical_status == C.MEDICAL_CRITICAL).count(),
        "needs_attention": mine.filter(Animal.medical_status.in_([C.MEDICAL_CRITICAL, C.MEDICAL_TREATMENT])).order_by(
            Animal.updated_at.desc()).limit(5).all(),
        "unassigned": unassigned_animals_query().count(),
        "records_this_month": records["values"][-1], "records_total": sum(records["values"]),
        "records_series": records["values"], "due": due[:6], "due_count": len(due),
        "overdue_count": len([v for v in due if v.next_due_date < today]),
        "follow_ups": follow_ups[:6], "follow_up_count": len(follow_ups), "today": today,
        "chart": {"type": "bar", "labels": records["labels"], "datasets": [
            {"label": "Examinations", "data": records["values"], "color": CORAL}], "legend": False},
    }


# --------------------------------------------------------------------- shelter
def shelter_dashboard(user):
    shelter = user.shelter_profile
    if shelter is None:
        return {"shelter": None}
    residents = Animal.query.filter(Animal.shelter_id == shelter.id, Animal.status != C.ANIMAL_ADOPTED)
    count = residents.count()
    status_counts = group_counts(Animal.status, Animal.shelter_id == shelter.id, Animal.status != C.ANIMAL_ADOPTED)
    labels = [s for s in C.ANIMAL_STATUSES if status_counts.get(s)]
    pending = AdoptionApplication.query.join(Animal, AdoptionApplication.animal_id == Animal.id).filter(
        Animal.shelter_id == shelter.id,
        AdoptionApplication.status.in_([C.ADOPTION_PENDING, C.ADOPTION_UNDER_REVIEW]))
    admissions = monthly_series(ShelterAdmission.admitted_at, 12, [ShelterAdmission.shelter_id == shelter.id])
    adoptions = monthly_series(AdoptionRecord.adoption_date, 12, [AdoptionRecord.shelter_id == shelter.id])
    return {
        "shelter": shelter, "count": count, "capacity": shelter.capacity,
        "percent": rules.occupancy_percent(shelter.capacity, count), "free": rules.available_capacity(shelter.capacity, count),
        "available": status_counts.get(C.ANIMAL_AVAILABLE, 0), "pending_count": pending.count(),
        "pending": pending.order_by(AdoptionApplication.created_at.desc()).limit(5).all(),
        "admitted_this_month": admissions["values"][-1], "adopted_total": AdoptionRecord.query.filter_by(
            shelter_id=shelter.id).count(),
        "recent_admissions": ShelterAdmission.query.filter_by(shelter_id=shelter.id).order_by(
            ShelterAdmission.admitted_at.desc(), ShelterAdmission.id.desc()).limit(5).all(),
        "admission_series": admissions["values"],
        "chart": {"type": "bar", "labels": admissions["labels"], "datasets": [
            {"label": "Admitted", "data": admissions["values"], "color": GREEN},
            {"label": "Adopted", "data": adoptions["values"], "color": VIOLET}]},
        "status_chart": {"type": "doughnut", "labels": labels, "datasets": [
            {"label": "Residents", "data": [status_counts[s] for s in labels],
             "colors": [ANIMAL_STATUS_COLORS[s] for s in labels]}], "center": {"text": str(count), "title": "residents"}},
        "status_legend": [{"label": s, "value": status_counts[s], "color": ANIMAL_STATUS_COLORS[s]} for s in labels],
    }


# --------------------------------------------------------------------- adopter
def adopter_dashboard(user):
    applications = AdoptionApplication.query.filter_by(adopter_id=user.id)
    counts = group_counts(AdoptionApplication.status, AdoptionApplication.adopter_id == user.id)
    applied_animal_ids = [a.animal_id for a in applications.all()]
    suggestions = Animal.query.filter(Animal.status == C.ANIMAL_AVAILABLE)
    if applied_animal_ids:
        suggestions = suggestions.filter(Animal.id.notin_(applied_animal_ids))
    labels = [status for status in C.ADOPTION_STATUSES if counts.get(status)]
    return {
        "total": sum(counts.values()), "counts": counts,
        "status_chart": {"type": "doughnut", "labels": labels, "datasets": [
            {"label": "Applications", "data": [counts[status] for status in labels],
             "colors": [ADOPTION_STATUS_COLORS[status] for status in labels]}],
         "center": {"text": str(sum(counts.values())), "title": "applications"}},
        "status_legend": [{"label": status, "value": counts[status], "color": ADOPTION_STATUS_COLORS[status]}
                          for status in labels],
        "active": sum(counts.get(status, 0) for status in C.ACTIVE_ADOPTION_STATUSES),
        "approved": counts.get(C.ADOPTION_APPROVED, 0),
        "adopted": AdoptionRecord.query.filter_by(adopter_id=user.id).count(),
        "recent": applications.order_by(AdoptionApplication.created_at.desc()).limit(5).all(),
        "suggestions": suggestions.order_by(Animal.available_since.desc(), Animal.id.desc()).limit(4).all(),
    }
