"""Veterinary records and vaccinations."""
from datetime import timedelta

from app import constants as C
from app.extensions import db
from app.models import Animal, MedicalRecord, User, Vaccination
from app.services import animal_service, audit, notifications, rules, uploads
from app.services.common import ServiceError, link_for, require, transaction
from app.utils import validators as V
from app.utils.timeutil import local_today


def _profile_link(animal):
    return link_for("medical.animal_profile", animal_id=animal.id)


def can_manage_medical(user, animal=None):
    """Only administrators and verified veterinarians may write official records.

    A veterinarian may only write for animals assigned to them (take an
    unassigned animal first with ``animal_service.claim_animal``).
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if user.role == C.ROLE_ADMIN:
        return True
    if user.role == C.ROLE_VETERINARIAN and user.is_verified and user.is_active:
        return animal is None or animal.veterinarian_id == user.id
    return False


def can_view_medical(user, animal):
    """Medical history is visible to staff involved with the animal."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if user.role == C.ROLE_ADMIN:
        return True
    if user.role == C.ROLE_VETERINARIAN:
        return user.is_verified
    if user.role == C.ROLE_SHELTER and user.is_verified:
        return animal.shelter is not None and animal.shelter.user_id == user.id
    if user.role == C.ROLE_RESCUER and user.is_verified:
        return animal.rescuer_id == user.id
    return False


def refresh_vaccination_status(animal):
    """Recalculate ``animal.vaccination_status`` from its vaccination rows."""
    rows = [(v.vaccine_name, v.vaccination_date, v.next_due_date) for v in animal.vaccinations]
    animal.vaccination_status = rules.compute_vaccination_status(rows, local_today())
    return animal.vaccination_status


def next_vaccination_due(animal):
    """Earliest ``next_due_date`` among the newest dose of every vaccine, or ``None``."""
    newest = {}
    for dose in animal.vaccinations:
        key = dose.vaccine_name.strip().lower()
        if key not in newest or (dose.vaccination_date, dose.id) > (newest[key].vaccination_date, newest[key].id):
            newest[key] = dose
    dates = [dose.next_due_date for dose in newest.values() if dose.next_due_date]
    return min(dates) if dates else None


def _notify_medical_update(animal, title, message):
    recipients = [animal.shelter.user_id] if animal.shelter is not None else []
    notifications.notify_many(recipients, title, message, C.NOTIFY_MEDICAL, _profile_link(animal))
    notifications.notify_admins(title, message, C.NOTIFY_MEDICAL, _profile_link(animal))


def _resolve_vet(vet_id, actor):
    if actor.role == C.ROLE_VETERINARIAN:
        return actor
    require(vet_id, "Please choose the examining veterinarian.")
    vet = db.session.get(User, int(vet_id))
    require(vet is not None and vet.role == C.ROLE_VETERINARIAN and vet.is_verified, "Choose a verified veterinarian.")
    return vet


def _clean_record_fields(data):
    diagnosis = V.clean_text(data.get("diagnosis"))
    require(diagnosis, "Please enter the diagnosis.")
    status = data.get("medical_status")
    require(status in C.MEDICAL_STATUSES, "Please choose the medical status.")
    exam_date = data.get("examination_date") or local_today()
    require(exam_date <= local_today(), "The examination date cannot be in the future.")
    follow_up = data.get("follow_up_date") or None
    require(follow_up is None or follow_up >= exam_date, "The follow-up date cannot be before the examination date.")
    weight = data.get("weight_kg")
    if weight in (None, ""):
        weight = None
    else:
        try:
            weight = float(weight)
        except (TypeError, ValueError):
            raise ServiceError("Weight must be a number.")
        require(0 < weight < 2000, "Weight must be a realistic value in kilograms.")
    return {
        "examination_date": exam_date, "weight_kg": weight, "symptoms": V.clean_text(data.get("symptoms")),
        "diagnosis": diagnosis, "treatment": V.clean_text(data.get("treatment")),
        "medicines": V.clean_text(data.get("medicines")), "medical_status": status,
        "notes": V.clean_text(data.get("notes")), "follow_up_date": follow_up,
    }


def add_medical_record(animal, actor, data, document_file=None):
    """Create an examination record, update the animal's medical status, notify staff."""
    require(can_manage_medical(actor, animal), "Only the assigned veterinarian or an administrator can add medical records.")
    require(not animal.is_adopted, "This animal has been adopted; its medical file is closed.")
    fields = _clean_record_fields(data)
    saved_document = None
    try:
        with transaction():
            vet = _resolve_vet(data.get("veterinarian_id"), actor)
            saved_document = uploads.save_upload(document_file, C.UPLOAD_MEDICAL, "document")
            record = MedicalRecord(
                animal=animal, veterinarian_id=vet.id, created_by=actor.id, document_filename=saved_document,
                document_original_name=(document_file.filename[:255] if saved_document else None), **fields,
            )
            db.session.add(record)
            if animal.veterinarian_id is None:
                animal.veterinarian_id = vet.id
            animal.medical_status = fields["medical_status"]
            next_status = rules.animal_status_for_medical(animal.status, fields["medical_status"])
            if next_status:
                animal_service._apply_status(animal, next_status, actor, "Updated after medical examination")
            audit.log_action("medical_record_added", "Animal", animal.id, f"{animal.animal_code}: {fields['medical_status']}", user=actor)
            _notify_medical_update(animal, "Medical information updated",
                                   f"{animal.display_name}: {fields['medical_status']}. Diagnosis: {fields['diagnosis'][:120]}")
    except Exception:
        if saved_document:
            uploads.delete_upload(C.UPLOAD_MEDICAL, saved_document)
        raise
    return record


