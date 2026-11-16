"""Animal records: registration, status changes, shelter admission, photos.

Every public function runs inside one database transaction. Rules that need no
database live in :mod:`app.services.rules`.
"""
import uuid

from sqlalchemy import false, func

from app import constants as C
from app.extensions import db
from app.models import (
    AdoptionApplication, Animal, AnimalImage, AnimalStatusHistory, ShelterAdmission,
    ShelterProfile, User,
)
from app.services import audit, notifications, rules, uploads
from app.services.common import ServiceError, link_for, require, transaction
from app.utils import validators as V
from app.utils.timeutil import local_today, utcnow


# --------------------------------------------------------------------- helpers
def _temp_code():
    return "TMP-" + uuid.uuid4().hex[:20]


def _animal_link(animal):
    return link_for("animals.detail", animal_id=animal.id)


def record_status_change(animal, old_status, new_status, actor, note=None):
    db.session.add(AnimalStatusHistory(
        animal=animal, old_status=old_status, new_status=new_status,
        changed_by=getattr(actor, "id", None), note=note,
    ))


def _clean_choice(value, allowed, label, default=None):
    value = (value or "").strip() if isinstance(value, str) else value
    if not value:
        return default
    require(value in allowed, f"Invalid {label}.")
    return value


def _apply_animal_fields(animal, data):
    """Copy editable fields from ``data`` onto ``animal`` (validating them)."""
    if "name" in data:
        animal.name = V.clean_text(data.get("name"), 80)
    if "animal_type" in data and data.get("animal_type"):
        animal.animal_type = _clean_choice(data["animal_type"], C.ANIMAL_TYPES, "animal type")
    if "breed" in data:
        animal.breed = V.clean_text(data.get("breed"), 80)
    if "age_years" in data or "age_extra_months" in data:  # two-box age input on forms
        try:
            animal.age_months = rules.age_to_months(data.get("age_years"), data.get("age_extra_months"))
        except (TypeError, ValueError):
            raise ServiceError("Age must be entered as whole numbers.")
        require(animal.age_months is None or animal.age_months <= 600, "Age must be at most 50 years.")
    if "age_months" in data:
        months = data.get("age_months")
        if months in (None, ""):
            animal.age_months = None
        else:
            try:
                months = int(months)
            except (TypeError, ValueError):
                raise ServiceError("Age must be a whole number of months.")
            require(0 <= months <= 600, "Age must be between 0 and 600 months.")
            animal.age_months = months
    if "gender" in data:
        animal.gender = _clean_choice(data.get("gender"), C.GENDERS, "gender", default="Unknown")
    if "color" in data:
        animal.color = V.clean_text(data.get("color"), 60)
    if "description" in data:
        animal.description = V.clean_text(data.get("description"))
    if "temperament" in data:
        animal.temperament = V.clean_text(data.get("temperament"), 200)
    if "rescue_date" in data:
        animal.rescue_date = data.get("rescue_date") or None
    if "rescue_location" in data:
        animal.rescue_location = V.clean_text(data.get("rescue_location"), 200)
    if "latitude" in data or "longitude" in data:
        try:
            animal.latitude, animal.longitude = V.parse_coordinates(data.get("latitude"), data.get("longitude"))
        except ValueError as error:
            raise ServiceError(str(error))
    if "health_condition" in data:
        animal.health_condition = V.clean_text(data.get("health_condition"))
    if "medical_status" in data and data.get("medical_status"):
        animal.medical_status = _clean_choice(data["medical_status"], C.MEDICAL_STATUSES, "medical status")
    if "rehabilitation_status" in data and data.get("rehabilitation_status"):
        animal.rehabilitation_status = _clean_choice(data["rehabilitation_status"], C.REHAB_STATUSES, "rehabilitation status")
    if "rehabilitation_notes" in data:
        animal.rehabilitation_notes = V.clean_text(data.get("rehabilitation_notes"))


def _get_shelter(shelter_or_id):
    if shelter_or_id in (None, ""):
        return None
    if isinstance(shelter_or_id, ShelterProfile):
        return shelter_or_id
    shelter = db.session.get(ShelterProfile, int(shelter_or_id))
    require(shelter is not None, "The selected shelter does not exist.")
    return shelter


# ------------------------------------------------------------------ queries
def occupancy_counts():
    """``{shelter_id: animals currently housed}`` in a single query."""
    rows = (
        db.session.query(Animal.shelter_id, func.count(Animal.id))
        .filter(Animal.shelter_id.isnot(None), Animal.status != C.ANIMAL_ADOPTED)
        .group_by(Animal.shelter_id)
        .all()
    )
    return {shelter_id: count for shelter_id, count in rows}


