"""Administrator tools: account lists, the verification queue, the activity log, the contact inbox,
in-app notices to users and CSV exports.

Like the other services, these functions do not look at who is signed in for *reading*; the routes in
``app/routes/admin.py`` are protected with ``roles_required(C.ROLE_ADMIN)``. Functions that change data
(``set_message_status``, ``send_broadcast``, ``record_export``) also check that the actor is an administrator.
"""
import csv
import io

from sqlalchemy.orm import selectinload

from app import constants as C
from app.extensions import db
from app.models import (
    AdoptionApplication, AdoptionRecord, Animal, AnimalReport, AuditLog, ContactMessage, MedicalRecord,
    RescueAssignment, User, Vaccination, VolunteerProfile, VolunteerTaskAssignment,
)
from app.services import audit, notifications, stats, volunteer_service
from app.services.common import ServiceError, like_pattern, link_for, require, transaction
from app.services.reporting import date_clauses, display_offset
from app.utils import validators as V
from app.utils.csvsafe import safe_cell
from app.utils.timeutil import local_today

ESCAPE = "\\"
SYSTEM_KIND = "System"
KIND_CHOICES = [name for name, _prefixes in stats.KIND_PREFIXES] + [SYSTEM_KIND]
BROADCAST_ACTION = "notification_broadcast"
BROADCAST_TARGETS = ("all", "role", "user")

EXPORT_DATASETS = [
    {"key": "reports", "title": "Rescue reports", "icon": "bi-life-preserver", "by": "report date",
     "text": "Every report with emergency level, status, reporter contact and the rescuer who handled it."},
    {"key": "animals", "title": "Animals", "icon": "bi-heart-pulse", "by": "registration date",
     "text": "Registered animals with medical, vaccination, rehabilitation and shelter details."},
    {"key": "adoptions", "title": "Adoption applications", "icon": "bi-balloon-heart", "by": "application date",
     "text": "Applications with the decision, who reviewed them and the date the adoption was completed."},
    {"key": "users", "title": "User accounts", "icon": "bi-people", "by": "sign-up date",
     "text": "Accounts with role, status and verification. Passwords are never exported."},
    {"key": "volunteers", "title": "Volunteers", "icon": "bi-person-lines-fill", "by": "application date",
     "text": "Volunteer applications with skills, availability, completed tasks and hours."},
    {"key": "medical", "title": "Medical records", "icon": "bi-clipboard2-pulse", "by": "examination date",
     "text": "Examinations with diagnosis, treatment, medicines and follow-up dates."},
    {"key": "vaccinations", "title": "Vaccinations", "icon": "bi-shield-check", "by": "vaccination date",
     "text": "Vaccinations given, the next dose due and whether it is overdue."},
]
DATASET_KEYS = tuple(item["key"] for item in EXPORT_DATASETS)


def _require_admin(actor):
    require(getattr(actor, "role", None) == C.ROLE_ADMIN, "Only an administrator can do this.")


def _search(query, text, *columns):
    pattern = like_pattern(text)
    return query.filter(db.or_(*[column.ilike(pattern, escape=ESCAPE) for column in columns]))


# ---------------------------------------------------------------- accounts
def user_query(q=None, role=None, status=None, verification=None):
    """Accounts matching the filters, newest first."""
    query = User.query
    if (q or "").strip():
        query = _search(query, q, User.full_name, User.email, User.phone)
    if role in C.ALL_ROLES:
        query = query.filter(User.role == role)
    if status in C.ACCOUNT_STATUSES:
        query = query.filter(User.status == status)
    if verification in C.VERIFICATION_STATUSES:
        query = query.filter(User.verification_status == verification)
    return query.order_by(User.created_at.desc(), User.id.desc())


def user_counts():
    roles = stats.group_counts(User.role)
    return {
        "total": sum(roles.values()), "roles": roles, "status": stats.group_counts(User.status),
        "pending_verification": User.query.filter(User.verification_status == C.VERIFY_PENDING).count(),
    }


