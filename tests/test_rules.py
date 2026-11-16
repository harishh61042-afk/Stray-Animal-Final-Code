"""Unit tests for the pure business rules (no database required)."""
from datetime import date, timedelta

from app import constants as C
from app.services import rules
from app.utils import validators as V
from app.utils import timeutil

TODAY = date(2026, 11, 7)


# ------------------------------------------------------------- rescue reports
def test_report_happy_path_transitions():
    assert rules.can_transition_report(C.REPORT_PENDING, C.REPORT_ASSIGNED)
    assert rules.can_transition_report(C.REPORT_ASSIGNED, C.REPORT_IN_PROGRESS)
    assert rules.can_transition_report(C.REPORT_IN_PROGRESS, C.REPORT_RESCUED)
    assert rules.can_transition_report(C.REPORT_RESCUED, C.REPORT_CLOSED)


def test_report_invalid_transitions():
    assert not rules.can_transition_report(C.REPORT_PENDING, C.REPORT_RESCUED)
    assert not rules.can_transition_report(C.REPORT_PENDING, C.REPORT_IN_PROGRESS)
    assert not rules.can_transition_report(C.REPORT_CLOSED, C.REPORT_PENDING)
    assert not rules.can_transition_report("Nonsense", C.REPORT_CLOSED)


def test_rejected_report_can_be_reopened_only_to_review():
    assert rules.allowed_report_transitions(C.REPORT_REJECTED) == [C.REPORT_UNDER_REVIEW]


def test_every_report_status_has_a_transition_entry():
    assert set(rules.REPORT_TRANSITIONS) == set(C.REPORT_STATUSES)


# -------------------------------------------------------------------- animals
def test_adopted_is_final_and_only_reachable_through_adoption():
    assert not rules.can_transition_animal(C.ANIMAL_ADOPTED, C.ANIMAL_IN_SHELTER)
    assert not rules.can_transition_animal(C.ANIMAL_AVAILABLE, C.ANIMAL_ADOPTED)
    assert rules.can_transition_animal(C.ANIMAL_AVAILABLE, C.ANIMAL_ADOPTED, via_adoption=True)


def test_animal_never_returns_to_reported_after_rescue():
    assert not rules.can_transition_animal(C.ANIMAL_RESCUED, C.ANIMAL_REPORTED)
    assert rules.can_transition_animal(C.ANIMAL_REPORTED, C.ANIMAL_RESCUED)


def test_same_status_is_not_a_transition():
    assert not rules.can_transition_animal(C.ANIMAL_RESCUED, C.ANIMAL_RESCUED)


def test_allowed_animal_transitions_exclude_adopted():
    options = rules.allowed_animal_transitions(C.ANIMAL_IN_SHELTER)
    assert C.ANIMAL_ADOPTED not in options
    assert C.ANIMAL_AVAILABLE in options


def test_adoption_readiness():
    assert rules.adoption_readiness_problems(C.ANIMAL_IN_SHELTER, C.MEDICAL_HEALTHY, True) == []
    assert rules.adoption_readiness_problems(C.ANIMAL_IN_SHELTER, C.MEDICAL_HEALTHY, False)
    assert rules.adoption_readiness_problems(C.ANIMAL_IN_SHELTER, C.MEDICAL_CRITICAL, True)
    assert rules.adoption_readiness_problems(C.ANIMAL_ADOPTED, C.MEDICAL_HEALTHY, True)


def test_animal_status_follows_medical_status():
    assert rules.animal_status_for_medical(C.ANIMAL_RESCUED, C.MEDICAL_CRITICAL) == C.ANIMAL_TREATMENT
    assert rules.animal_status_for_medical(C.ANIMAL_AVAILABLE, C.MEDICAL_TREATMENT) == C.ANIMAL_TREATMENT
    assert rules.animal_status_for_medical(C.ANIMAL_TREATMENT, C.MEDICAL_TREATMENT) is None
    assert rules.animal_status_for_medical(C.ANIMAL_TREATMENT, C.MEDICAL_RECOVERING) == C.ANIMAL_RECOVERING
    assert rules.animal_status_for_medical(C.ANIMAL_AVAILABLE, C.MEDICAL_RECOVERING) is None
    assert rules.animal_status_for_medical(C.ANIMAL_RESCUED, C.MEDICAL_HEALTHY) is None
    assert rules.animal_status_for_medical(C.ANIMAL_ADOPTED, C.MEDICAL_CRITICAL) is None


# ---------------------------------------------------------------- vaccination
def test_vaccination_status_none():
    assert rules.compute_vaccination_status([], TODAY) == C.VACC_NONE


def test_vaccination_status_partial_and_full():
    one = [("Rabies", TODAY - timedelta(days=10), TODAY + timedelta(days=355))]
    assert rules.compute_vaccination_status(one, TODAY) == C.VACC_PARTIAL
    two = one + [("DHPP", TODAY - timedelta(days=5), None)]
    assert rules.compute_vaccination_status(two, TODAY) == C.VACC_FULL


