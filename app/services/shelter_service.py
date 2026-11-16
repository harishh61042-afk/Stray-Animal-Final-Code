"""Shelter directory, shelter profile changes and admission history."""
from sqlalchemy import func

from app import constants as C
from app.extensions import db
from app.models import Animal, ShelterAdmission, ShelterProfile, User
from app.services import animal_service, audit
from app.services.common import like_pattern, require, transaction
from app.services.user_service import _shelter_values
from app.utils import validators as V


# --------------------------------------------------------------------- queries
def _resident_count():
    """Scalar sub-query: animals currently housed by the shelter of the outer row."""
    return (
        db.session.query(func.count(Animal.id))
        .filter(Animal.shelter_id == ShelterProfile.id, Animal.status != C.ANIMAL_ADOPTED)
        .correlate(ShelterProfile)
        .scalar_subquery()
    )


def _search(query, q):
    q = (q or "").strip()
    if q:
        pattern = like_pattern(q)
        query = query.filter(db.or_(
            ShelterProfile.shelter_name.ilike(pattern, escape="\\"), ShelterProfile.city.ilike(pattern, escape="\\"),
            ShelterProfile.state.ilike(pattern, escape="\\"), ShelterProfile.address.ilike(pattern, escape="\\"),
        ))
    return query


def directory_query(q="", city="", with_space=False):
    """Verified, active shelters for the public directory."""
    query = ShelterProfile.query.join(User, ShelterProfile.user_id == User.id).filter(
        User.status == C.ACCOUNT_ACTIVE, User.verification_status == C.VERIFY_VERIFIED)
    query = _search(query, q)
    if city:
        query = query.filter(ShelterProfile.city == city)
    if with_space:
        query = query.filter(ShelterProfile.capacity > _resident_count())
    return query.order_by(ShelterProfile.shelter_name)


def directory_cities():
    rows = (
        db.session.query(ShelterProfile.city).join(User, ShelterProfile.user_id == User.id)
        .filter(User.status == C.ACCOUNT_ACTIVE, User.verification_status == C.VERIFY_VERIFIED,
                ShelterProfile.city.isnot(None), ShelterProfile.city != "")
        .distinct().order_by(ShelterProfile.city).all()
    )
    return [city for (city,) in rows]


def admin_query(q="", verification=""):
    """Every shelter (also those still waiting for verification) for the administrator's list."""
    query = ShelterProfile.query.join(User, ShelterProfile.user_id == User.id)
    query = _search(query, q)
    if verification in C.VERIFICATION_STATUSES:
        query = query.filter(User.verification_status == verification)
    return query.order_by(ShelterProfile.shelter_name)


def adoptable_counts():
    """``{shelter_id: animals listed for adoption}``."""
    rows = (
        db.session.query(Animal.shelter_id, func.count(Animal.id))
        .filter(Animal.shelter_id.isnot(None), Animal.status == C.ANIMAL_AVAILABLE)
        .group_by(Animal.shelter_id).all()
    )
    return {shelter_id: count for shelter_id, count in rows}


def can_view_shelter(user, shelter):
    """The public sees verified shelters only; administrators and the shelter itself see their page any time."""
    if shelter.is_verified:
        return True
    if not getattr(user, "is_authenticated", False):
        return False
    return user.role == C.ROLE_ADMIN or user.id == shelter.user_id


def admissions_query(shelter=None, state="current", q=""):
    """Admission records (newest first). ``state``: current, past or all."""
    query = ShelterAdmission.query.join(Animal, ShelterAdmission.animal_id == Animal.id)
    if shelter is not None:
        query = query.filter(ShelterAdmission.shelter_id == shelter.id)
    if state == "current":
        query = query.filter(ShelterAdmission.discharged_at.is_(None))
    elif state == "past":
        query = query.filter(ShelterAdmission.discharged_at.isnot(None))
    q = (q or "").strip()
    if q:
        pattern = like_pattern(q)
        query = query.filter(db.or_(
            Animal.name.ilike(pattern, escape="\\"), Animal.animal_code.ilike(pattern, escape="\\"),
            Animal.breed.ilike(pattern, escape="\\"),
        ))
    return query.order_by(ShelterAdmission.admitted_at.desc(), ShelterAdmission.id.desc())


def admission_counts(shelter=None):
    query = db.session.query(
        func.count(ShelterAdmission.id),
        func.sum(db.case((ShelterAdmission.discharged_at.is_(None), 1), else_=0)),
    )
    if shelter is not None:
        query = query.filter(ShelterAdmission.shelter_id == shelter.id)
    total, current = query.one()
    return {"all": int(total or 0), "current": int(current or 0), "past": int((total or 0) - (current or 0))}


def awaiting_placement_query():
    """Animals that have no shelter yet and are ready to be housed (rescued, under treatment or recovering)."""
    return Animal.query.filter(
        Animal.shelter_id.is_(None), Animal.status.notin_([C.ANIMAL_REPORTED, C.ANIMAL_ADOPTED]),
    ).order_by(Animal.created_at.desc(), Animal.id.desc())


def map_markers(shelters, counts=None):
    """Pins for the shelter map (only shelters that have saved coordinates)."""
    from flask import url_for

    counts = counts if counts is not None else animal_service.occupancy_counts()
    markers = []
    for shelter in shelters:
        if not shelter.has_location:
            continue
        used = counts.get(shelter.id, 0)
        free = max(shelter.capacity - used, 0)
        markers.append({
            "lat": shelter.latitude, "lng": shelter.longitude, "title": shelter.shelter_name,
            "subtitle": f"{shelter.city or ''} - {free} of {shelter.capacity} places free".strip(" -"),
            "url": url_for("shelters.detail", shelter_id=shelter.id), "linkLabel": "Open the shelter page",
            "color": "#1f9d63" if free else "#e0614d",
        })
    return markers


# ---------------------------------------------------------------------- update
def update_shelter(shelter, data, actor):
    """Edit a shelter profile (the shelter itself or an administrator)."""
    is_admin = getattr(actor, "role", None) == C.ROLE_ADMIN
    is_owner = getattr(actor, "role", None) == C.ROLE_SHELTER and actor.id == shelter.user_id
    require(is_admin or is_owner, "You can only edit your own shelter profile.")
    owner = shelter.user
    try:
        new_capacity = int(data.get("capacity"))
    except (TypeError, ValueError):
        new_capacity = None
    # An administrator may have admitted animals beyond the old capacity; that must not block other edits.
    housed = shelter.current_count if new_capacity is not None and new_capacity != shelter.capacity else 0
    values = _shelter_values(data, owner.phone, owner.email, housed)
    with transaction():
        for key, value in values.items():
            setattr(shelter, key, value)
        if "registration_number" in data:
            shelter.registration_number = V.clean_text(data.get("registration_number"), 60)
        audit.log_action("shelter_updated", "ShelterProfile", shelter.id, shelter.shelter_name, user=actor)
    return shelter