def profile_rows(user):
    """``[{label, value}]`` describing the role-specific profile (empty values are left out)."""
    profile = user.role_profile
    if profile is None:
        return []

    def years(value):
        return None if value is None else f"{value} year{'s' if value != 1 else ''}"

    if user.role == C.ROLE_RESCUER:
        rows = [("Organisation", profile.organization), ("Experience", years(profile.experience_years)),
                ("Service area", profile.service_area), ("Has a vehicle", "Yes" if profile.has_vehicle else "No")]
    elif user.role == C.ROLE_VETERINARIAN:
        rows = [("Clinic", profile.clinic_name), ("Licence number", profile.license_number),
                ("Qualification", profile.qualification), ("Specialisation", profile.specialization),
                ("Experience", years(profile.experience_years)), ("Clinic address", profile.clinic_address),
                ("Consultation hours", profile.consultation_hours)]
    elif user.role == C.ROLE_SHELTER:
        place = ", ".join(part for part in (profile.address, profile.city, profile.state, profile.pincode) if part)
        rows = [("Shelter name", profile.shelter_name), ("Registration number", profile.registration_number),
                ("Address", place), ("Capacity", f"{profile.capacity} animals" if profile.capacity else None),
                ("Contact phone", profile.contact_phone), ("Contact e-mail", profile.contact_email),
                ("Website", profile.website)]
    elif user.role == C.ROLE_VOLUNTEER:
        emergency = " - ".join(part for part in (profile.emergency_contact_name, profile.emergency_contact_phone) if part)
        rows = [("Skills", profile.skills), ("Availability", profile.availability), ("Experience", profile.experience),
                ("Why they volunteer", profile.motivation), ("Emergency contact", emergency)]
    else:
        rows = []
    return [{"label": label, "value": value} for label, value in rows if value not in (None, "")]


def user_summary(user):
    """A few real numbers about what an account has done (shown on the account page)."""
    rows = []
    sent = AnimalReport.query.filter(AnimalReport.reporter_id == user.id).count()
    if sent:
        rows.append(("Rescue reports sent", sent))
    if user.role == C.ROLE_ADOPTER:
        rows.append(("Adoption applications", AdoptionApplication.query.filter(AdoptionApplication.adopter_id == user.id).count()))
        rows.append(("Adoptions completed", AdoptionRecord.query.filter(AdoptionRecord.adopter_id == user.id).count()))
    elif user.role == C.ROLE_RESCUER:
        mine = RescueAssignment.query.filter(RescueAssignment.rescuer_id == user.id)
        rows.append(("Rescues assigned", mine.count()))
        rows.append(("Rescues completed", mine.filter(RescueAssignment.completed_at.isnot(None)).count()))
    elif user.role == C.ROLE_VETERINARIAN:
        rows.append(("Animals in their care", Animal.query.filter(Animal.veterinarian_id == user.id).count()))
        rows.append(("Medical records written", MedicalRecord.query.filter(MedicalRecord.veterinarian_id == user.id).count()))
    elif user.role == C.ROLE_VOLUNTEER:
        summary = volunteer_service.volunteer_summary(user)
        rows.append(("Tasks completed", summary["completed"]))
        rows.append(("Hours recorded", summary["hours"]))
    elif user.role == C.ROLE_SHELTER and user.shelter_profile is not None:
        shelter = user.shelter_profile
        rows.append(("Animals housed", f"{shelter.current_count} of {shelter.capacity}"))
        rows.append(("Adoptions from this shelter", AdoptionRecord.query.filter(AdoptionRecord.shelter_id == shelter.id).count()))
    return [{"label": label, "value": value} for label, value in rows]


