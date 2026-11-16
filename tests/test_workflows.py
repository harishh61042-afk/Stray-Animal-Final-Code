"""Rescue coordination, volunteer approval and tasks, shelter capacity, medical records and notifications."""
from datetime import timedelta
from types import SimpleNamespace

import pytest

pytest.importorskip("flask_sqlalchemy")
pytest.importorskip("flask_login")
pytest.importorskip("flask_wtf")

from app import constants as C  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import (  # noqa: E402
    Animal, AnimalReport, MedicalRecord, Notification, RescueAssignment, ShelterAdmission, ShelterProfile, User,
    Vaccination, VolunteerProfile, VolunteerTask,
)
from app.services import animal_service, medical_service, notifications, rescue_service, volunteer_service  # noqa: E402
from app.services.common import ServiceError  # noqa: E402
from app.utils.timeutil import local_today, utcnow  # noqa: E402
from tests.helpers import count, create_animal, create_report, create_user, field, login_as, url  # noqa: E402


def load(models, *ids):
    """Load one row per model by id inside the current application context."""
    return [db.session.get(model, object_id) for model, object_id in zip(models, ids)]


# ================================================================== rescue coordination
@pytest.fixture()
def rescue(app):
    reporter = create_user(app, C.ROLE_ADOPTER)
    report_id, code = create_report(app, reporter_id=reporter)
    return SimpleNamespace(
        admin=create_user(app, C.ROLE_ADMIN), rescuer=create_user(app, C.ROLE_RESCUER),
        other_rescuer=create_user(app, C.ROLE_RESCUER), reporter=reporter, report=report_id, code=code,
    )


def assign(app, rescue, rescuer_id=None, actor_id=None):
    """Assign a rescuer to the report; returns the assignment id."""
    with app.app_context():
        report, rescuer, actor = load((AnimalReport, User, User), rescue.report, rescuer_id or rescue.rescuer,
                                      actor_id or rescue.admin)
        return rescue_service.assign_rescuer(report, rescuer, actor).id


def respond(app, assignment_id, rescuer_id, accept, note=None):
    with app.app_context():
        assignment, rescuer = load((RescueAssignment, User), assignment_id, rescuer_id)
        return rescue_service.respond_to_assignment(assignment, rescuer, accept, note)


def complete(app, report_id, actor_id, details="The dog was treated and taken to a shelter."):
    with app.app_context():
        report, actor = load((AnimalReport, User), report_id, actor_id)
        return rescue_service.complete_rescue(report, actor, details)


def report_status(app, rescue):
    return field(app, AnimalReport, rescue.report, "status")


def test_assign_accept_and_complete_a_rescue(app, rescue):
    assignment_id = assign(app, rescue)
    assert report_status(app, rescue) == C.REPORT_ASSIGNED
    assert count(app, Notification, user_id=rescue.rescuer, title="New rescue case assigned") == 1
    assert count(app, Notification, user_id=rescue.reporter, title="Rescue status updated") == 1  # the reporter hears too

    respond(app, assignment_id, rescue.rescuer, accept=True)
    assert report_status(app, rescue) == C.REPORT_IN_PROGRESS
    assert field(app, RescueAssignment, assignment_id, "status") == C.ASSIGNMENT_ACCEPTED
    assert count(app, Notification, user_id=rescue.admin, title="Rescue case accepted") == 1

    complete(app, rescue.report, rescue.rescuer)
    assert report_status(app, rescue) == C.REPORT_RESCUED
    assert field(app, RescueAssignment, assignment_id, "status") == C.ASSIGNMENT_COMPLETED


def test_only_administrators_can_assign_rescuers(app, rescue):
    with pytest.raises(ServiceError, match="Only an administrator"):
        assign(app, rescue, actor_id=rescue.rescuer)
    assert report_status(app, rescue) == C.REPORT_PENDING


def test_an_unverified_rescuer_cannot_be_assigned(app, rescue):
    newcomer = create_user(app, C.ROLE_RESCUER, verified=False)
    with pytest.raises(ServiceError, match="not verified"):
        assign(app, rescue, rescuer_id=newcomer)
    assert count(app, RescueAssignment) == 0