def verified_shelters():
    """Shelters that are verified and active (the only ones that may receive animals)."""
    shelters = ShelterProfile.query.join(User, ShelterProfile.user_id == User.id).filter(
        User.status == C.ACCOUNT_ACTIVE, User.verification_status == C.VERIFY_VERIFIED
    ).order_by(ShelterProfile.shelter_name).all()
    return shelters


def verified_veterinarians():
    return User.query.filter_by(
        role=C.ROLE_VETERINARIAN, status=C.ACCOUNT_ACTIVE, verification_status=C.VERIFY_VERIFIED
    ).order_by(User.full_name).all()


# ---------------------------------------------------------------- permissions
# Who may see or change an animal's record. Routes call these before every action,
# and templates receive the answers so that buttons only appear when they work.
def _owns_shelter_of(user, animal):
    return (user.role == C.ROLE_SHELTER and animal.shelter is not None and animal.shelter.user_id == user.id)


def _rescued(user, animal):
    return user.role == C.ROLE_RESCUER and user.id in (animal.rescuer_id, animal.registered_by)


def can_view_animal(user, animal):
    if not getattr(user, "is_authenticated", False):
        return False
    if user.role == C.ROLE_ADMIN:
        return True
    if user.role == C.ROLE_VETERINARIAN:
        return bool(user.is_verified and user.is_active)
    if user.role == C.ROLE_SHELTER:
        waiting = animal.shelter_id is None and animal.status not in (C.ANIMAL_REPORTED, C.ANIMAL_ADOPTED)
        return bool(user.is_verified and (_owns_shelter_of(user, animal) or waiting))
    if user.role == C.ROLE_RESCUER:
        return bool(user.is_verified and _rescued(user, animal))
    return False


def can_edit_animal(user, animal):
    """Descriptive details and photos."""
    if animal.is_adopted or not can_view_animal(user, animal):
        return False
    if user.role == C.ROLE_ADMIN:
        return True
    if user.role == C.ROLE_SHELTER:
        return _owns_shelter_of(user, animal)
    if user.role == C.ROLE_RESCUER:
        return animal.shelter_id is None  # once a shelter has the animal, the shelter keeps the record
    return False


def can_manage_status(user, animal):
    """Care stage, adoption listing, discharge and rehabilitation progress."""
    if animal.is_adopted or not getattr(user, "is_authenticated", False):
        return False
    return user.role == C.ROLE_ADMIN or (_owns_shelter_of(user, animal) and bool(user.is_verified))


def can_place_animal(user, animal):
    """Admit the animal to a shelter (a shelter can only admit to its own, enforced by the service)."""
    if animal.is_adopted or not can_view_animal(user, animal):
        return False
    if user.role == C.ROLE_ADMIN:
        return True
    if user.role == C.ROLE_RESCUER:
        return animal.shelter_id is None
    if user.role == C.ROLE_SHELTER:
        return animal.shelter_id is None
    return False


def can_assign_veterinarian(user, animal):
    return not animal.is_adopted and getattr(user, "role", None) == C.ROLE_ADMIN


def can_claim_animal(user, animal):
    return (not animal.is_adopted and getattr(user, "role", None) == C.ROLE_VETERINARIAN
            and bool(user.is_verified and user.is_active) and animal.veterinarian_id is None)


def visible_animals_query(user, scope=None):
    """The animals a staff member may browse. Veterinarians see their own cases unless ``scope == 'all'``."""
    query = Animal.query
    if user.role == C.ROLE_ADMIN:
        return query
    if user.role == C.ROLE_VETERINARIAN:
        return query if scope == "all" else query.filter(Animal.veterinarian_id == user.id)
    if user.role == C.ROLE_SHELTER:
        profile = user.shelter_profile
        return query.filter(Animal.shelter_id == (profile.id if profile is not None else -1))
    if user.role == C.ROLE_RESCUER:
        return query.filter(db.or_(Animal.rescuer_id == user.id, Animal.registered_by == user.id))
    return query.filter(false())


