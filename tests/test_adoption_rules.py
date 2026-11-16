"""The adoption workflow and its rules, tested through the same service functions the web pages use.

Rules covered: only available animals can be applied for, one active application per adopter and animal, only
adopters apply, only the housing shelter or an administrator reviews, rejection needs a reason, only one approval per
animal, completion is atomic (record + animal + admission + competing applications) and can happen only once.
"""
import re
from datetime import timedelta
from types import SimpleNamespace

import pytest

pytest.importorskip("flask_sqlalchemy")
pytest.importorskip("flask_login")
pytest.importorskip("flask_wtf")

from app import constants as C  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import AdoptionApplication, AdoptionRecord, Animal, Notification, ShelterAdmission, ShelterProfile, User  # noqa: E402
from app.services import adoption_service  # noqa: E402
from app.services.common import ServiceError  # noqa: E402
from app.utils.timeutil import local_today  # noqa: E402
from tests.helpers import (  # noqa: E402
    adoption_data, count, create_animal, create_application, create_user, field, form_values, login_as, url,
)


@pytest.fixture()
def world(app):
    """An administrator, two shelters, two adopters and one available animal living in the first shelter (ids only)."""
    shelter = create_user(app, C.ROLE_SHELTER)
    return SimpleNamespace(
        admin=create_user(app, C.ROLE_ADMIN),
        shelter=shelter,
        other_shelter=create_user(app, C.ROLE_SHELTER),
        adopter=create_user(app, C.ROLE_ADOPTER),
        other_adopter=create_user(app, C.ROLE_ADOPTER),
        animal=create_animal(app, shelter_user_id=shelter),
    )


def apply(app, world, *, animal_id=None, adopter_id=None, **overrides):
    return create_application(app, animal_id or world.animal, adopter_id or world.adopter, **overrides)


def act(app, function, application_id, actor_id, *args, **kwargs):
    """Run ``function(application, actor, ...)`` the way a request would, inside one application context."""
    with app.app_context():
        application = db.session.get(AdoptionApplication, application_id)
        actor = db.session.get(User, actor_id)
        return function(application, actor, *args, **kwargs)


def status_of(app, application_id):
    return field(app, AdoptionApplication, application_id, "status")


# ------------------------------------------------------------------ applying
def test_an_adopter_can_apply_for_an_available_animal(app, world):
    application_id = apply(app, world)
    with app.app_context():
        application = db.session.get(AdoptionApplication, application_id)
        assert application.status == C.ADOPTION_PENDING
        assert re.match(r"^ADP-\d{4}-\d{5}$", application.application_code)
        assert application.agreed_to_terms is True
    for recipient in (world.shelter, world.admin, world.adopter):  # everybody involved is told
        assert count(app, Notification, user_id=recipient, category=C.NOTIFY_ADOPTION) == 1


def test_an_adopter_cannot_hold_two_active_applications_for_one_animal(app, world):
    apply(app, world)
    with pytest.raises(ServiceError, match="already have an active application"):
        apply(app, world)
    assert count(app, AdoptionApplication) == 1
    apply(app, world, adopter_id=world.other_adopter)  # a different adopter may apply too
    assert count(app, AdoptionApplication) == 2


@pytest.mark.parametrize("status", [C.ANIMAL_REPORTED, C.ANIMAL_RESCUED, C.ANIMAL_TREATMENT, C.ANIMAL_RECOVERING,
                                    C.ANIMAL_IN_SHELTER, C.ANIMAL_ADOPTED])
def test_only_animals_listed_as_available_can_be_applied_for(app, world, status):
    animal_id = create_animal(app, shelter_user_id=world.shelter, status=status)
    with pytest.raises(ServiceError, match="not currently available"):
        apply(app, world, animal_id=animal_id)
    assert count(app, AdoptionApplication) == 0


@pytest.mark.parametrize("role", [C.ROLE_RESCUER, C.ROLE_VOLUNTEER, C.ROLE_VETERINARIAN, C.ROLE_SHELTER, C.ROLE_ADMIN])
def test_only_adopter_accounts_can_apply(app, world, role):
    other = create_user(app, role)
    with pytest.raises(ServiceError, match="Only adopter accounts"):
        apply(app, world, adopter_id=other)


def test_an_inactive_adopter_cannot_apply(app, world):
    suspended = create_user(app, C.ROLE_ADOPTER, status=C.ACCOUNT_SUSPENDED)
    with pytest.raises(ServiceError, match="not active"):
        apply(app, world, adopter_id=suspended)