# ------------------------------------------------------------ verification
def verification_query(status=None, role=None, q=None):
    """Rescuer / veterinarian / shelter accounts (oldest waiting first when looking at the pending ones)."""
    query = User.query.filter(User.role.in_(C.VERIFICATION_REQUIRED_ROLES))
    if status in (C.VERIFY_PENDING, C.VERIFY_VERIFIED, C.VERIFY_REJECTED):
        query = query.filter(User.verification_status == status)
    if role in C.VERIFICATION_REQUIRED_ROLES:
        query = query.filter(User.role == role)
    if (q or "").strip():
        query = _search(query, q, User.full_name, User.email)
    if status == C.VERIFY_PENDING:
        return query.order_by(User.created_at.asc(), User.id.asc())
    return query.order_by(User.created_at.desc(), User.id.desc())


def verification_counts():
    return stats.group_counts(User.verification_status, User.role.in_(C.VERIFICATION_REQUIRED_ROLES))


# ------------------------------------------------------------ activity log
def action_title(action):
    return stats.ACTIVITY_TITLES.get(action) or (action or "").replace("_", " ").capitalize()


def audit_query(q=None, action=None, kind=None, user_id=None):
    """Audit-log rows matching the filters, newest first."""
    query = AuditLog.query.outerjoin(User, AuditLog.user_id == User.id)
    if action:
        query = query.filter(AuditLog.action == action)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if kind == SYSTEM_KIND:
        known = [AuditLog.action.startswith(prefix, autoescape=True)
                 for _name, prefixes in stats.KIND_PREFIXES for prefix in prefixes]
        query = query.filter(~db.or_(*known))
    elif kind in KIND_CHOICES:
        prefixes = dict(stats.KIND_PREFIXES)[kind]
        query = query.filter(db.or_(*[AuditLog.action.startswith(prefix, autoescape=True) for prefix in prefixes]))
    if (q or "").strip():
        query = _search(query, q, AuditLog.description, AuditLog.action, User.full_name, User.email)
    return query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())


def audit_action_choices():
    """``[(action, friendly title)]`` for every action that appears in the log."""
    actions = [row[0] for row in db.session.query(AuditLog.action).distinct().all()]
    return sorted(((action, action_title(action)) for action in actions), key=lambda pair: pair[1].lower())


_ENTITY_LINKS = {
    "User": ("admin.user_detail", "user_id"), "AnimalReport": ("reports.detail", "report_id"),
    "Animal": ("animals.detail", "animal_id"), "AdoptionApplication": ("adoption.detail", "application_id"),
    "VolunteerTask": ("tasks.detail", "task_id"), "ShelterProfile": ("shelters.detail", "shelter_id"),
    "MedicalRecord": ("medical.record_detail", "record_id"),
}


def entity_link(entry):
    """Address of the page about the thing an audit row is about (``None`` when there is no such page)."""
    target = _ENTITY_LINKS.get(entry.entity_type)
    if target is None or not entry.entity_id:
        return None
    endpoint, argument = target
    return link_for(endpoint, **{argument: entry.entity_id})


def describe_entries(rows):
    """Audit rows plus what a page needs to show them: who, a friendly title, the kind and a link."""
    described = []
    for entry in rows:
        kind = stats.activity_kind(entry.action)
        described.append({
            "entry": entry, "who": entry.user.full_name if entry.user else "System",
            "title": action_title(entry.action), "kind": kind, "tone": stats.KIND_TONES[kind],
            "link": entity_link(entry),
        })
    return described


def user_activity(user, limit=15):
    """What an account did and what was done to it (sign-ins are left out: they are only noise here)."""
    return (
        AuditLog.query
        .filter(db.or_(AuditLog.user_id == user.id, db.and_(AuditLog.entity_type == "User", AuditLog.entity_id == user.id)),
                AuditLog.action != "login")
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .all()
    )


def recent_broadcasts(limit=8):
    return AuditLog.query.filter(AuditLog.action == BROADCAST_ACTION).order_by(
        AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).all()