def test_vaccination_status_due_when_next_dose_date_has_passed():
    overdue = [("Rabies", TODAY - timedelta(days=400), TODAY - timedelta(days=1))]
    assert rules.compute_vaccination_status(overdue, TODAY) == C.VACC_DUE
    due_today = [("Rabies", TODAY - timedelta(days=365), TODAY)]
    assert rules.compute_vaccination_status(due_today, TODAY) == C.VACC_DUE


def test_vaccination_status_uses_latest_dose_of_each_vaccine():
    records = [
        ("Rabies", TODAY - timedelta(days=400), TODAY - timedelta(days=35)),   # old, overdue
        ("rabies ", TODAY - timedelta(days=10), TODAY + timedelta(days=355)),  # renewed
    ]
    assert rules.compute_vaccination_status(records, TODAY) == C.VACC_PARTIAL


# ------------------------------------------------------------------- shelters
def test_capacity_rules():
    assert rules.has_capacity(10, 9)
    assert not rules.has_capacity(10, 10)
    assert not rules.has_capacity(10, 11)
    assert rules.available_capacity(10, 4) == 6
    assert rules.available_capacity(10, 12) == 0
    assert rules.occupancy_percent(20, 5) == 25
    assert rules.occupancy_percent(0, 5) == 0
    assert rules.occupancy_percent(10, 30) == 100


# ------------------------------------------------------------ volunteer tasks
def test_task_without_volunteers_is_available():
    assert rules.compute_task_status(C.TASK_AVAILABLE, []) == C.TASK_AVAILABLE
    assert rules.compute_task_status(C.TASK_ASSIGNED, [C.TA_DECLINED]) == C.TASK_AVAILABLE


def test_task_status_follows_assignments():
    assert rules.compute_task_status(C.TASK_AVAILABLE, [C.TA_ASSIGNED]) == C.TASK_ASSIGNED
    assert rules.compute_task_status(C.TASK_ASSIGNED, [C.TA_ACCEPTED]) == C.TASK_ACCEPTED
    assert rules.compute_task_status(C.TASK_ACCEPTED, [C.TA_IN_PROGRESS]) == C.TASK_IN_PROGRESS
    assert rules.compute_task_status(C.TASK_IN_PROGRESS, [C.TA_COMPLETED]) == C.TASK_COMPLETED


def test_multi_volunteer_task_completes_only_when_fully_staffed_and_done():
    assert rules.compute_task_status(C.TASK_IN_PROGRESS, [C.TA_COMPLETED], volunteers_needed=2) == C.TASK_IN_PROGRESS
    both = [C.TA_COMPLETED, C.TA_COMPLETED]
    assert rules.compute_task_status(C.TASK_IN_PROGRESS, both, volunteers_needed=2) == C.TASK_COMPLETED


def test_cancelled_task_stays_cancelled():
    assert rules.compute_task_status(C.TASK_CANCELLED, [C.TA_ACCEPTED]) == C.TASK_CANCELLED


def test_open_slots_ignore_declined_and_cancelled():
    assert rules.task_open_slots(3, [C.TA_ACCEPTED, C.TA_DECLINED, C.TA_CANCELLED]) == 2
    assert rules.task_open_slots(1, [C.TA_ASSIGNED]) == 0
    assert rules.task_open_slots(1, [C.TA_ASSIGNED, C.TA_ACCEPTED]) == 0


# ------------------------------------------------------------------- adoption
def test_adoption_status_transitions():
    assert rules.can_transition_adoption(C.ADOPTION_PENDING, C.ADOPTION_UNDER_REVIEW)
    assert rules.can_transition_adoption(C.ADOPTION_UNDER_REVIEW, C.ADOPTION_APPROVED)
    assert rules.can_transition_adoption(C.ADOPTION_APPROVED, C.ADOPTION_COMPLETED)
    assert not rules.can_transition_adoption(C.ADOPTION_PENDING, C.ADOPTION_COMPLETED)
    assert not rules.can_transition_adoption(C.ADOPTION_REJECTED, C.ADOPTION_APPROVED)
    assert not rules.can_transition_adoption(C.ADOPTION_COMPLETED, C.ADOPTION_CANCELLED)


def test_only_available_animals_accept_applications():
    assert rules.adoption_submission_problem(C.ANIMAL_AVAILABLE, []) is None
    for status in C.ANIMAL_STATUSES:
        if status != C.ANIMAL_AVAILABLE:
            assert rules.adoption_submission_problem(status, [])


def test_adopter_cannot_apply_twice_while_application_is_active():
    assert rules.adoption_submission_problem(C.ANIMAL_AVAILABLE, [C.ADOPTION_PENDING])
    assert rules.adoption_submission_problem(C.ANIMAL_AVAILABLE, [C.ADOPTION_APPROVED])
    assert rules.adoption_submission_problem(C.ANIMAL_AVAILABLE, [C.ADOPTION_REJECTED, C.ADOPTION_CANCELLED]) is None


