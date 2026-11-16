"""Business rules as pure functions.

Nothing in this file touches Flask or the database, so every rule can be unit
tested directly (see ``tests/test_rules.py``). The service modules call these
functions before they change any data.
"""
from app import constants as C

# ----------------------------------------------------------- rescue reports
REPORT_TRANSITIONS = {
    C.REPORT_PENDING: {C.REPORT_UNDER_REVIEW, C.REPORT_ASSIGNED, C.REPORT_REJECTED, C.REPORT_CLOSED},
    C.REPORT_UNDER_REVIEW: {C.REPORT_ASSIGNED, C.REPORT_REJECTED, C.REPORT_CLOSED},
    C.REPORT_ASSIGNED: {C.REPORT_IN_PROGRESS, C.REPORT_UNDER_REVIEW, C.REPORT_CLOSED},
    C.REPORT_IN_PROGRESS: {C.REPORT_RESCUED, C.REPORT_CLOSED, C.REPORT_UNDER_REVIEW},
    C.REPORT_RESCUED: {C.REPORT_CLOSED},
    C.REPORT_CLOSED: set(),
    C.REPORT_REJECTED: {C.REPORT_UNDER_REVIEW},
}


def can_transition_report(old, new):
    return new in REPORT_TRANSITIONS.get(old, set())


def allowed_report_transitions(old):
    """Ordered list of statuses a report may move to from ``old``."""
    allowed = REPORT_TRANSITIONS.get(old, set())
    return [status for status in C.REPORT_STATUSES if status in allowed]


# ------------------------------------------------------------------- animals
def can_transition_animal(old, new, via_adoption=False):
    """Animals may move freely between care stages, with three guard rails.

    * ``Adopted`` is final.
    * ``Adopted`` can only be reached by completing an adoption.
    * An animal never goes back to ``Reported`` once it has been rescued.
    """
    if old == new:
        return False
    if old == C.ANIMAL_ADOPTED:
        return False
    if new == C.ANIMAL_ADOPTED:
        return bool(via_adoption)
    if new == C.ANIMAL_REPORTED:
        return old == C.ANIMAL_REPORTED
    return new in C.ANIMAL_STATUSES and old in C.ANIMAL_STATUSES


def allowed_animal_transitions(old):
    return [s for s in C.ANIMAL_STATUSES if can_transition_animal(old, s)]


def adoption_readiness_problems(animal_status, medical_status, has_shelter):
    """Reasons an animal cannot be listed for adoption yet (empty = ready)."""
    problems = []
    if animal_status == C.ANIMAL_ADOPTED:
        problems.append("This animal has already been adopted.")
    if not has_shelter:
        problems.append("Assign the animal to a shelter before listing it for adoption.")
    if medical_status == C.MEDICAL_CRITICAL:
        problems.append("An animal in critical medical condition cannot be listed for adoption.")
    return problems


def animal_status_for_medical(current_status, medical_status):
    """Which animal status should follow a new medical finding? ``None`` = keep."""
    if current_status == C.ANIMAL_ADOPTED:
        return None
    if medical_status in (C.MEDICAL_TREATMENT, C.MEDICAL_CRITICAL):
        target = C.ANIMAL_TREATMENT
        return target if current_status != target else None
    if medical_status == C.MEDICAL_RECOVERING:
        if current_status in (C.ANIMAL_REPORTED, C.ANIMAL_RESCUED, C.ANIMAL_TREATMENT):
            return C.ANIMAL_RECOVERING
    return None


# --------------------------------------------------------------- vaccination
def compute_vaccination_status(records, today):
    """Overall vaccination status from ``(name, given_date, next_due_date)`` rows.

    * no records                         -> Not Vaccinated
    * a vaccine whose latest dose is due -> Booster Due
    * two or more different vaccines     -> Fully Vaccinated
    * one vaccine                        -> Partially Vaccinated
    """
    latest = {}
    for name, given, due in records:
        key = (name or "").strip().lower()
        if key not in latest or (given and latest[key][0] and given > latest[key][0]):
            latest[key] = (given, due)
    if not latest:
        return C.VACC_NONE
    if any(due is not None and due <= today for (_given, due) in latest.values()):
        return C.VACC_DUE
    return C.VACC_FULL if len(latest) >= 2 else C.VACC_PARTIAL