def test_declining_needs_a_reason_and_the_case_can_be_reassigned(app, rescue):
    assignment_id = assign(app, rescue)
    with pytest.raises(ServiceError, match="why you cannot take"):
        respond(app, assignment_id, rescue.rescuer, accept=False, note="")

    respond(app, assignment_id, rescue.rescuer, accept=False, note="I am away this week.")
    assert report_status(app, rescue) == C.REPORT_UNDER_REVIEW
    assert field(app, RescueAssignment, assignment_id, "status") == C.ASSIGNMENT_REJECTED
    assert count(app, Notification, user_id=rescue.admin, title="Rescue case declined") == 1

    assign(app, rescue, rescuer_id=rescue.other_rescuer)  # the administrator picks someone else
    assert report_status(app, rescue) == C.REPORT_ASSIGNED


def test_only_the_assigned_rescuer_can_answer_the_assignment(app, rescue):
    assignment_id = assign(app, rescue)
    with pytest.raises(ServiceError, match="not assigned to you"):
        respond(app, assignment_id, rescue.other_rescuer, accept=True)
    respond(app, assignment_id, rescue.rescuer, accept=True)
    with pytest.raises(ServiceError, match="already been answered"):
        respond(app, assignment_id, rescue.rescuer, accept=True)


def test_only_the_rescuer_who_accepted_the_case_can_complete_it(app, rescue):
    assignment_id = assign(app, rescue)
    with pytest.raises(ServiceError, match="Only the assigned rescuer"):
        complete(app, rescue.report, rescue.other_rescuer)
    respond(app, assignment_id, rescue.rescuer, accept=True)
    with pytest.raises(ServiceError, match="Only the assigned rescuer"):
        complete(app, rescue.report, rescue.other_rescuer)
    with pytest.raises(ServiceError, match="describe the outcome"):
        complete(app, rescue.report, rescue.rescuer, details="  ")


def test_rejecting_a_report_needs_a_reason(app, rescue):
    with app.app_context():
        report, admin = load((AnimalReport, User), rescue.report, rescue.admin)
        with pytest.raises(ServiceError, match="reason for rejecting"):
            rescue_service.update_status(report, C.REPORT_REJECTED, admin, None)
        rescue_service.update_status(report, C.REPORT_REJECTED, admin, "Duplicate of another report.")
        assert report.status == C.REPORT_REJECTED
        assert report.rejection_reason == "Duplicate of another report."


def test_a_rejected_or_closed_report_cannot_be_assigned(app, rescue):
    with app.app_context():
        report, admin = load((AnimalReport, User), rescue.report, rescue.admin)
        rescue_service.update_status(report, C.REPORT_REJECTED, admin, "Not an animal in need.")
    with pytest.raises(ServiceError, match="can no longer be assigned"):
        assign(app, rescue)


# ================================================================== volunteers and tasks
def task_data(**overrides):
    data = {"title": "Feed the shelter dogs", "task_type": C.TASK_TYPES[0], "volunteers_needed": 1}
    data.update(overrides)
    return data


def make_task(app, actor_id, **overrides):
    with app.app_context():
        actor = db.session.get(User, actor_id)
        return volunteer_service.create_task(actor, task_data(**overrides)).id


def accept(app, task_id, volunteer_id):
    with app.app_context():
        task, volunteer = load((VolunteerTask, User), task_id, volunteer_id)
        return volunteer_service.accept_task(task, volunteer)


def test_an_administrator_approves_a_volunteer_application(app):
    admin = create_user(app, C.ROLE_ADMIN)
    volunteer = create_user(app, C.ROLE_VOLUNTEER, approved=False)
    with app.app_context():
        profile = VolunteerProfile.query.filter_by(user_id=volunteer).one()
        assert db.session.get(User, volunteer).is_approved_volunteer is False
        volunteer_service.review_application(profile, db.session.get(User, admin), True)
        assert profile.application_status == C.APPLICATION_APPROVED
        assert db.session.get(User, volunteer).is_approved_volunteer is True
        with pytest.raises(ServiceError, match="already been reviewed"):
            volunteer_service.review_application(profile, db.session.get(User, admin), True)
    assert count(app, Notification, user_id=volunteer, category=C.NOTIFY_ACCOUNT) == 1


