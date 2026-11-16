"""Adoption workflow: apply -> review -> approve / reject -> complete."""
import uuid

from app import constants as C
from app.extensions import db
from app.models import AdoptionApplication, AdoptionRecord, Animal
from app.services import animal_service, audit, notifications, rules
from app.services.common import ServiceError, link_for, require, transaction
from app.utils import validators as V
from app.utils.timeutil import local_today, utcnow


def _detail_link(application):
    return link_for("adoption.detail", application_id=application.id)


def can_review(user, application):
    """Administrators, and the shelter that currently houses the animal."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if user.role == C.ROLE_ADMIN:
        return True
    shelter = application.animal.shelter
    return bool(user.role == C.ROLE_SHELTER and user.is_verified and shelter is not None and shelter.user_id == user.id)


def can_view(user, application):
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    return application.adopter_id == user.id or can_review(user, application)


# --------------------------------------------------------------- submission
def _validate_application(data):
    cleaned = {}
    name = V.clean_text(data.get("applicant_name"), 100)
    require(name, "Please enter your full name.")
    cleaned["applicant_name"] = name
    email = V.normalize_email(data.get("applicant_email"))
    require(V.is_valid_email(email), "Please enter a valid e-mail address.")
    cleaned["applicant_email"] = email
    phone = V.clean_text(data.get("applicant_phone"), 20)
    require(phone and V.is_valid_phone(phone), "Please enter a valid phone number.")
    cleaned["applicant_phone"] = phone
    address = V.clean_text(data.get("address"))
    require(address, "Please enter your address.")
    cleaned["address"] = address
    city = V.clean_text(data.get("city"), 80)
    require(city, "Please enter your city.")
    cleaned["city"] = city
    cleaned["state"] = V.clean_text(data.get("state"), 80)
    cleaned["pincode"] = V.clean_text(data.get("pincode"), 10)
    cleaned["occupation"] = V.clean_text(data.get("occupation"), 100)
    require(data.get("housing_type") in C.HOUSING_TYPES, "Please choose your housing type.")
    cleaned["housing_type"] = data["housing_type"]
    members = data.get("household_members")
    if members in (None, ""):
        cleaned["household_members"] = None
    else:
        try:
            members = int(members)
        except (TypeError, ValueError):
            raise ServiceError("Household members must be a whole number.")
        require(1 <= members <= 50, "Household members must be between 1 and 50.")
        cleaned["household_members"] = members
    cleaned["has_other_pets"] = bool(data.get("has_other_pets"))
    cleaned["other_pets_details"] = V.clean_text(data.get("other_pets_details")) if cleaned["has_other_pets"] else None
    cleaned["previous_experience"] = V.clean_text(data.get("previous_experience"))
    reason = V.clean_text(data.get("adoption_reason"))
    require(reason and len(reason) >= 20, "Please explain why you want to adopt (at least 20 characters).")
    cleaned["adoption_reason"] = reason
    require(data.get("agreed_to_terms"), "You must accept the adoption declaration to continue.")
    cleaned["agreed_to_terms"] = True
    return cleaned


def submit_application(animal, adopter, data):
    """An adopter applies for an animal that is listed as available."""
    require(adopter.role == C.ROLE_ADOPTER, "Only adopter accounts can submit adoption applications.")
    require(adopter.is_active, "Your account is not active.")
    cleaned = _validate_application(data)
    with transaction():
        db.session.refresh(animal)  # work with the latest status
        existing = [a.status for a in AdoptionApplication.query.filter_by(animal_id=animal.id, adopter_id=adopter.id).all()]
        problem = rules.adoption_submission_problem(animal.status, existing)
        require(problem is None, problem)
        application = AdoptionApplication(
            application_code="TMP-" + uuid.uuid4().hex[:20], animal=animal, adopter_id=adopter.id,
            status=C.ADOPTION_PENDING, **cleaned,
        )
        db.session.add(application)
        db.session.flush()
        application.application_code = V.format_code("ADP", local_today().year, application.id)
        recipients = [animal.shelter.user_id] if animal.shelter is not None else []
        notifications.notify_many(
            recipients, "New adoption request",
            f"{adopter.full_name} applied to adopt {animal.display_name} ({application.application_code}).",
            C.NOTIFY_ADOPTION, _detail_link(application))
        notifications.notify_admins(
            "New adoption request", f"{adopter.full_name} applied to adopt {animal.display_name} ({application.application_code}).",
            C.NOTIFY_ADOPTION, _detail_link(application))
        notifications.notify(
            adopter, "Application submitted",
            f"Your application {application.application_code} for {animal.display_name} was received.",
            C.NOTIFY_ADOPTION, _detail_link(application))
        audit.log_action("adoption_applied", "AdoptionApplication", application.id, application.application_code, user=adopter)
    return application


# ------------------------------------------------------------------- review
def _set_status(application, new_status, actor, comment=None):
    require(rules.can_transition_adoption(application.status, new_status),
            f"An application cannot move from '{application.status}' to '{new_status}'.")
    application.status = new_status
    application.reviewed_by = getattr(actor, "id", None)
    application.reviewed_at = utcnow()
    if comment is not None:
        application.review_comment = V.clean_text(comment)


def mark_under_review(application, actor, comment=None):
    require(can_review(actor, application), "You are not allowed to review this application.")
    with transaction():
        _set_status(application, C.ADOPTION_UNDER_REVIEW, actor, comment)
        notifications.notify(application.adopter_id, "Application under review",
                             f"Your application {application.application_code} is being reviewed.", C.NOTIFY_ADOPTION, _detail_link(application))
        audit.log_action("adoption_under_review", "AdoptionApplication", application.id, application.application_code, user=actor)
    return application


def approve_application(application, actor, comment=None):
    require(can_review(actor, application), "You are not allowed to review this application.")
    animal = application.animal
    require(animal.status == C.ANIMAL_AVAILABLE, "The animal is no longer available for adoption.")
    with transaction():
        other_approved = AdoptionApplication.query.filter(
            AdoptionApplication.animal_id == animal.id, AdoptionApplication.status == C.ADOPTION_APPROVED,
            AdoptionApplication.id != application.id).count()
        require(other_approved == 0, "Another application for this animal is already approved. Complete or reject it first.")
        _set_status(application, C.ADOPTION_APPROVED, actor, comment)
        notifications.notify(application.adopter_id, "Adoption request approved",
                             f"Good news! Your application {application.application_code} for {animal.display_name} was approved.",
                             C.NOTIFY_ADOPTION, _detail_link(application))
        audit.log_action("adoption_approved", "AdoptionApplication", application.id, application.application_code, user=actor)
    return application


def reject_application(application, actor, comment):
    require(can_review(actor, application), "You are not allowed to review this application.")
    require(V.clean_text(comment), "Please add a comment explaining the decision.")
    with transaction():
        _set_status(application, C.ADOPTION_REJECTED, actor, comment)
        notifications.notify(application.adopter_id, "Adoption request rejected",
                             f"Your application {application.application_code} for {application.animal.display_name} was not approved. "
                             f"Reason: {V.clean_text(comment)}", C.NOTIFY_ADOPTION, _detail_link(application))
        audit.log_action("adoption_rejected", "AdoptionApplication", application.id, application.application_code, user=actor)
    return application


def cancel_application(application, actor):
    """The adopter withdraws their own application."""
    require(application.adopter_id == getattr(actor, "id", None), "You can only cancel your own applications.")
    with transaction():
        _set_status(application, C.ADOPTION_CANCELLED, actor, "Cancelled by the applicant")
        recipients = [application.animal.shelter.user_id] if application.animal.shelter is not None else []
        notifications.notify_many(recipients, "Adoption application cancelled",
                                  f"{application.applicant_name} cancelled {application.application_code}.", C.NOTIFY_ADOPTION, _detail_link(application))
        audit.log_action("adoption_cancelled", "AdoptionApplication", application.id, application.application_code, user=actor)
    return application


# --------------------------------------------------------------- completion
def complete_adoption(application, actor, adoption_date=None, final_notes=None):
    """Finalise an approved adoption in ONE transaction.

    * writes the adoption record (UNIQUE per animal)
    * marks the application Completed and the animal Adopted
    * closes the animal's shelter admission
    * closes every competing application and tells those applicants
    """
    require(can_review(actor, application), "You are not allowed to complete this adoption.")
    adoption_date = adoption_date or local_today()
    require(adoption_date <= local_today(), "The adoption date cannot be in the future.")
    with transaction():
        # Lock the animal row (MySQL/InnoDB) so two staff members cannot complete two adoptions at once.
        animal = db.session.query(Animal).filter(Animal.id == application.animal_id).with_for_update().one()
        db.session.refresh(application)
        has_record = AdoptionRecord.query.filter_by(animal_id=animal.id).first() is not None
        problem = rules.adoption_completion_problem(application.status, animal.status, has_record)
        require(problem is None, problem)

        shelter_id = animal.shelter_id
        record = AdoptionRecord(
            application_id=application.id, animal_id=animal.id, adopter_id=application.adopter_id, shelter_id=shelter_id,
            adoption_date=adoption_date, completed_by=actor.id, final_notes=V.clean_text(final_notes),
        )
        db.session.add(record)
        _set_status(application, C.ADOPTION_COMPLETED, actor)
        animal_service._apply_status(animal, C.ANIMAL_ADOPTED, actor, f"Adopted by {application.applicant_name}", via_adoption=True)
        animal_service._discharge(animal, "Adopted", actor)
        closed = animal_service.close_active_applications(
            animal, "This animal has been adopted by another applicant.", actor, exclude_id=application.id)
        notifications.notify(application.adopter_id, "Adoption completed",
                             f"Congratulations! The adoption of {animal.display_name} is complete.", C.NOTIFY_ADOPTION, _detail_link(application))
        if animal.shelter is not None:
            notifications.notify(animal.shelter.user_id, "Animal adopted",
                                 f"{animal.display_name} ({animal.animal_code}) was adopted by {application.applicant_name}.",
                                 C.NOTIFY_ADOPTION, link_for("animals.detail", animal_id=animal.id))
        audit.log_action("adoption_completed", "AdoptionRecord", application.id,
                         f"{animal.animal_code} adopted; {closed} other application(s) closed", user=actor)
    return record