# ------------------------------------------------------------------ shelters
def has_capacity(capacity, current_count):
    return int(current_count) < int(capacity)


def available_capacity(capacity, current_count):
    return max(int(capacity) - int(current_count), 0)


def occupancy_percent(capacity, current_count):
    if not capacity:
        return 0
    return min(100, round(int(current_count) * 100 / int(capacity)))


# ------------------------------------------------------------ volunteer tasks
def _active(statuses):
    return [s for s in statuses if s not in C.INACTIVE_TASK_ASSIGNMENT_STATUSES]


def task_open_slots(volunteers_needed, assignment_statuses):
    return max(0, int(volunteers_needed) - len(_active(assignment_statuses)))


def compute_task_status(current_status, assignment_statuses, volunteers_needed=1):
    """Task status derived from its volunteer assignments."""
    if current_status == C.TASK_CANCELLED:
        return C.TASK_CANCELLED
    active = _active(assignment_statuses)
    if not active:
        return C.TASK_AVAILABLE
    completed = [s for s in active if s == C.TA_COMPLETED]
    if len(completed) == len(active) and len(active) >= int(volunteers_needed):
        return C.TASK_COMPLETED
    if completed or any(s == C.TA_IN_PROGRESS for s in active):
        return C.TASK_IN_PROGRESS
    if any(s == C.TA_ACCEPTED for s in active):
        return C.TASK_ACCEPTED
    return C.TASK_ASSIGNED


# ------------------------------------------------------------------ adoption
ADOPTION_TRANSITIONS = {
    C.ADOPTION_PENDING: {C.ADOPTION_UNDER_REVIEW, C.ADOPTION_APPROVED, C.ADOPTION_REJECTED, C.ADOPTION_CANCELLED},
    C.ADOPTION_UNDER_REVIEW: {C.ADOPTION_APPROVED, C.ADOPTION_REJECTED, C.ADOPTION_CANCELLED},
    C.ADOPTION_APPROVED: {C.ADOPTION_COMPLETED, C.ADOPTION_REJECTED, C.ADOPTION_CANCELLED},
    C.ADOPTION_REJECTED: set(),
    C.ADOPTION_COMPLETED: set(),
    C.ADOPTION_CANCELLED: set(),
}


def can_transition_adoption(old, new):
    return new in ADOPTION_TRANSITIONS.get(old, set())


def adoption_submission_problem(animal_status, adopter_existing_statuses):
    """Why an adopter cannot apply right now, or ``None`` if they can."""
    if animal_status != C.ANIMAL_AVAILABLE:
        return "This animal is not currently available for adoption."
    if any(s in C.ACTIVE_ADOPTION_STATUSES for s in adopter_existing_statuses):
        return "You already have an active application for this animal."
    return None


def adoption_completion_problem(application_status, animal_status, has_completed_record):
    """Why an adoption cannot be completed, or ``None`` if it can."""
    if application_status != C.ADOPTION_APPROVED:
        return "Only an approved application can be completed."
    if animal_status == C.ANIMAL_ADOPTED or has_completed_record:
        return "This animal has already been adopted."
    return None


# ---------------------------------------------------------------- age helpers
def age_text(months):
    if months is None:
        return "Age unknown"
    months = int(months)
    if months < 1:
        return "Under 1 month"
    if months < 12:
        return f"{months} month{'s' if months != 1 else ''}"
    years, rest = divmod(months, 12)
    text = f"{years} year{'s' if years != 1 else ''}"
    if rest:
        text += f" {rest} mo"
    return text


def age_to_months(years, months):
    """Combine the two age inputs of a form into total months (``None`` if both blank)."""
    if years in (None, "") and months in (None, ""):
        return None
    total = int(years or 0) * 12 + int(months or 0)
    return max(total, 0)


def age_group(months):
    if months is None:
        return None
    for key, (low, high) in C.AGE_GROUP_RANGES.items():
        if months >= low and (high is None or months < high):
            return key
    return None
