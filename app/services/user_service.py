"""Accounts: registration, sign-in, profiles, passwords and admin account actions."""
import secrets
from datetime import timedelta

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app import constants as C
from app.extensions import db
from app.models import (
    RescuerProfile, ShelterProfile, User, UserProfile, VeterinarianProfile, VolunteerProfile,
)
from app.services import audit, notifications, uploads
from app.services.common import ServiceError, link_for, require, transaction
from app.utils import validators as V
from app.utils.timeutil import utcnow

# Fields a user may edit on their own role profile (whitelist).
ROLE_PROFILE_FIELDS = {
    C.ROLE_VOLUNTEER: ("skills", "experience", "availability", "motivation", "emergency_contact_name", "emergency_contact_phone"),
    C.ROLE_RESCUER: ("organization", "experience_years", "service_area", "has_vehicle"),
    C.ROLE_VETERINARIAN: ("clinic_name", "specialization", "qualification", "experience_years", "clinic_address", "consultation_hours"),
    C.ROLE_SHELTER: ("shelter_name", "address", "city", "state", "pincode", "latitude", "longitude",
                     "contact_phone", "contact_email", "website", "capacity", "description"),
}


def _years(value, label="Experience"):
    if value in (None, ""):
        return None
    try:
        years = int(value)
    except (TypeError, ValueError):
        raise ServiceError(f"{label} must be a whole number of years.")
    require(0 <= years <= 70, f"{label} must be between 0 and 70 years.")
    return years


def _shelter_values(data, user_phone=None, user_email=None, current_count=0):
    name = V.clean_text(data.get("shelter_name"), 150)
    require(name, "Please enter the shelter name.")
    address = V.clean_text(data.get("address"))
    require(address, "Please enter the shelter address.")
    city = V.clean_text(data.get("city"), 80)
    require(city, "Please enter the shelter's city.")
    try:
        capacity = int(data.get("capacity"))
    except (TypeError, ValueError):
        raise ServiceError("Capacity must be a whole number.")
    require(1 <= capacity <= 5000, "Capacity must be between 1 and 5000 animals.")
    require(capacity >= current_count, f"Capacity cannot be lower than the {current_count} animals currently housed.")
    try:
        latitude, longitude = V.parse_coordinates(data.get("latitude"), data.get("longitude"))
    except ValueError as error:
        raise ServiceError(str(error))
    contact_phone = V.clean_text(data.get("contact_phone"), 20) or user_phone
    require(not contact_phone or V.is_valid_phone(contact_phone), "Please enter a valid shelter contact phone.")
    contact_email = V.normalize_email(data.get("contact_email")) or user_email
    require(not contact_email or V.is_valid_email(contact_email), "Please enter a valid shelter contact e-mail.")
    website = V.clean_text(data.get("website"), 200)
    require(not website or website.lower().startswith(("http://", "https://")), "The website must start with http:// or https://")
    return {
        "shelter_name": name, "address": address, "city": city, "state": V.clean_text(data.get("state"), 80),
        "pincode": V.clean_text(data.get("pincode"), 10), "latitude": latitude, "longitude": longitude,
        "contact_phone": contact_phone, "contact_email": contact_email, "website": website, "capacity": capacity,
        "description": V.clean_text(data.get("description")),
    }