# ------------------------------------------------------------- registration
def create_animal(data, actor, report=None, image_files=None):
    """Register a rescued animal (optionally linked to a rescue report).

    ``data`` may contain any of the editable fields plus ``shelter_id``,
    ``capacity_override`` (admin only) and ``override_reason``.
    """
    saved_images = []
    try:
        with transaction():
            animal = Animal(animal_type="Other", status=C.ANIMAL_RESCUED, animal_code=_temp_code())
            if report is not None:
                animal.report_id = report.id
                animal.animal_type = report.animal_type if report.animal_type in C.ANIMAL_TYPES else "Other"
                animal.rescue_location = (report.location_name or "")[:200]
                animal.latitude, animal.longitude = report.latitude, report.longitude
                animal.health_condition = report.animal_condition
            animal.rescue_date = local_today()
            animal.registered_by = getattr(actor, "id", None)
            if getattr(actor, "role", None) == C.ROLE_RESCUER:
                animal.rescuer_id = actor.id
            elif report is not None and report.active_assignment is not None:
                animal.rescuer_id = report.active_assignment.rescuer_id
            elif report is not None and report.latest_assignment is not None:
                animal.rescuer_id = report.latest_assignment.rescuer_id

            _apply_animal_fields(animal, data)
            initial_status = data.get("status") or C.ANIMAL_RESCUED
            require(initial_status in (C.ANIMAL_REPORTED, C.ANIMAL_RESCUED), "A new animal must start as Reported or Rescued.")
            animal.status = initial_status

            db.session.add(animal)
            db.session.flush()
            animal.animal_code = V.format_code("ANM", local_today().year, animal.id)
            record_status_change(animal, None, animal.status, actor, "Animal registered")

            saved_images = uploads.save_uploads(image_files, C.UPLOAD_ANIMALS)
            for index, filename in enumerate(saved_images):
                db.session.add(AnimalImage(animal=animal, filename=filename, is_primary=(index == 0), uploaded_by=getattr(actor, "id", None)))

            shelter = _get_shelter(data.get("shelter_id"))
            if shelter is not None:
                _admit(animal, shelter, actor, bool(data.get("capacity_override")), data.get("override_reason"), "Admitted on registration")

            vet = data.get("veterinarian_id")
            if vet:
                _set_veterinarian(animal, db.session.get(User, int(vet)), actor)

            audit.log_action("animal_registered", "Animal", animal.id, f"{animal.animal_code} registered", user=actor)
            notifications.notify_admins(
                "New animal registered", f"{animal.display_name} ({animal.animal_code}) was added to the animal records.",
                C.NOTIFY_RESCUE, _animal_link(animal),
            )
            if animal.veterinarian_id is None:
                notifications.notify_role(
                    C.ROLE_VETERINARIAN, "Animal awaiting examination",
                    f"{animal.display_name} ({animal.animal_code}) needs a veterinarian. Open the animal to take the case.",
                    C.NOTIFY_MEDICAL, link_for("medical.animal_profile", animal_id=animal.id),
                )
    except Exception:
        for filename in saved_images:
            uploads.delete_upload(C.UPLOAD_ANIMALS, filename)
        raise
    return animal


def update_animal(animal, data, actor):
    """Edit descriptive / care fields. Status changes use :func:`change_status`."""
    require(not animal.is_adopted, "An adopted animal's record can no longer be edited.")
    with transaction():
        _apply_animal_fields(animal, data)
        audit.log_action("animal_updated", "Animal", animal.id, f"{animal.animal_code} updated", user=actor)
    return animal


# ------------------------------------------------------------------- status
def _apply_status(animal, new_status, actor, note=None, via_adoption=False):
    require(new_status in C.ANIMAL_STATUSES, "Invalid animal status.")
    old_status = animal.status
    if old_status == new_status:
        return False
    require(rules.can_transition_animal(old_status, new_status, via_adoption),
            f"An animal cannot move from '{old_status}' to '{new_status}'.")
    if new_status == C.ANIMAL_AVAILABLE:
        problems = rules.adoption_readiness_problems(old_status, animal.medical_status, animal.shelter_id is not None)
        require(not problems, " ".join(problems))
    animal.status = new_status
    animal.available_since = utcnow() if new_status == C.ANIMAL_AVAILABLE else None
    record_status_change(animal, old_status, new_status, actor, note)
    if old_status == C.ANIMAL_AVAILABLE and new_status != C.ANIMAL_ADOPTED:
        close_active_applications(animal, "The animal is no longer listed for adoption.", actor)
    return True