def test_rejecting_a_volunteer_needs_a_reason_and_an_administrator(app):
    admin = create_user(app, C.ROLE_ADMIN)
    rescuer = create_user(app, C.ROLE_RESCUER)
    volunteer = create_user(app, C.ROLE_VOLUNTEER, approved=False)
    with app.app_context():
        profile = VolunteerProfile.query.filter_by(user_id=volunteer).one()
        with pytest.raises(ServiceError, match="Only an administrator"):
            volunteer_service.review_application(profile, db.session.get(User, rescuer), True)
        with pytest.raises(ServiceError, match="reason for rejecting"):
            volunteer_service.review_application(profile, db.session.get(User, admin), False, "")
        volunteer_service.review_application(profile, db.session.get(User, admin), False, "Please add your availability.")
        assert profile.application_status == C.APPLICATION_REJECTED
        assert db.session.get(User, volunteer).is_approved_volunteer is False


def test_only_administrators_and_verified_rescuers_create_tasks(app):
    with pytest.raises(ServiceError, match="Only administrators and verified rescuers"):
        make_task(app, create_user(app, C.ROLE_VOLUNTEER))
    with pytest.raises(ServiceError, match="Only administrators and verified rescuers"):
        make_task(app, create_user(app, C.ROLE_RESCUER, verified=False))
    assert make_task(app, create_user(app, C.ROLE_RESCUER))  # a verified rescuer may
    assert make_task(app, create_user(app, C.ROLE_ADMIN))


def test_an_unapproved_volunteer_cannot_accept_a_task(app):
    task_id = make_task(app, create_user(app, C.ROLE_ADMIN))
    waiting = create_user(app, C.ROLE_VOLUNTEER, approved=False)
    with pytest.raises(ServiceError, match="Only approved volunteers"):
        accept(app, task_id, waiting)
    assert field(app, VolunteerTask, task_id, "status") == C.TASK_AVAILABLE


def test_an_approved_volunteer_accepts_a_task_and_slots_are_limited(app):
    task_id = make_task(app, create_user(app, C.ROLE_ADMIN), volunteers_needed=1)
    first = create_user(app, C.ROLE_VOLUNTEER)
    second = create_user(app, C.ROLE_VOLUNTEER)

    accept(app, task_id, first)
    assert field(app, VolunteerTask, task_id, "status") == C.TASK_ACCEPTED
    with pytest.raises(ServiceError, match="all the volunteers it needs"):
        accept(app, task_id, second)
    with pytest.raises(ServiceError, match="already accepted"):
        accept(app, task_id, first)


def test_a_task_with_a_past_deadline_is_refused(app):
    with pytest.raises(ServiceError, match="deadline must be in the future"):
        make_task(app, create_user(app, C.ROLE_ADMIN), due_at=utcnow() - timedelta(days=1))


def test_new_tasks_notify_volunteers(app):
    volunteer = create_user(app, C.ROLE_VOLUNTEER)
    make_task(app, create_user(app, C.ROLE_ADMIN))
    assert count(app, Notification, user_id=volunteer, category=C.NOTIFY_TASK) == 1


# ================================================================== shelters and capacity
def shelter_of(user_id):
    return ShelterProfile.query.filter_by(user_id=user_id).one()


def admit(app, animal_id, shelter_user_id, actor_id, **options):
    with app.app_context():
        animal, actor = load((Animal, User), animal_id, actor_id)
        return animal_service.assign_to_shelter(animal, shelter_of(shelter_user_id), actor, **options)


@pytest.fixture()
def full_shelter(app):
    """A shelter with room for exactly one animal that already houses one, plus a second animal waiting."""
    shelter = create_user(app, C.ROLE_SHELTER, capacity=1)
    create_animal(app, shelter_user_id=shelter, status=C.ANIMAL_IN_SHELTER, name="Resident")
    return SimpleNamespace(
        shelter=shelter, admin=create_user(app, C.ROLE_ADMIN),
        waiting=create_animal(app, status=C.ANIMAL_RESCUED, name="Newcomer"),
    )