# ----------------------------------------------------------- contact inbox
def message_query(status=None, q=None):
    query = ContactMessage.query
    if status in C.CONTACT_STATUSES:
        query = query.filter(ContactMessage.status == status)
    if (q or "").strip():
        query = _search(query, q, ContactMessage.name, ContactMessage.email, ContactMessage.subject, ContactMessage.message)
    return query.order_by(ContactMessage.created_at.desc(), ContactMessage.id.desc())


def message_counts():
    return stats.group_counts(ContactMessage.status)


def set_message_status(message, status, actor):
    _require_admin(actor)
    require(status in C.CONTACT_STATUSES, "Invalid message status.")
    with transaction():
        message.status = status
        audit.log_action("contact_message_status", "ContactMessage", message.id, f"{message.subject} -> {status}", user=actor)
    return message


# ------------------------------------------------------------------ notices
def send_broadcast(actor, target, title, message, role=None, email=None, link=None):
    """Send an in-app notice (it appears in the notification bell; nothing is e-mailed or texted).

    ``target``: ``all`` active accounts, every active account of one ``role``, or one person by ``email``.
    Returns the number of people who received it.
    """
    _require_admin(actor)
    title = V.clean_text(title, 150)
    require(title and len(title) >= 3, "Please enter a title of at least 3 characters.")
    message = V.clean_text(message, 1000)
    require(message and len(message) >= 5, "Please enter the message (at least 5 characters).")
    link = V.clean_text(link, 255)
    require(not link or (link.startswith("/") and not link.startswith("//") and "\\" not in link and " " not in link),
            "The link must be a page of this site, for example /adopt.")

    recipients = db.session.query(User.id).filter(User.status == C.ACCOUNT_ACTIVE)
    if target == "all":
        who = "everyone"
    elif target == "role":
        require(role in C.ALL_ROLES, "Choose which account type should receive the notice.")
        recipients = recipients.filter(User.role == role)
        who = f"all {C.ROLE_LABELS[role].lower()} accounts"
    elif target == "user":
        address = V.normalize_email(email)
        require(address, "Enter the e-mail address of the person.")
        recipients = recipients.filter(db.func.lower(User.email) == address)
        who = address
    else:
        raise ServiceError("Choose who should receive the notice.")
    ids = [row[0] for row in recipients.all()]
    require(ids, "There is nobody to send this to (the account may not exist or may not be active).")

    with transaction():
        notifications.notify_many(ids, title, message, C.NOTIFY_SYSTEM, link)
        audit.log_action(BROADCAST_ACTION, None, None,
                         f"To {who} ({len(ids)} recipient{'s' if len(ids) != 1 else ''}): {title}", user=actor)
    return len(ids)


# ------------------------------------------------------------------ exports
def _due_state(vaccination, today):
    if vaccination.next_due_date is None:
        return "No booster planned"
    if vaccination.next_due_date < today:
        return "Overdue"
    return "Due within 14 days" if (vaccination.next_due_date - today).days <= 14 else "Up to date"


def _reports(start, end):
    query = (
        AnimalReport.query
        .options(selectinload(AnimalReport.assignments).selectinload(RescueAssignment.rescuer))
        .filter(*date_clauses(AnimalReport.created_at, start, end))
        .order_by(AnimalReport.created_at.desc(), AnimalReport.id.desc())
    )
    headers = ["Report ID", "Submitted", "Status", "Emergency level", "Animal type", "Animals", "Condition",
               "Location", "Address", "Latitude", "Longitude", "Reporter", "Reporter phone", "Reporter e-mail",
               "Rescuer", "Assignment status", "Closed"]

    def rows():
        for r in query.all():
            last = r.latest_assignment
            yield [r.report_code, r.created_at, r.status, r.emergency_level, r.animal_type, r.animal_count,
                   r.animal_condition, r.location_name, r.address, r.latitude, r.longitude, r.reporter_name,
                   r.reporter_phone, r.reporter_email, last.rescuer.full_name if last and last.rescuer else None,
                   last.status if last else None, r.closed_at]

    return headers, rows()