# ------------------------------------------------------------ registration
def register_user(data, files=None):
    """Create an account with the role's profile. Admin accounts can never be self-registered."""
    files = files or {}
    role = data.get("role")
    require(role in C.REGISTRABLE_ROLES, "Please choose a valid account type.")
    email = V.normalize_email(data.get("email"))
    require(V.is_valid_email(email), "Please enter a valid e-mail address.")
    full_name = V.clean_text(data.get("full_name"), 100)
    require(full_name and len(full_name) >= 2, "Please enter your full name.")
    phone = V.clean_text(data.get("phone"), 20)
    require(phone and V.is_valid_phone(phone), "Please enter a valid phone number.")
    password = data.get("password") or ""
    problems = V.password_problems(password)
    require(not problems, " ".join(problems))
    if "confirm_password" in data:
        require(password == data.get("confirm_password"), "The two passwords do not match.")
    require(User.query.filter(db.func.lower(User.email) == email).first() is None, "An account with this e-mail already exists.")

    # Role specific validation happens before anything is written.
    role_values = {}
    if role == C.ROLE_VOLUNTEER:
        skills = V.clean_text(data.get("skills"))
        require(skills, "Please list your skills.")
        availability = V.clean_text(data.get("availability"), 200)
        require(availability, "Please tell us when you are available.")
        role_values = {
            "skills": skills, "availability": availability, "experience": V.clean_text(data.get("experience")),
            "motivation": V.clean_text(data.get("motivation")),
            "emergency_contact_name": V.clean_text(data.get("emergency_contact_name"), 100),
            "emergency_contact_phone": V.clean_text(data.get("emergency_contact_phone"), 20),
        }
    elif role == C.ROLE_RESCUER:
        area = V.clean_text(data.get("service_area"), 150)
        require(area, "Please enter the area you can serve.")
        details = V.clean_text(data.get("verification_details"))
        require(details and len(details) >= 10, "Please add verification details (at least 10 characters).")
        role_values = {
            "organization": V.clean_text(data.get("organization"), 150), "experience_years": _years(data.get("experience_years")),
            "service_area": area, "has_vehicle": bool(data.get("has_vehicle")), "verification_details": details,
        }
    elif role == C.ROLE_VETERINARIAN:
        license_number = V.clean_text(data.get("license_number"), 60)
        require(license_number, "Please enter your veterinary licence / registration number.")
        qualification = V.clean_text(data.get("qualification"), 150)
        require(qualification, "Please enter your qualification.")
        role_values = {
            "license_number": license_number, "qualification": qualification, "clinic_name": V.clean_text(data.get("clinic_name"), 150),
            "specialization": V.clean_text(data.get("specialization"), 100), "experience_years": _years(data.get("experience_years")),
            "clinic_address": V.clean_text(data.get("clinic_address")), "consultation_hours": V.clean_text(data.get("consultation_hours"), 100),
            "verification_details": V.clean_text(data.get("verification_details")),
        }
    elif role == C.ROLE_SHELTER:
        role_values = _shelter_values(data, user_phone=phone, user_email=email)
        role_values["registration_number"] = V.clean_text(data.get("registration_number"), 60)
        details = V.clean_text(data.get("verification_details"))
        require(details and len(details) >= 10, "Please add verification details (at least 10 characters).")
        role_values["verification_details"] = details

    saved_document = None
    try:
        with transaction():
            if role in C.VERIFICATION_REQUIRED_ROLES:
                saved_document = uploads.save_upload(files.get("verification_document"), C.UPLOAD_VERIFICATION, "document")
                role_values["verification_document"] = saved_document
            user = User(email=email, full_name=full_name, phone=phone, role=role, status=C.ACCOUNT_ACTIVE,
                        verification_status=C.VERIFY_PENDING if role in C.VERIFICATION_REQUIRED_ROLES else C.VERIFY_NOT_REQUIRED)
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            db.session.add(UserProfile(
                user=user, address=V.clean_text(data.get("address")) if role != C.ROLE_SHELTER else None,
                city=V.clean_text(data.get("city"), 80) if role != C.ROLE_SHELTER else None,
                state=V.clean_text(data.get("state"), 80) if role != C.ROLE_SHELTER else None,
                pincode=V.clean_text(data.get("pincode"), 10) if role != C.ROLE_SHELTER else None))
            if role == C.ROLE_VOLUNTEER:
                db.session.add(VolunteerProfile(user=user, application_status=C.APPLICATION_PENDING, **role_values))
            elif role == C.ROLE_RESCUER:
                db.session.add(RescuerProfile(user=user, **role_values))
            elif role == C.ROLE_VETERINARIAN:
                db.session.add(VeterinarianProfile(user=user, **role_values))
            elif role == C.ROLE_SHELTER:
                db.session.add(ShelterProfile(user=user, **role_values))
            _welcome_and_alert_admins(user)
            audit.log_action("user_registered", "User", user.id, f"{user.email} ({user.role})", user=user)
    except IntegrityError:
        db.session.rollback()
        if saved_document:
            uploads.delete_upload(C.UPLOAD_VERIFICATION, saved_document)
        raise ServiceError("An account with this e-mail already exists.")
    except Exception:
        if saved_document:
            uploads.delete_upload(C.UPLOAD_VERIFICATION, saved_document)
        raise
    return user