def test_adoption_completion_guards():
    assert rules.adoption_completion_problem(C.ADOPTION_APPROVED, C.ANIMAL_AVAILABLE, False) is None
    assert rules.adoption_completion_problem(C.ADOPTION_PENDING, C.ANIMAL_AVAILABLE, False)
    assert rules.adoption_completion_problem(C.ADOPTION_APPROVED, C.ANIMAL_ADOPTED, False)
    assert rules.adoption_completion_problem(C.ADOPTION_APPROVED, C.ANIMAL_AVAILABLE, True)


# ----------------------------------------------------------------------- ages
def test_age_text_and_groups():
    assert rules.age_text(None) == "Age unknown"
    assert rules.age_text(0) == "Under 1 month"
    assert rules.age_text(1) == "1 month"
    assert rules.age_text(7) == "7 months"
    assert rules.age_text(12) == "1 year"
    assert rules.age_text(27) == "2 years 3 mo"
    assert rules.age_group(6) == "baby"
    assert rules.age_group(12) == "young"
    assert rules.age_group(40) == "adult"
    assert rules.age_group(120) == "senior"
    assert rules.age_group(None) is None


def test_age_to_months():
    assert rules.age_to_months("", "") is None
    assert rules.age_to_months(2, 3) == 27
    assert rules.age_to_months("1", None) == 12
    assert rules.age_to_months(None, 5) == 5


# ----------------------------------------------------------------- validators
def test_email_validation():
    assert V.is_valid_email("asha@example.com")
    assert V.is_valid_email("a.b+c@mail.example.co.in")
    assert not V.is_valid_email("asha@")
    assert not V.is_valid_email("asha example.com")
    assert not V.is_valid_email("")
    assert V.normalize_email("  Asha@Example.COM ") == "asha@example.com"


def test_phone_validation():
    assert V.is_valid_phone("+91 98765 43210")
    assert V.is_valid_phone("9876543210")
    assert not V.is_valid_phone("12345")
    assert not V.is_valid_phone("call me")
    assert not V.is_valid_phone("")


def test_coordinate_parsing():
    assert V.parse_coordinates("", "") == (None, None)
    assert V.parse_coordinates("12.5", "77.25") == (12.5, 77.25)
    for bad in [("12.5", ""), ("95", "10"), ("10", "190"), ("abc", "10")]:
        try:
            V.parse_coordinates(*bad)
        except ValueError:
            continue
        raise AssertionError(f"{bad} should have been rejected")


def test_password_policy():
    assert V.password_problems("Sup3rSecret") == []
    assert V.password_problems("short1")
    assert V.password_problems("allletters")
    assert V.password_problems("12345678")


def test_file_signature_detection():
    assert V.detect_file_type(b"\x89PNG\r\n\x1a\n" + b"0" * 20) == "png"
    assert V.detect_file_type(b"\xff\xd8\xff\xe0" + b"0" * 20) == "jpg"
    assert V.detect_file_type(b"GIF89a" + b"0" * 20) == "gif"
    assert V.detect_file_type(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "webp"
    assert V.detect_file_type(b"%PDF-1.7\n") == "pdf"
    assert V.detect_file_type(b"<?php echo 1; ?>") is None
    assert V.detect_file_type(b"") is None


def test_unique_filenames_are_unique_and_keep_extension():
    names = {V.unique_filename("JPG") for _ in range(50)}
    assert len(names) == 50
    assert all(n.endswith(".jpg") for n in names)
    assert V.unique_filename(".jpeg").endswith(".jpg")


def test_code_format_and_clean_text():
    assert V.format_code("RPT", 2026, 42) == "RPT-2026-00042"
    assert V.clean_text("   ") is None
    assert V.clean_text(" hi ") == "hi"
    assert V.clean_text("abcdef", 3) == "abc"


# ------------------------------------------------------------------ time utils
def test_time_helpers():
    from datetime import datetime

    value = datetime(2026, 11, 6, 20, 0)  # 20:00 UTC -> 01:30 next day IST
    assert timeutil.to_local(value).strftime("%Y-%m-%d %H:%M") == "2026-11-07 01:30"
    assert timeutil.format_datetime(None) == "-"
    now = datetime(2026, 11, 7, 12, 0)
    assert timeutil.time_ago(datetime(2026, 11, 7, 11, 59, 40), now) == "just now"
    assert timeutil.time_ago(datetime(2026, 11, 7, 11, 55), now) == "5 minutes ago"
    assert timeutil.time_ago(datetime(2026, 11, 7, 9, 0), now) == "3 hours ago"
    assert timeutil.time_ago(datetime(2026, 11, 5, 12, 0), now) == "2 days ago"
    assert timeutil.month_start(date(2026, 2, 15), 3) == date(2025, 11, 1)