def update_medical_record(record, actor, data, document_file=None):
    animal = record.animal
    require(can_manage_medical(actor, animal), "You are not allowed to modify this medical record.")
    fields = _clean_record_fields(data)
    saved_document = None
    old_document = record.document_filename
    try:
        with transaction():
            saved_document = uploads.save_upload(document_file, C.UPLOAD_MEDICAL, "document")
            for key, value in fields.items():
                setattr(record, key, value)
            record.updated_by = actor.id
            if saved_document:
                record.document_filename = saved_document
                record.document_original_name = document_file.filename[:255]
            latest = max(animal.medical_records, key=lambda r: (r.examination_date, r.id))
            if latest.id == record.id:
                animal.medical_status = fields["medical_status"]
            audit.log_action("medical_record_updated", "MedicalRecord", record.id, f"{animal.animal_code}", user=actor)
            _notify_medical_update(animal, "Medical record updated", f"A medical record for {animal.display_name} was updated.")
    except Exception:
        if saved_document:
            uploads.delete_upload(C.UPLOAD_MEDICAL, saved_document)
        raise
    if saved_document and old_document:
        uploads.delete_upload(C.UPLOAD_MEDICAL, old_document)
    return record


def add_vaccination(animal, actor, data, medical_record=None):
    """Record a vaccination and refresh the animal's overall vaccination status."""
    require(can_manage_medical(actor, animal), "Only the assigned veterinarian or an administrator can add vaccinations.")
    name = V.clean_text(data.get("vaccine_name"), 120)
    require(name, "Please enter the vaccine name.")
    given = data.get("vaccination_date") or local_today()
    require(given <= local_today(), "The vaccination date cannot be in the future.")
    due = data.get("next_due_date") or None
    require(due is None or due > given, "The next due date must be after the vaccination date.")
    with transaction():
        vaccination = Vaccination(
            animal=animal, medical_record=medical_record, vaccine_name=name, vaccination_date=given, next_due_date=due,
            administered_by=actor.id if actor.role == C.ROLE_VETERINARIAN else (animal.veterinarian_id or None),
            batch_number=V.clean_text(data.get("batch_number"), 60), notes=V.clean_text(data.get("notes")),
        )
        db.session.add(vaccination)
        db.session.flush()
        refresh_vaccination_status(animal)
        audit.log_action("vaccination_added", "Animal", animal.id, f"{animal.animal_code}: {name}", user=actor)
        _notify_medical_update(animal, "Vaccination recorded", f"{animal.display_name} received {name}. Status: {animal.vaccination_status}.")
    return vaccination


def delete_vaccination(vaccination, actor):
    animal = vaccination.animal
    require(can_manage_medical(actor, animal), "You are not allowed to remove vaccination records.")
    with transaction():
        db.session.delete(vaccination)
        db.session.flush()
        db.session.expire(animal, ["vaccinations"])
        refresh_vaccination_status(animal)
        audit.log_action("vaccination_deleted", "Animal", animal.id, animal.animal_code, user=actor)
    return animal


# ------------------------------------------------------------ due reminders
def due_vaccinations(within_days=14, vet=None, include_overdue=True):
    """Vaccinations whose next dose is due within ``within_days`` (or overdue)."""
    today = local_today()
    horizon = today + timedelta(days=within_days)
    query = Vaccination.query.join(Animal, Vaccination.animal_id == Animal.id).filter(
        Vaccination.next_due_date.isnot(None), Vaccination.next_due_date <= horizon, Animal.status != C.ANIMAL_ADOPTED,
    )
    if not include_overdue:
        query = query.filter(Vaccination.next_due_date >= today)
    if vet is not None:
        query = query.filter(Animal.veterinarian_id == vet.id)
    due = query.order_by(Vaccination.next_due_date).all()
    # Hide doses already superseded by a newer dose of the same vaccine.
    result = []
    for item in due:
        newer = any(
            other.vaccine_name.strip().lower() == item.vaccine_name.strip().lower() and other.vaccination_date > item.vaccination_date
            for other in item.animal.vaccinations
        )
        if not newer:
            result.append(item)
    return result


def send_vaccination_due_notifications(within_days=7):
    """Notify about vaccinations due soon. Safe to call repeatedly (one reminder each)."""
    created = 0
    with transaction():
        for vaccination in due_vaccinations(within_days):
            if vaccination.reminder_sent:
                continue
            animal = vaccination.animal
            recipients = []
            if animal.veterinarian_id:
                recipients.append(animal.veterinarian_id)
            if animal.shelter is not None:
                recipients.append(animal.shelter.user_id)
            admins = User.query.filter_by(role=C.ROLE_ADMIN, status=C.ACCOUNT_ACTIVE).all()
            recipients.extend(a.id for a in admins)
            message = f"{vaccination.vaccine_name} for {animal.display_name} is due on {vaccination.next_due_date:%d %b %Y}."
            created += len(notifications.notify_many(recipients, "Vaccination due", message, C.NOTIFY_MEDICAL, _profile_link(animal)))
            vaccination.reminder_sent = True
            refresh_vaccination_status(animal)
    return created