def _welcome_and_alert_admins(user):
    if user.role in C.VERIFICATION_REQUIRED_ROLES:
        welcome = "Welcome to PawConnect! Your account is waiting for administrator verification. You will be notified as soon as it is complete."
        notifications.notify_admins(f"New {user.role_label.lower()} awaiting verification",
                                    f"{user.full_name} registered as a {user.role_label.lower()}.", C.NOTIFY_ACCOUNT,
                                    link_for("admin.verifications"))
    elif user.role == C.ROLE_VOLUNTEER:
        welcome = "Welcome to PawConnect! Your volunteer application is waiting for approval. You can follow its status from your dashboard."
        notifications.notify_admins("New volunteer application", f"{user.full_name} applied to volunteer.", C.NOTIFY_ACCOUNT,
                                    link_for("volunteers.applications"))
    else:
        welcome = "Welcome to PawConnect! Browse animals waiting for a home and send an adoption request."
    notifications.notify(user, "Welcome to PawConnect", welcome, C.NOTIFY_ACCOUNT, link_for("dashboard.index"))


# ----------------------------------------------------------------- sign in
def authenticate(email, password):
    """Check credentials. Raises ``ServiceError`` with a safe message on failure."""
    generic = "Invalid e-mail or password."
    user = User.query.filter_by(email=V.normalize_email(email)).first()
    if user is None:
        raise ServiceError(generic)
    if user.is_locked:
        minutes = max(1, int((user.locked_until - utcnow()).total_seconds() // 60) + 1)
        raise ServiceError(f"Too many failed sign-in attempts. Please try again in {minutes} minute(s).")
    if not user.check_password(password):
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= current_app.config.get("MAX_FAILED_LOGINS", 5):
            user.locked_until = utcnow() + timedelta(minutes=current_app.config.get("LOCKOUT_MINUTES", 15))
            user.failed_login_attempts = 0
            audit.log_action("account_locked", "User", user.id, user.email, user=user)
        db.session.commit()
        raise ServiceError(generic)
    if user.status != C.ACCOUNT_ACTIVE:
        raise ServiceError(f"This account is {user.status}. Please contact an administrator.")
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = utcnow()
    audit.log_action("login", "User", user.id, user.email, user=user)
    db.session.commit()
    return user


# ---------------------------------------------------------------- passwords
def change_password(user, current_password, new_password):
    require(user.check_password(current_password), "Your current password is incorrect.")
    problems = V.password_problems(new_password)
    require(not problems, " ".join(problems))
    require(not user.check_password(new_password), "Choose a password different from your current one.")
    with transaction():
        user.set_password(new_password)
        user.must_change_password = False
        audit.log_action("password_changed", "User", user.id, user.email, user=user)
    return user


def _temporary_password():
    """A random one-time password that satisfies the password rules (letters and digits, 8+ characters)."""
    return f"Paw-{secrets.token_hex(3)}-{secrets.randbelow(90) + 10}"


def admin_reset_password(user, actor):
    """Give ``user`` a one-time temporary password (shown once to the administrator)."""
    require(getattr(actor, "role", None) == C.ROLE_ADMIN, "Only an administrator can reset passwords.")
    temporary = _temporary_password()
    with transaction():
        user.set_password(temporary)
        user.must_change_password = True
        user.failed_login_attempts = 0
        user.locked_until = None
        audit.log_action("password_reset_by_admin", "User", user.id, user.email, user=actor)
    return temporary


# ------------------------------------------------------------------ profiles
def update_profile(user, data):
    """Update the signed-in user's own details (name, phone, address and role profile)."""
    full_name = V.clean_text(data.get("full_name"), 100)
    require(full_name and len(full_name) >= 2, "Please enter your full name.")
    phone = V.clean_text(data.get("phone"), 20)
    require(phone and V.is_valid_phone(phone), "Please enter a valid phone number.")
    with transaction():
        user.full_name = full_name
        user.phone = phone
        profile = user.profile or UserProfile(user=user)
        db.session.add(profile)
        for field in ("address", "city", "state", "pincode", "bio"):
            if field in data:
                setattr(profile, field, V.clean_text(data.get(field), {"city": 80, "state": 80, "pincode": 10}.get(field)))
        if "date_of_birth" in data:
            profile.date_of_birth = data.get("date_of_birth") or None
        _update_role_profile(user, data)
        audit.log_action("profile_updated", "User", user.id, user.email, user=user)
    return user


def _update_role_profile(user, data):
    role_profile = user.role_profile
    allowed = ROLE_PROFILE_FIELDS.get(user.role, ())
    if role_profile is None or not any(field in data for field in allowed):
        return
    if user.role == C.ROLE_SHELTER:
        merged = {field: data.get(field, getattr(role_profile, field)) for field in allowed}
        for field in ("latitude", "longitude"):
            if field in data:
                merged[field] = data.get(field)
        for key, value in _shelter_values(merged, user.phone, user.email, role_profile.current_count).items():
            setattr(role_profile, key, value)
        return
    for field in allowed:
        if field not in data:
            continue
        value = data.get(field)
        if field == "experience_years":
            value = _years(value)
        elif field == "has_vehicle":
            value = bool(value)
        elif isinstance(value, str):
            value = V.clean_text(value)
        setattr(role_profile, field, value)
    if user.role == C.ROLE_VOLUNTEER:
        require(role_profile.skills, "Please list your skills.")


# ------------------------------------------------------------ admin actions
def admin_create_user(data, actor):
    """Create an account of any type as an administrator. Returns ``(user, temporary_password or None)``.

    The administrator vouches for the person, so rescuer / veterinarian / shelter accounts start *verified* and
    volunteers start *approved*. When no password is given a temporary one is generated (the caller shows it once).
    Nothing is e-mailed: the administrator hands the credentials over.
    """
    require(getattr(actor, "role", None) == C.ROLE_ADMIN, "Only an administrator can create accounts.")
    role = data.get("role")
    require(role in C.ALL_ROLES, "Please choose a valid account type.")
    email = V.normalize_email(data.get("email"))
    require(V.is_valid_email(email), "Please enter a valid e-mail address.")
    full_name = V.clean_text(data.get("full_name"), 100)
    require(full_name and len(full_name) >= 2, "Please enter the person's full name.")
    phone = V.clean_text(data.get("phone"), 20)
    require(phone and V.is_valid_phone(phone), "Please enter a valid phone number.")
    require(User.query.filter(db.func.lower(User.email) == email).first() is None, "An account with this e-mail already exists.")

    password = data.get("password") or ""
    temporary = None
    if password:
        problems = V.password_problems(password)
        require(not problems, " ".join(problems))
    else:
        temporary = password = _temporary_password()
    must_change = bool(data.get("must_change_password")) or temporary is not None

    note = "Account created by an administrator."
    role_values = {}
    if role == C.ROLE_VOLUNTEER:
        skills = V.clean_text(data.get("skills"))
        require(skills, "Please list the volunteer's skills.")
        availability = V.clean_text(data.get("availability"), 200)
        require(availability, "Please enter when the volunteer is available.")
        role_values = {"skills": skills, "availability": availability}
    elif role == C.ROLE_RESCUER:
        area = V.clean_text(data.get("service_area"), 150)
        require(area, "Please enter the area the rescuer serves.")
        role_values = {"organization": V.clean_text(data.get("organization"), 150), "service_area": area,
                       "has_vehicle": bool(data.get("has_vehicle")), "verification_details": note}
    elif role == C.ROLE_VETERINARIAN:
        license_number = V.clean_text(data.get("license_number"), 60)
        require(license_number, "Please enter the veterinary licence / registration number.")
        qualification = V.clean_text(data.get("qualification"), 150)
        require(qualification, "Please enter the qualification.")
        role_values = {"license_number": license_number, "qualification": qualification,
                       "clinic_name": V.clean_text(data.get("clinic_name"), 150), "verification_details": note}
    elif role == C.ROLE_SHELTER:
        role_values = _shelter_values(data, user_phone=phone, user_email=email)
        role_values["registration_number"] = V.clean_text(data.get("registration_number"), 60)
        role_values["verification_details"] = note

    now = utcnow()
    needs_check = role in C.VERIFICATION_REQUIRED_ROLES
    try:
        with transaction():
            user = User(email=email, full_name=full_name, phone=phone, role=role, status=C.ACCOUNT_ACTIVE,
                        verification_status=C.VERIFY_VERIFIED if needs_check else C.VERIFY_NOT_REQUIRED,
                        must_change_password=must_change)
            if needs_check:
                user.verified_by, user.verified_at, user.verification_note = actor.id, now, note
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            db.session.add(UserProfile(user=user))
            if role == C.ROLE_VOLUNTEER:
                db.session.add(VolunteerProfile(user=user, application_status=C.APPLICATION_APPROVED, reviewed_by=actor.id,
                                                reviewed_at=now, review_note=note, **role_values))
            elif role == C.ROLE_RESCUER:
                db.session.add(RescuerProfile(user=user, **role_values))
            elif role == C.ROLE_VETERINARIAN:
                db.session.add(VeterinarianProfile(user=user, **role_values))
            elif role == C.ROLE_SHELTER:
                db.session.add(ShelterProfile(user=user, **role_values))
            notifications.notify(user, "Welcome to PawConnect", "An administrator created your PawConnect account. "
                                 "Sign in with the details you were given.", C.NOTIFY_ACCOUNT, link_for("dashboard.index"))
            audit.log_action("user_created_by_admin", "User", user.id, f"{user.email} ({user.role})", user=actor)
    except IntegrityError:
        db.session.rollback()
        raise ServiceError("An account with this e-mail already exists.")
    return user, temporary


def set_account_status(user, status, actor, reason=None):
    """Activate, deactivate or suspend an account (administrators only)."""
    require(getattr(actor, "role", None) == C.ROLE_ADMIN, "Only an administrator can change account status.")
    require(status in C.ACCOUNT_STATUSES, "Invalid account status.")
    require(user.id != actor.id, "You cannot change the status of your own account.")
    if user.role == C.ROLE_ADMIN and status != C.ACCOUNT_ACTIVE:
        others = User.query.filter(User.role == C.ROLE_ADMIN, User.status == C.ACCOUNT_ACTIVE, User.id != user.id).count()
        require(others > 0, "At least one active administrator must remain.")
    with transaction():
        user.status = status
        if status == C.ACCOUNT_ACTIVE:
            user.failed_login_attempts = 0
            user.locked_until = None
        notifications.notify(user, "Account status changed", f"Your account is now {status}." + (f" Reason: {V.clean_text(reason)}" if reason else ""),
                             C.NOTIFY_ACCOUNT, link_for("account.profile"))
        audit.log_action("account_status_changed", "User", user.id, f"{user.email} -> {status}", user=actor)
    return user


def verify_account(user, approve, actor, note=None):
    """Approve / reject a rescuer, veterinarian or shelter account."""
    require(getattr(actor, "role", None) == C.ROLE_ADMIN, "Only an administrator can verify accounts.")
    require(user.needs_verification, "This account type does not need verification.")
    if not approve:
        require(V.clean_text(note), "Please give a reason for rejecting the verification.")
    with transaction():
        user.verification_status = C.VERIFY_VERIFIED if approve else C.VERIFY_REJECTED
        user.verification_note = V.clean_text(note)
        user.verified_by = actor.id
        user.verified_at = utcnow()
        notifications.notify(
            user, "Account verification completed" if approve else "Account verification update",
            ("Your account has been verified. You now have full access." if approve
             else f"Your verification was not approved. Reason: {user.verification_note}"),
            C.NOTIFY_ACCOUNT, link_for("dashboard.index"))
        audit.log_action("account_verified" if approve else "account_verification_rejected", "User", user.id, user.email, user=actor)
    return user