def _animals(start, end):
    query = (
        Animal.query
        .options(selectinload(Animal.shelter), selectinload(Animal.veterinarian), selectinload(Animal.report))
        .filter(*date_clauses(Animal.created_at, start, end))
        .order_by(Animal.created_at.desc(), Animal.id.desc())
    )
    headers = ["Animal ID", "Name", "Type", "Breed", "Gender", "Age (months)", "Colour", "Status", "Medical status",
               "Vaccination status", "Rehabilitation", "Shelter", "Veterinarian", "Rescue date", "Rescue location",
               "Rescue report", "Registered", "Available since"]

    def rows():
        for a in query.all():
            yield [a.animal_code, a.name, a.animal_type, a.breed, a.gender, a.age_months, a.color, a.status,
                   a.medical_status, a.vaccination_status, a.rehabilitation_status,
                   a.shelter.shelter_name if a.shelter else None, a.veterinarian.full_name if a.veterinarian else None,
                   a.rescue_date, a.rescue_location, a.report.report_code if a.report else None, a.created_at,
                   a.available_since]

    return headers, rows()


def _adoptions(start, end):
    query = (
        AdoptionApplication.query
        .options(selectinload(AdoptionApplication.animal).selectinload(Animal.shelter),
                 selectinload(AdoptionApplication.reviewer), selectinload(AdoptionApplication.record))
        .filter(*date_clauses(AdoptionApplication.created_at, start, end))
        .order_by(AdoptionApplication.created_at.desc(), AdoptionApplication.id.desc())
    )
    headers = ["Application ID", "Submitted", "Status", "Animal ID", "Animal", "Animal type", "Applicant",
               "Applicant e-mail", "Applicant phone", "City", "Housing", "Household members", "Other pets",
               "Reviewed by", "Reviewed", "Adoption completed", "Shelter"]

    def rows():
        for a in query.all():
            animal = a.animal
            yield [a.application_code, a.created_at, a.status, animal.animal_code if animal else None,
                   animal.display_name if animal else None, animal.animal_type if animal else None, a.applicant_name,
                   a.applicant_email, a.applicant_phone, a.city, a.housing_type, a.household_members, a.has_other_pets,
                   a.reviewer.full_name if a.reviewer else None, a.reviewed_at,
                   a.record.adoption_date if a.record else None,
                   animal.shelter.shelter_name if animal and animal.shelter else None]

    return headers, rows()


def _users(start, end):
    query = User.query.filter(*date_clauses(User.created_at, start, end)).order_by(User.created_at.desc(), User.id.desc())
    headers = ["User ID", "Name", "E-mail", "Phone", "Role", "Account status", "Verification", "Verified on",
               "Registered", "Last sign-in"]

    def rows():
        for u in query.all():
            yield [u.id, u.full_name, u.email, u.phone, u.role_label, u.status,
                   u.verification_status if u.needs_verification else "Not required", u.verified_at, u.created_at,
                   u.last_login_at]

    return headers, rows()


def _volunteers(start, end):
    pairs = (
        db.session.query(User, VolunteerProfile)
        .select_from(VolunteerProfile)
        .join(User, User.id == VolunteerProfile.user_id)
        .filter(*date_clauses(VolunteerProfile.applied_at, start, end))
        .order_by(VolunteerProfile.applied_at.desc(), VolunteerProfile.id.desc())
    )
    done = {
        volunteer_id: (count, hours)
        for volunteer_id, count, hours in db.session.query(
            VolunteerTaskAssignment.volunteer_id, db.func.count(VolunteerTaskAssignment.id),
            db.func.coalesce(db.func.sum(VolunteerTaskAssignment.hours_spent), 0))
        .filter(VolunteerTaskAssignment.status == C.TA_COMPLETED)
        .group_by(VolunteerTaskAssignment.volunteer_id).all()
    }
    headers = ["User ID", "Name", "E-mail", "Phone", "Application status", "Skills", "Availability", "Applied",
               "Reviewed", "Tasks completed", "Hours"]

    def rows():
        for user, profile in pairs.all():
            count, hours = done.get(user.id, (0, 0))
            yield [user.id, user.full_name, user.email, user.phone, profile.application_status, profile.skills,
                   profile.availability, profile.applied_at, profile.reviewed_at, count, round(float(hours or 0), 1)]

    return headers, rows()