def change_status(animal, new_status, actor, note=None):
    """Move an animal to another care stage (validated by ``rules``)."""
    with transaction():
        changed = _apply_status(animal, new_status, actor, note)
        if changed:
            audit.log_action("animal_status_changed", "Animal", animal.id, f"{animal.animal_code} -> {new_status}", user=actor)
            if new_status == C.ANIMAL_AVAILABLE:
                _announce_available(animal)
            elif animal.shelter_id:
                _notify_shelter(animal, "Animal status updated", f"{animal.display_name} is now '{new_status}'.", C.NOTIFY_RESCUE)
    return animal


def mark_available_for_adoption(animal, actor):
    """Shelter / admin lists the animal for adoption (see ``rules.adoption_readiness_problems``)."""
    return change_status(animal, C.ANIMAL_AVAILABLE, actor, "Marked available for adoption")


def withdraw_from_adoption(animal, actor, note=None):
    require(animal.status == C.ANIMAL_AVAILABLE, "The animal is not currently listed for adoption.")
    return change_status(animal, C.ANIMAL_IN_SHELTER, actor, note or "Withdrawn from adoption listing")


def _announce_available(animal):
    notifications.notify_role(
        C.ROLE_ADOPTER, "New animal available for adoption",
        f"{animal.display_name} ({animal.animal_type}) is looking for a home.",
        C.NOTIFY_ADOPTION, link_for("public.animal_detail", animal_id=animal.id), verified_only=False,
    )


def _notify_shelter(animal, title, message, category):
    if animal.shelter is not None:
        notifications.notify(animal.shelter.user_id, title, message, category, _animal_link(animal))


def close_active_applications(animal, reason, actor=None, status=C.ADOPTION_REJECTED, exclude_id=None):
    """Close every pending / under-review / approved application for ``animal``.

    Used when the animal is adopted by someone else or taken off the adoption
    list, so applicants are never left waiting on an animal that is gone.
    """
    query = AdoptionApplication.query.filter(
        AdoptionApplication.animal_id == animal.id,
        AdoptionApplication.status.in_(C.ACTIVE_ADOPTION_STATUSES),
    )
    if exclude_id is not None:
        query = query.filter(AdoptionApplication.id != exclude_id)
    closed = 0
    for application in query.all():
        application.status = status
        application.review_comment = reason
        application.reviewed_at = utcnow()
        application.reviewed_by = getattr(actor, "id", None)
        notifications.notify(
            application.adopter_id, "Adoption application closed",
            f"Your application {application.application_code} for {animal.display_name} was closed: {reason}",
            C.NOTIFY_ADOPTION, link_for("adoption.detail", application_id=application.id),
        )
        closed += 1
    return closed


# ------------------------------------------------------------------ shelters
def _current_admission(animal):
    for admission in animal.admissions:
        if admission.discharged_at is None:
            return admission
    return None


def _discharge(animal, reason, actor=None):
    admission = _current_admission(animal)
    if admission is not None:
        admission.discharged_at = utcnow()
        admission.discharge_reason = reason


def _admit(animal, shelter, actor, override=False, override_reason=None, note=None):
    require(shelter.is_verified, "Only verified, active shelters can receive animals.")
    require(animal.shelter_id != shelter.id, "The animal is already in this shelter.")
    require(not animal.is_adopted, "An adopted animal cannot be admitted to a shelter.")
    if getattr(actor, "role", None) == C.ROLE_SHELTER:
        require(shelter.user_id == actor.id, "You can only admit animals to your own shelter.")

    used_override = False
    if not rules.has_capacity(shelter.capacity, shelter.current_count):
        require(override and getattr(actor, "role", None) == C.ROLE_ADMIN,
                f"{shelter.shelter_name} is at full capacity ({shelter.capacity}). Only an administrator can override this.")
        require(V.clean_text(override_reason), "Please give a reason for exceeding the shelter's capacity.")
        used_override = True

    previous = animal.shelter_id
    _discharge(animal, "Transferred to another shelter" if previous else None, actor)
    animal.shelter_id = shelter.id
    db.session.add(ShelterAdmission(
        shelter=shelter, animal=animal, admitted_by=getattr(actor, "id", None),
        capacity_override=used_override, override_reason=V.clean_text(override_reason) if used_override else None,
        note=V.clean_text(note),
    ))
    if animal.status in (C.ANIMAL_REPORTED, C.ANIMAL_RESCUED):
        _apply_status(animal, C.ANIMAL_IN_SHELTER, actor, f"Admitted to {shelter.shelter_name}")
    notifications.notify(
        shelter.user_id, "Animal assigned to your shelter",
        f"{animal.display_name} ({animal.animal_code}) has been assigned to {shelter.shelter_name}.",
        C.NOTIFY_RESCUE, _animal_link(animal),
    )