@pytest.mark.parametrize("changes, message", [
    ({"applicant_name": ""}, "full name"),
    ({"applicant_email": "nope"}, "valid e-mail"),
    ({"applicant_phone": "abc"}, "valid phone"),
    ({"address": ""}, "your address"),
    ({"city": ""}, "your city"),
    ({"housing_type": "Castle"}, "housing type"),
    ({"household_members": 0}, "between 1 and 50"),
    ({"adoption_reason": "Too short"}, "at least 20 characters"),
    ({"agreed_to_terms": False}, "adoption declaration"),
])
def test_incomplete_applications_are_refused(app, world, changes, message):
    with pytest.raises(ServiceError, match=message):
        apply(app, world, **changes)
    assert count(app, AdoptionApplication) == 0


def test_the_apply_page_creates_an_application_for_the_signed_in_adopter(app, client, world):
    login_as(app, client, C.ROLE_ADOPTER, email="applicant@pawconnect.test")
    address = url(app, "adoption.apply", animal_id=world.animal)
    assert client.get(address).status_code == 200

    response = client.post(address, data=form_values(adoption_data()))
    assert response.status_code == 302
    assert "/adoption/application/" in response.headers["Location"]
    assert count(app, AdoptionApplication) == 1

    again = client.get(address)  # a second visit goes to the existing application instead of a new form
    assert again.status_code == 302 and "/adoption/application/" in again.headers["Location"]


def test_the_apply_page_is_for_adopters_only(app, client, world):
    address = url(app, "adoption.apply", animal_id=world.animal)
    assert client.get(address).status_code == 302  # signed out -> sign in
    login_as(app, client, C.ROLE_VOLUNTEER)
    assert client.get(address).status_code == 403


# ------------------------------------------------------------------ reviewing
def test_the_shelter_that_houses_the_animal_can_approve(app, world):
    application_id = apply(app, world)
    act(app, adoption_service.approve_application, application_id, world.shelter, "Looks like a great home")
    assert status_of(app, application_id) == C.ADOPTION_APPROVED
    assert field(app, AdoptionApplication, application_id, "review_comment") == "Looks like a great home"
    assert field(app, AdoptionApplication, application_id, "reviewed_by") == world.shelter
    assert count(app, Notification, user_id=world.adopter, title="Adoption request approved") == 1


def test_an_administrator_can_review_any_application(app, world):
    application_id = apply(app, world)
    act(app, adoption_service.mark_under_review, application_id, world.admin)
    assert status_of(app, application_id) == C.ADOPTION_UNDER_REVIEW
    act(app, adoption_service.approve_application, application_id, world.admin)
    assert status_of(app, application_id) == C.ADOPTION_APPROVED


@pytest.mark.parametrize("actor", ["other_shelter", "adopter", "other_adopter"])
def test_nobody_else_can_review_an_application(app, world, actor):
    application_id = apply(app, world)
    with pytest.raises(ServiceError, match="not allowed"):
        act(app, adoption_service.approve_application, application_id, getattr(world, actor))
    with pytest.raises(ServiceError, match="not allowed"):
        act(app, adoption_service.reject_application, application_id, getattr(world, actor), "No")
    assert status_of(app, application_id) == C.ADOPTION_PENDING


def test_rejecting_needs_a_reason_and_is_final(app, world):
    application_id = apply(app, world)
    with pytest.raises(ServiceError, match="comment"):
        act(app, adoption_service.reject_application, application_id, world.shelter, "   ")
    assert status_of(app, application_id) == C.ADOPTION_PENDING

    act(app, adoption_service.reject_application, application_id, world.shelter, "The home is too small.")
    assert status_of(app, application_id) == C.ADOPTION_REJECTED
    assert field(app, AdoptionApplication, application_id, "review_comment") == "The home is too small."

    with pytest.raises(ServiceError, match="cannot move"):
        act(app, adoption_service.approve_application, application_id, world.shelter)  # a rejected one stays rejected


def test_only_one_application_per_animal_can_be_approved(app, world):
    first = apply(app, world)
    second = apply(app, world, adopter_id=world.other_adopter)
    act(app, adoption_service.approve_application, first, world.shelter)
    with pytest.raises(ServiceError, match="already approved"):
        act(app, adoption_service.approve_application, second, world.shelter)
    assert status_of(app, first) == C.ADOPTION_APPROVED
    assert status_of(app, second) == C.ADOPTION_PENDING