def _medical(start, end):
    query = (
        MedicalRecord.query
        .options(selectinload(MedicalRecord.animal), selectinload(MedicalRecord.veterinarian))
        .filter(*date_clauses(MedicalRecord.examination_date, start, end, is_date=True))
        .order_by(MedicalRecord.examination_date.desc(), MedicalRecord.id.desc())
    )
    headers = ["Record ID", "Animal ID", "Animal", "Examination date", "Veterinarian", "Weight (kg)", "Symptoms",
               "Diagnosis", "Treatment", "Medicines", "Medical status", "Follow-up date"]

    def rows():
        for m in query.all():
            yield [m.id, m.animal.animal_code if m.animal else None, m.animal.display_name if m.animal else None,
                   m.examination_date, m.veterinarian.full_name if m.veterinarian else None, m.weight_kg, m.symptoms,
                   m.diagnosis, m.treatment, m.medicines, m.medical_status, m.follow_up_date]

    return headers, rows()


def _vaccinations(start, end):
    query = (
        Vaccination.query
        .options(selectinload(Vaccination.animal), selectinload(Vaccination.administrator))
        .filter(*date_clauses(Vaccination.vaccination_date, start, end, is_date=True))
        .order_by(Vaccination.vaccination_date.desc(), Vaccination.id.desc())
    )
    headers = ["Animal ID", "Animal", "Vaccine", "Vaccination date", "Next dose due", "Due state", "Given by", "Batch number"]
    today = local_today(display_offset())

    def rows():
        for v in query.all():
            yield [v.animal.animal_code if v.animal else None, v.animal.display_name if v.animal else None,
                   v.vaccine_name, v.vaccination_date, v.next_due_date, _due_state(v, today),
                   v.administrator.full_name if v.administrator else None, v.batch_number]

    return headers, rows()


_BUILDERS = {
    "reports": _reports, "animals": _animals, "adoptions": _adoptions, "users": _users,
    "volunteers": _volunteers, "medical": _medical, "vaccinations": _vaccinations,
}


def export_csv(dataset, start=None, end=None):
    """Build a CSV file (UTF-8 with a byte-order mark so Excel shows accents correctly).

    Returns ``(text, number of data rows)``. ``start`` / ``end`` are local dates; the date used for each data set is
    listed in ``EXPORT_DATASETS``. Text that starts like a spreadsheet formula is neutralised (see ``csvsafe``).
    """
    builder = _BUILDERS.get(dataset)
    require(builder is not None, "Unknown data set.")
    headers, rows = builder(start, end)
    offset = display_offset()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    count = 0
    for row in rows:
        writer.writerow([safe_cell(value, offset) for value in row])
        count += 1
    return "﻿" + buffer.getvalue(), count


def export_filename(dataset):
    return f"pawconnect-{dataset}-{local_today(display_offset()):%Y%m%d}.csv"


def record_export(dataset, count, actor, start=None, end=None):
    """Write an audit row so it is always known who downloaded which data."""
    _require_admin(actor)
    span = f" from {start or 'the beginning'} to {end or 'today'}" if start or end else ""
    with transaction():
        audit.log_action("data_exported", None, None, f"{dataset}: {count} row{'s' if count != 1 else ''}{span}", user=actor)