def assign_to_shelter(animal, shelter, actor, override=False, override_reason=None, note=None):
    """Admit ``animal`` to ``shelter`` (capacity is enforced; admin may override)."""
    shelter = _get_shelter(shelter)
    require(shelter is not None, "Please choose a shelter.")
    with transaction():
        _admit(animal, shelter, actor, override, override_reason, note)
        audit.log_action("animal_admitted", "Animal", animal.id, f"{animal.animal_code} -> {shelter.shelter_name}", user=actor)
    return animal


def discharge_from_shelter(animal, actor, reason="Other"):
    require(animal.shelter_id is not None, "The animal is not in a shelter.")
    require(reason in C.DISCHARGE_REASONS and reason != "Adopted", "Choose a valid discharge reason.")
    with transaction():
        _discharge(animal, reason, actor)
        animal.shelter_id = None
        if animal.status in (C.ANIMAL_IN_SHELTER, C.ANIMAL_AVAILABLE):
            _apply_status(animal, C.ANIMAL_RESCUED, actor, f"Discharged from shelter ({reason})")
        audit.log_action("animal_discharged", "Animal", animal.id, f"{animal.animal_code} discharged: {reason}", user=actor)
    return animal


def update_rehabilitation(animal, status, notes, actor):
    """Shelter progress update (Not Started / In Progress / Completed)."""
    require(status in C.REHAB_STATUSES, "Invalid rehabilitation status.")
    with transaction():
        animal.rehabilitation_status = status
        animal.rehabilitation_notes = V.clean_text(notes)
        audit.log_action("rehabilitation_updated", "Animal", animal.id, f"{animal.animal_code}: {status}", user=actor)
    return animal


# --------------------------------------------------------------- veterinarians
def _set_veterinarian(animal, vet, actor):
    require(vet is not None and vet.role == C.ROLE_VETERINARIAN, "Please choose a veterinarian.")
    require(vet.is_verified and vet.is_active, "That veterinarian account is not verified / active.")
    if animal.veterinarian_id == vet.id:
        return
    animal.veterinarian_id = vet.id
    notifications.notify(
        vet, "Animal assigned to you",
        f"{animal.display_name} ({animal.animal_code}) is now assigned to you for medical care.",
        C.NOTIFY_MEDICAL, link_for("medical.animal_profile", animal_id=animal.id),
    )


def assign_veterinarian(animal, vet, actor):
    with transaction():
        _set_veterinarian(animal, vet, actor)
        audit.log_action("vet_assigned", "Animal", animal.id, f"{animal.animal_code} -> {vet.full_name}", user=actor)
    return animal


def claim_animal(animal, vet):
    """A verified veterinarian takes an unassigned animal."""
    require(animal.veterinarian_id is None or animal.veterinarian_id == vet.id, "This animal already has a veterinarian.")
    return assign_veterinarian(animal, vet, vet)


# ---------------------------------------------------------------------- photos
def add_images(animal, files, actor):
    """Attach one or more photographs; the first one becomes the cover if none exists."""
    saved = []
    try:
        with transaction():
            saved = uploads.save_uploads(files, C.UPLOAD_ANIMALS)
            require(saved, "Please choose at least one image.")
            has_cover = animal.primary_image is not None
            for index, filename in enumerate(saved):
                db.session.add(AnimalImage(
                    animal=animal, filename=filename, is_primary=(not has_cover and index == 0),
                    uploaded_by=getattr(actor, "id", None),
                ))
            audit.log_action("animal_photos_added", "Animal", animal.id, f"{len(saved)} photo(s) added", user=actor)
    except Exception:
        for filename in saved:
            uploads.delete_upload(C.UPLOAD_ANIMALS, filename)
        raise
    return animal


def set_primary_image(image, actor):
    with transaction():
        for other in image.animal.images:
            other.is_primary = other.id == image.id
        audit.log_action("animal_cover_changed", "Animal", image.animal_id, "Cover photo changed", user=actor)
    return image


def delete_image(image, actor):
    animal, filename = image.animal, image.filename
    with transaction():
        was_primary = image.is_primary
        db.session.delete(image)
        db.session.flush()
        remaining = [i for i in animal.images if i.id != image.id]
        if was_primary and remaining:
            remaining[0].is_primary = True
        audit.log_action("animal_photo_deleted", "Animal", animal.id, "Photo removed", user=actor)
    uploads.delete_upload(C.UPLOAD_ANIMALS, filename)
    return animal