def test_an_animal_that_is_no_longer_available_cannot_be_approved(app, world):
    application_id = apply(app, world)
    with app.app_context():
        db.session.get(Animal, world.animal).status = C.ANIMAL_TREATMENT
        db.session.commit()
    with pytest.raises(ServiceError, match="no longer available"):
        act(app, adoption_service.approve_application, application_id, world.shelter)


# ------------------------------------------------------------------ cancelling
def test_an_adopter_can_cancel_only_their_own_application(app, world):
    application_id = apply(app, world)
    with pytest.raises(ServiceError, match="only cancel your own"):
        act(app, adoption_service.cancel_application, application_id, world.other_adopter)
    act(app, adoption_service.cancel_application, application_id, world.adopter)
    assert status_of(app, application_id) == C.ADOPTION_CANCELLED
    apply(app, world)  # after cancelling, the adopter may apply again
    assert count(app, AdoptionApplication) == 2


# ------------------------------------------------------------------ completing
def test_completing_an_adoption_updates_everything_together(app, world):
    winner = apply(app, world)
    competitor = apply(app, world, adopter_id=world.other_adopter)
    act(app, adoption_service.approve_application, winner, world.shelter)
    act(app, adoption_service.complete_adoption, winner, world.shelter, None, "Home visit done.")

    assert status_of(app, winner) == C.ADOPTION_COMPLETED
    assert field(app, Animal, world.animal, "status") == C.ANIMAL_ADOPTED

    with app.app_context():
        record = AdoptionRecord.query.one()  # exactly one record, written by this transaction
        assert record.animal_id == world.animal and record.application_id == winner
        assert record.adopter_id == world.adopter and record.final_notes == "Home visit done."
        assert record.adoption_date == local_today()

        admission = ShelterAdmission.query.filter_by(animal_id=world.animal).one()
        assert admission.discharged_at is not None and admission.discharge_reason == "Adopted"

        shelter = ShelterProfile.query.filter_by(user_id=world.shelter).one()
        assert shelter.current_count == 0  # the adopted animal has left the shelter's count

    assert status_of(app, competitor) == C.ADOPTION_REJECTED  # the other applicant is told, not left waiting
    assert "adopted by another applicant" in field(app, AdoptionApplication, competitor, "review_comment")
    assert count(app, Notification, user_id=world.adopter, title="Adoption completed") == 1
    assert count(app, Notification, user_id=world.other_adopter, category=C.NOTIFY_ADOPTION) >= 2


def test_only_an_approved_application_can_be_completed(app, world):
    application_id = apply(app, world)
    with pytest.raises(ServiceError, match="Only an approved application"):
        act(app, adoption_service.complete_adoption, application_id, world.shelter)
    assert count(app, AdoptionRecord) == 0
    assert field(app, Animal, world.animal, "status") == C.ANIMAL_AVAILABLE


def test_an_adoption_can_be_completed_only_once(app, world):
    application_id = apply(app, world)
    act(app, adoption_service.approve_application, application_id, world.shelter)
    act(app, adoption_service.complete_adoption, application_id, world.shelter)
    with pytest.raises(ServiceError, match="Only an approved application"):
        act(app, adoption_service.complete_adoption, application_id, world.shelter)
    assert count(app, AdoptionRecord) == 1


def test_an_adoption_date_in_the_future_is_refused(app, world):
    application_id = apply(app, world)
    act(app, adoption_service.approve_application, application_id, world.shelter)
    with pytest.raises(ServiceError, match="cannot be in the future"):
        act(app, adoption_service.complete_adoption, application_id, world.shelter, local_today() + timedelta(days=1))
    assert status_of(app, application_id) == C.ADOPTION_APPROVED
    assert count(app, AdoptionRecord) == 0


def test_only_the_housing_shelter_or_an_administrator_can_complete(app, world):
    application_id = apply(app, world)
    act(app, adoption_service.approve_application, application_id, world.shelter)
    with pytest.raises(ServiceError, match="not allowed"):
        act(app, adoption_service.complete_adoption, application_id, world.other_shelter)
    act(app, adoption_service.complete_adoption, application_id, world.admin)
    assert status_of(app, application_id) == C.ADOPTION_COMPLETED


def test_an_adopted_animal_leaves_the_public_adoption_list(app, client, world):
    assert "Buddy" in client.get(url(app, "public.animals")).get_data(as_text=True)
    application_id = apply(app, world)
    act(app, adoption_service.approve_application, application_id, world.shelter)
    act(app, adoption_service.complete_adoption, application_id, world.shelter)
    assert "Buddy" not in client.get(url(app, "public.animals")).get_data(as_text=True)
