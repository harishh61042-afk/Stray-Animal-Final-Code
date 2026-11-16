"""Volunteer applications and volunteer tasks."""
from app import constants as C
from app.extensions import db
from app.models import AnimalReport, User, VolunteerTask, VolunteerTaskAssignment
from app.services import audit, notifications, rules
from app.services.common import ServiceError, link_for, require, transaction
from app.utils import validators as V
from app.utils.timeutil import utcnow


def _task_link(task):
    return link_for("tasks.detail", task_id=task.id)


# ------------------------------------------------------------- permissions
def can_manage_tasks(user):
    """Administrators and verified rescuers create and coordinate tasks."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    return user.role == C.ROLE_ADMIN or (user.role == C.ROLE_RESCUER and user.is_verified and user.is_active)


def can_edit_task(user, task):
    return bool(can_manage_tasks(user) and (user.role == C.ROLE_ADMIN or task.created_by == user.id))


def can_view_task(user, task):
    if not getattr(user, "is_authenticated", False):
        return False
    if can_manage_tasks(user):
        return True
    if user.role == C.ROLE_VOLUNTEER:
        mine = any(a.volunteer_id == user.id for a in task.assignments)
        return mine or (user.is_approved_volunteer and task.status not in (C.TASK_CANCELLED,))
    return False


# ----------------------------------------------------------- applications
def review_application(profile, actor, approve, note=None):
    """Administrator approves or rejects a volunteer application."""
    require(getattr(actor, "role", None) == C.ROLE_ADMIN, "Only an administrator can review volunteer applications.")
    require(profile.application_status == C.APPLICATION_PENDING, "This application has already been reviewed.")
    if not approve:
        require(V.clean_text(note), "Please give a reason for rejecting the application.")
    with transaction():
        profile.application_status = C.APPLICATION_APPROVED if approve else C.APPLICATION_REJECTED
        profile.reviewed_by = actor.id
        profile.reviewed_at = utcnow()
        profile.review_note = V.clean_text(note)
        message = ("Your volunteer application was approved. You can now accept volunteer tasks."
                   if approve else f"Your volunteer application was not approved. Reason: {profile.review_note}")
        notifications.notify(profile.user_id, "Account verification completed" if approve else "Volunteer application update",
                             message, C.NOTIFY_ACCOUNT, link_for("volunteers.my_application"))
        audit.log_action("volunteer_application_reviewed", "VolunteerProfile", profile.id,
                         f"{profile.user.full_name}: {profile.application_status}", user=actor)
    return profile


def resubmit_application(user, data):
    """A rejected (or still pending) volunteer updates the form and applies again."""
    profile = user.volunteer_profile
    require(user.role == C.ROLE_VOLUNTEER and profile is not None, "Only volunteer accounts have an application.")
    require(profile.application_status in (C.APPLICATION_PENDING, C.APPLICATION_REJECTED),
            "Your application is already approved.")
    skills = V.clean_text(data.get("skills"))
    require(skills, "Please list your skills.")
    availability = V.clean_text(data.get("availability"), 200)
    require(availability, "Please tell us when you are available.")
    with transaction():
        profile.skills = skills
        profile.availability = availability
        profile.experience = V.clean_text(data.get("experience"))
        profile.motivation = V.clean_text(data.get("motivation"))
        profile.emergency_contact_name = V.clean_text(data.get("emergency_contact_name"), 100)
        profile.emergency_contact_phone = V.clean_text(data.get("emergency_contact_phone"), 20)
        was_rejected = profile.application_status == C.APPLICATION_REJECTED
        profile.application_status = C.APPLICATION_PENDING
        profile.applied_at = utcnow()
        profile.review_note = None
        if was_rejected:
            notifications.notify_admins("Volunteer application resubmitted", f"{user.full_name} updated and resubmitted an application.",
                                        C.NOTIFY_ACCOUNT, link_for("volunteers.applications"))
        audit.log_action("volunteer_application_submitted", "VolunteerProfile", profile.id, user.full_name, user=user)
    return profile


# -------------------------------------------------------------------- tasks
def _clean_task_data(data):
    title = V.clean_text(data.get("title"), 150)
    require(title, "Please enter a task title.")
    require(data.get("task_type") in C.TASK_TYPES, "Please choose a task type.")
    try:
        needed = int(data.get("volunteers_needed") or 1)
    except (TypeError, ValueError):
        raise ServiceError("Volunteers needed must be a whole number.")
    require(1 <= needed <= 50, "Volunteers needed must be between 1 and 50.")
    try:
        latitude, longitude = V.parse_coordinates(data.get("latitude"), data.get("longitude"))
    except ValueError as error:
        raise ServiceError(str(error))
    return {
        "title": title, "task_type": data["task_type"], "description": V.clean_text(data.get("description")),
        "location_name": V.clean_text(data.get("location_name"), 150), "address": V.clean_text(data.get("address")),
        "latitude": latitude, "longitude": longitude, "instructions": V.clean_text(data.get("instructions")),
        "due_at": data.get("due_at") or None, "volunteers_needed": needed,
        "report_id": data.get("report_id") or None, "animal_id": data.get("animal_id") or None,
        "shelter_id": data.get("shelter_id") or None,
    }


def recompute_status(task):
    """Set ``task.status`` from its assignments (see ``rules.compute_task_status``)."""
    new_status = rules.compute_task_status(task.status, [a.status for a in task.assignments], task.volunteers_needed)
    task.status = new_status
    task.completed_at = (task.completed_at or utcnow()) if new_status == C.TASK_COMPLETED else None
    return new_status


def create_task(actor, data, volunteer_ids=None, notify_volunteers=True):
    """Create a task, optionally assigning volunteers straight away."""
    require(can_manage_tasks(actor), "Only administrators and verified rescuers can create volunteer tasks.")
    fields = _clean_task_data(data)
    if fields["due_at"]:
        require(fields["due_at"] > utcnow(), "The deadline must be in the future.")
    if fields["report_id"]:
        require(db.session.get(AnimalReport, int(fields["report_id"])) is not None, "The linked rescue report does not exist.")
    with transaction():
        task = VolunteerTask(status=C.TASK_AVAILABLE, created_by=actor.id, **fields)
        db.session.add(task)
        db.session.flush()
        for volunteer_id in volunteer_ids or []:
            _assign(task, db.session.get(User, int(volunteer_id)), actor)
        recompute_status(task)
        if notify_volunteers and task.status == C.TASK_AVAILABLE:
            notifications.notify_role(
                C.ROLE_VOLUNTEER, "New volunteer task available", f"{task.title} ({task.task_type}) needs volunteers.",
                C.NOTIFY_TASK, _task_link(task), verified_only=False)
        audit.log_action("task_created", "VolunteerTask", task.id, task.title, user=actor)
    return task


def update_task(task, actor, data):
    require(can_edit_task(actor, task), "You are not allowed to edit this task.")
    require(task.status not in (C.TASK_COMPLETED, C.TASK_CANCELLED), "A completed or cancelled task cannot be edited.")
    fields = _clean_task_data(data)
    require(fields["volunteers_needed"] >= len(task.active_assignments), "You already have more volunteers assigned than that.")
    with transaction():
        for key, value in fields.items():
            setattr(task, key, value)
        recompute_status(task)
        audit.log_action("task_updated", "VolunteerTask", task.id, task.title, user=actor)
    return task


def _assign(task, volunteer, actor):
    require(volunteer is not None and volunteer.role == C.ROLE_VOLUNTEER, "Please choose a volunteer.")
    require(volunteer.is_approved_volunteer and volunteer.is_active, f"{volunteer.full_name} is not an approved volunteer.")
    require(task.status not in (C.TASK_COMPLETED, C.TASK_CANCELLED), "This task is closed.")
    existing = next((a for a in task.assignments if a.volunteer_id == volunteer.id), None)
    if existing is not None:
        require(existing.status in C.INACTIVE_TASK_ASSIGNMENT_STATUSES, f"{volunteer.full_name} is already assigned to this task.")
    require(task.open_slots > 0, "This task already has all the volunteers it needs.")
    if existing is not None:
        existing.status = C.TA_ASSIGNED
        existing.assigned_by = actor.id
        existing.assigned_at = utcnow()
        existing.responded_at = None
        existing.progress_percent = 0
        assignment = existing
    else:
        assignment = VolunteerTaskAssignment(task=task, volunteer_id=volunteer.id, assigned_by=actor.id, status=C.TA_ASSIGNED)
        db.session.add(assignment)
    db.session.flush()
    notifications.notify(volunteer, "Volunteer task assigned",
                         f"You were assigned: {task.title}. Please accept or decline.", C.NOTIFY_TASK, _task_link(task))
    return assignment


def assign_volunteer(task, volunteer, actor):
    require(can_manage_tasks(actor), "You are not allowed to assign volunteers.")
    with transaction():
        assignment = _assign(task, volunteer, actor)
        recompute_status(task)
        audit.log_action("task_assigned", "VolunteerTask", task.id, f"{task.title} -> {volunteer.full_name}", user=actor)
    return assignment


def _my_assignment(task, volunteer):
    return next((a for a in task.assignments if a.volunteer_id == volunteer.id), None)


def _notify_managers(task, title, message):
    recipients = [task.created_by] if task.created_by else []
    notifications.notify_many(recipients, title, message, C.NOTIFY_TASK, _task_link(task))
    notifications.notify_admins(title, message, C.NOTIFY_TASK, _task_link(task))


def accept_task(task, volunteer):
    """Accept a task assigned to you, or claim an open one. Approved volunteers only."""
    require(volunteer.role == C.ROLE_VOLUNTEER and volunteer.is_approved_volunteer,
            "Only approved volunteers can accept tasks. Your application must be approved first.")
    require(task.status not in (C.TASK_COMPLETED, C.TASK_CANCELLED), "This task is no longer open.")
    with transaction():
        assignment = _my_assignment(task, volunteer)
        if assignment is not None and assignment.status in (C.TA_ASSIGNED,):
            assignment.status = C.TA_ACCEPTED
        elif assignment is not None and assignment.status in C.INACTIVE_TASK_ASSIGNMENT_STATUSES:
            require(task.open_slots > 0, "This task already has all the volunteers it needs.")
            assignment.status = C.TA_ACCEPTED
            assignment.progress_percent = 0
        elif assignment is None:
            require(task.open_slots > 0, "This task already has all the volunteers it needs.")
            assignment = VolunteerTaskAssignment(task=task, volunteer_id=volunteer.id, assigned_by=None, status=C.TA_ACCEPTED)
            db.session.add(assignment)
        else:
            raise ServiceError("You have already accepted this task.")
        assignment.responded_at = utcnow()
        db.session.flush()
        recompute_status(task)
        _notify_managers(task, "Volunteer task accepted", f"{volunteer.full_name} accepted '{task.title}'.")
        audit.log_action("task_accepted", "VolunteerTask", task.id, f"{task.title} by {volunteer.full_name}", user=volunteer)
    return assignment


def decline_task(task, volunteer, reason=None):
    assignment = _my_assignment(task, volunteer)
    require(assignment is not None, "This task is not assigned to you.")
    require(assignment.status in (C.TA_ASSIGNED, C.TA_ACCEPTED), "You can only decline a task you have not started.")
    with transaction():
        assignment.status = C.TA_DECLINED
        assignment.responded_at = utcnow()
        assignment.progress_note = V.clean_text(reason)
        db.session.flush()
        recompute_status(task)
        _notify_managers(task, "Volunteer task declined", f"{volunteer.full_name} declined '{task.title}'. It needs another volunteer.")
        audit.log_action("task_declined", "VolunteerTask", task.id, f"{task.title} by {volunteer.full_name}", user=volunteer)
    return assignment


def update_progress(task, volunteer, percent, note=None):
    assignment = _my_assignment(task, volunteer)
    require(assignment is not None, "This task is not assigned to you.")
    require(assignment.status in (C.TA_ACCEPTED, C.TA_IN_PROGRESS), "Accept the task before reporting progress.")
    try:
        percent = int(percent)
    except (TypeError, ValueError):
        raise ServiceError("Progress must be a number between 0 and 99.")
    require(0 <= percent <= 99, "Progress must be between 0 and 99. Use 'Mark completed' to finish the task.")
    with transaction():
        assignment.status = C.TA_IN_PROGRESS
        assignment.started_at = assignment.started_at or utcnow()
        assignment.progress_percent = percent
        assignment.progress_note = V.clean_text(note)
        db.session.flush()
        recompute_status(task)
        audit.log_action("task_progress", "VolunteerTask", task.id, f"{task.title}: {percent}%", user=volunteer)
    return assignment


def complete_task(task, volunteer, notes=None, hours=None):
    assignment = _my_assignment(task, volunteer)
    require(assignment is not None, "This task is not assigned to you.")
    require(assignment.status in (C.TA_ACCEPTED, C.TA_IN_PROGRESS), "Only an accepted task can be completed.")
    if hours in (None, ""):
        hours = None
    else:
        try:
            hours = float(hours)
        except (TypeError, ValueError):
            raise ServiceError("Hours must be a number.")
        require(0 < hours <= 100, "Hours must be between 0 and 100.")
    with transaction():
        assignment.status = C.TA_COMPLETED
        assignment.progress_percent = 100
        assignment.completed_at = utcnow()
        assignment.started_at = assignment.started_at or assignment.completed_at
        assignment.completion_notes = V.clean_text(notes)
        assignment.hours_spent = hours
        db.session.flush()
        recompute_status(task)
        _notify_managers(task, "Volunteer task completed", f"{volunteer.full_name} completed '{task.title}'.")
        audit.log_action("task_completed", "VolunteerTask", task.id, f"{task.title} by {volunteer.full_name}", user=volunteer)
    return assignment


def remove_volunteer(task, assignment, actor):
    require(can_edit_task(actor, task) or getattr(actor, "role", None) == C.ROLE_ADMIN, "You are not allowed to change this task.")
    require(assignment.task_id == task.id, "That volunteer is not on this task.")
    require(assignment.status not in (C.TA_COMPLETED,) + tuple(C.INACTIVE_TASK_ASSIGNMENT_STATUSES), "That assignment can no longer be removed.")
    with transaction():
        assignment.status = C.TA_CANCELLED
        db.session.flush()
        recompute_status(task)
        notifications.notify(assignment.volunteer_id, "Volunteer task update", f"You were removed from '{task.title}'.", C.NOTIFY_TASK, _task_link(task))
        audit.log_action("task_volunteer_removed", "VolunteerTask", task.id, task.title, user=actor)
    return task


def cancel_task(task, actor, reason=None):
    require(can_edit_task(actor, task), "You are not allowed to cancel this task.")
    require(task.status not in (C.TASK_COMPLETED, C.TASK_CANCELLED), "This task is already closed.")
    with transaction():
        for assignment in task.assignments:
            if assignment.status in (C.TA_ASSIGNED, C.TA_ACCEPTED, C.TA_IN_PROGRESS):
                assignment.status = C.TA_CANCELLED
                notifications.notify(assignment.volunteer_id, "Volunteer task cancelled",
                                     f"'{task.title}' was cancelled.", C.NOTIFY_TASK, _task_link(task))
        task.status = C.TASK_CANCELLED
        task.cancel_reason = V.clean_text(reason)
        audit.log_action("task_cancelled", "VolunteerTask", task.id, task.title, user=actor)
    return task


# ------------------------------------------------------------------- queries
def open_tasks_for(volunteer):
    """Tasks a volunteer could still join (open slots, not already theirs)."""
    candidates = VolunteerTask.query.filter(
        VolunteerTask.status.in_([C.TASK_AVAILABLE, C.TASK_ASSIGNED, C.TASK_ACCEPTED])
    ).order_by(VolunteerTask.due_at.is_(None), VolunteerTask.due_at, VolunteerTask.id.desc()).all()
    result = []
    for task in candidates:
        mine = _my_assignment(task, volunteer)
        if mine is not None and mine.status not in C.INACTIVE_TASK_ASSIGNMENT_STATUSES:
            continue
        if task.open_slots > 0:
            result.append(task)
    return result


def volunteer_summary(volunteer):
    """Counts and hours for a volunteer's dashboard / profile."""
    rows = VolunteerTaskAssignment.query.filter_by(volunteer_id=volunteer.id).all()
    count = lambda status: sum(1 for r in rows if r.status == status)  # noqa: E731
    return {
        "assigned": count(C.TA_ASSIGNED), "accepted": count(C.TA_ACCEPTED), "in_progress": count(C.TA_IN_PROGRESS),
        "completed": count(C.TA_COMPLETED), "declined": count(C.TA_DECLINED),
        "hours": round(sum(r.hours_spent or 0 for r in rows), 1),
    }