def test_a_shelter_with_room_accepts_an_animal(app):
    shelter = create_user(app, C.ROLE_SHELTER, capacity=2)
    admin = create_user(app, C.ROLE_ADMIN)
    animal = create_animal(app, status=C.ANIMAL_RESCUED)
    admit(app, animal, shelter, admin)
    assert field(app, Animal, animal, "status") == C.ANIMAL_IN_SHELTER
    with app.app_context():
        assert shelter_of(shelter).current_count == 1
        assert shelter_of(shelter).available_capacity == 1
    assert count(app, Notification, user_id=shelter, category=C.NOTIFY_RESCUE) == 1


def test_a_full_shelter_refuses_another_animal(app, full_shelter):
    with pytest.raises(ServiceError, match="full capacity"):
        admit(app, full_shelter.waiting, full_shelter.shelter, full_shelter.admin)
    with pytest.raises(ServiceError, match="full capacity"):  # the shelter itself cannot override either
        admit(app, full_shelter.waiting, full_shelter.shelter, full_shelter.shelter, override=True, override_reason="Please")
    assert field(app, Animal, full_shelter.waiting, "shelter_id") is None


def test_only_an_administrator_can_override_the_capacity_and_must_say_why(app, full_shelter):
    with pytest.raises(ServiceError, match="reason for exceeding"):
        admit(app, full_shelter.waiting, full_shelter.shelter, full_shelter.admin, override=True, override_reason="")

    admit(app, full_shelter.waiting, full_shelter.shelter, full_shelter.admin, override=True,
          override_reason="Emergency: the other shelter is flooded.")
    with app.app_context():
        admission = ShelterAdmission.query.filter_by(animal_id=full_shelter.waiting).one()
        assert admission.capacity_override is True
        assert admission.override_reason == "Emergency: the other shelter is flooded."
        assert shelter_of(full_shelter.shelter).current_count == 2  # now above the capacity of 1
        assert shelter_of(full_shelter.shelter).is_full


def test_a_shelter_admits_only_to_its_own_house_and_only_when_verified(app):
    mine = create_user(app, C.ROLE_SHELTER)
    other = create_user(app, C.ROLE_SHELTER)
    unverified = create_user(app, C.ROLE_SHELTER, verified=False)
    admin = create_user(app, C.ROLE_ADMIN)
    animal = create_animal(app, status=C.ANIMAL_RESCUED)

    with pytest.raises(ServiceError, match="your own shelter"):
        admit(app, animal, other, mine)
    with pytest.raises(ServiceError, match="verified, active shelters"):
        admit(app, animal, unverified, admin)
    assert field(app, Animal, animal, "shelter_id") is None


def test_discharging_frees_a_place(app):
    shelter = create_user(app, C.ROLE_SHELTER, capacity=1)
    admin = create_user(app, C.ROLE_ADMIN)
    animal = create_animal(app, shelter_user_id=shelter, status=C.ANIMAL_IN_SHELTER)
    with app.app_context():
        animal_row, actor = load((Animal, User), animal, admin)
        animal_service.discharge_from_shelter(animal_row, actor, "Released back")
        assert shelter_of(shelter).current_count == 0
        assert animal_row.status == C.ANIMAL_RESCUED


# ================================================================== medical records
def test_only_the_assigned_veterinarian_or_an_administrator_writes_medical_records(app):
    admin = create_user(app, C.ROLE_ADMIN)
    vet = create_user(app, C.ROLE_VETERINARIAN)
    other_vet = create_user(app, C.ROLE_VETERINARIAN)
    adopter = create_user(app, C.ROLE_ADOPTER)
    animal_id = create_animal(app, status=C.ANIMAL_RESCUED)
    record = {"diagnosis": "Sprained front leg", "medical_status": C.MEDICAL_TREATMENT, "treatment": "Rest and a bandage."}

    with app.app_context():
        animal, admin_user = load((Animal, User), animal_id, admin)
        with pytest.raises(ServiceError, match="Only the assigned veterinarian"):
            medical_service.add_medical_record(animal, db.session.get(User, adopter), record)
        with pytest.raises(ServiceError, match="Only the assigned veterinarian"):  # not assigned to this animal yet
            medical_service.add_medical_record(animal, db.session.get(User, vet), record)

        animal_service.assign_veterinarian(animal, db.session.get(User, vet), admin_user)
        with pytest.raises(ServiceError, match="Only the assigned veterinarian"):  # a colleague still cannot
            medical_service.add_medical_record(animal, db.session.get(User, other_vet), record)

        saved = medical_service.add_medical_record(animal, db.session.get(User, vet), record)
        assert saved.veterinarian_id == vet
        assert animal.medical_status == C.MEDICAL_TREATMENT
        assert animal.status == C.ANIMAL_TREATMENT  # a serious finding moves the animal to medical treatment

    assert count(app, MedicalRecord, animal_id=animal_id) == 1


def test_medical_records_need_a_diagnosis_and_a_realistic_date(app):
    admin = create_user(app, C.ROLE_ADMIN)
    animal_id = create_animal(app, status=C.ANIMAL_RESCUED)
    with app.app_context():
        animal, actor = load((Animal, User), animal_id, admin)
        with pytest.raises(ServiceError, match="enter the diagnosis"):
            medical_service.add_medical_record(animal, actor, {"diagnosis": "", "medical_status": C.MEDICAL_HEALTHY})
        with pytest.raises(ServiceError, match="cannot be in the future"):
            medical_service.add_medical_record(animal, actor, {
                "diagnosis": "Healthy", "medical_status": C.MEDICAL_HEALTHY,
                "examination_date": local_today() + timedelta(days=2)})
    assert count(app, MedicalRecord) == 0


def test_a_vaccination_updates_the_vaccination_status(app):
    admin = create_user(app, C.ROLE_ADMIN)
    animal_id = create_animal(app, status=C.ANIMAL_RESCUED)
    with app.app_context():
        animal, actor = load((Animal, User), animal_id, admin)
        assert animal.vaccination_status == C.VACC_NONE
        medical_service.add_vaccination(animal, actor, {"vaccine_name": "Rabies"})
        assert animal.vaccination_status == C.VACC_PARTIAL  # one vaccine
        medical_service.add_vaccination(animal, actor, {"vaccine_name": "Distemper"})
        assert animal.vaccination_status == C.VACC_FULL  # two different vaccines
        with pytest.raises(ServiceError, match="vaccine name"):
            medical_service.add_vaccination(animal, actor, {"vaccine_name": ""})
    assert count(app, Vaccination, animal_id=animal_id) == 2


# ================================================================== notifications
def test_notification_centre_and_polling_api(app, client):
    user_id = login_as(app, client, C.ROLE_ADOPTER)
    other_id = create_user(app, C.ROLE_ADOPTER)
    with app.app_context():
        notifications.notify(user_id, "First", "Hello there", C.NOTIFY_SYSTEM, "/adoption/my")
        notifications.notify(user_id, "Second", "Another message", C.NOTIFY_ADOPTION)
        notifications.notify(other_id, "Not yours", "Private to someone else", C.NOTIFY_SYSTEM)
        db.session.commit()

    page = client.get(url(app, "notifications.index"))
    body = page.get_data(as_text=True)
    assert page.status_code == 200 and "First" in body and "Second" in body and "Not yours" not in body

    count_response = client.get(url(app, "notifications.api_count"))
    assert count_response.get_json() == {"count": 2}
    recent = client.get(url(app, "notifications.api_recent")).get_json()
    assert recent["count"] == 2 and {item["title"] for item in recent["items"]} == {"First", "Second"}

    with app.app_context():
        mine = Notification.query.filter_by(user_id=user_id, title="First").one().id
        others = Notification.query.filter_by(user_id=other_id).one().id
    ajax = {"X-Requested-With": "XMLHttpRequest"}
    assert client.post(url(app, "notifications.mark_read", notification_id=others), headers=ajax).status_code == 404
    assert client.post(url(app, "notifications.mark_read", notification_id=mine), headers=ajax).status_code == 200
    assert client.get(url(app, "notifications.api_count")).get_json() == {"count": 1}

    assert client.post(url(app, "notifications.mark_all_read"), headers=ajax).get_json()["count"] == 1
    assert client.get(url(app, "notifications.api_count")).get_json() == {"count": 0}
    assert count(app, Notification, user_id=other_id, is_read=False) == 1  # someone else's stays unread
