"""Small factories and helpers for the integration tests.

Each factory opens its own application context and returns plain ids, so a test never keeps a database session open
while it uses the test client, and objects are always loaded fresh inside the ``with`` block that uses them.

Import this module only after the test module has skipped itself when the web packages are missing.
"""
import itertools

from flask import url_for

from app import constants as C
from app.extensions import db
from app.models import (
    Animal, RescuerProfile, ShelterAdmission, ShelterProfile, User, UserProfile, VeterinarianProfile, VolunteerProfile,
)
from app.services import adoption_service, rescue_service
from app.utils.timeutil import utcnow

PASSWORD = "Test@12345"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64  # the smallest thing the upload check accepts as a PNG picture
_numbers = itertools.count(1)


# ------------------------------------------------------------------ general helpers
def url(app, endpoint, **values):
    """The address of ``endpoint`` (so the tests do not repeat paths)."""
    with app.test_request_context():
        return url_for(endpoint, **values)


def form_values(data):
    """Python values -> what a browser sends: unchecked boxes are simply absent, checked ones are ``y``."""
    sent = {}
    for key, value in data.items():
        if value is None or value is False:
            continue
        sent[key] = "y" if value is True else str(value)
    return sent


def count(app, model, **filters):
    """How many rows of ``model`` match ``filters``."""
    with app.app_context():
        return model.query.filter_by(**filters).count()


def field(app, model, object_id, name):
    """One attribute of one row, read in its own short context."""
    with app.app_context():
        return getattr(db.session.get(model, object_id), name)


# ------------------------------------------------------------------ people
def create_user(app, role=C.ROLE_ADOPTER, email=None, *, verified=True, approved=True, status=C.ACCOUNT_ACTIVE,
                full_name=None, password=PASSWORD, capacity=5, must_change_password=False):
    """Create an account (with the role's profile) and return its id.

    ``verified`` applies to rescuers, veterinarians and shelters; ``approved`` to volunteers.
    """
    number = next(_numbers)
    email = email or f"{role}{number}@pawconnect.test"
    if role in C.VERIFICATION_REQUIRED_ROLES:
        verification = C.VERIFY_VERIFIED if verified else C.VERIFY_PENDING
    else:
        verification = C.VERIFY_NOT_REQUIRED
    with app.app_context():
        user = User(
            email=email, full_name=full_name or f"Test {role.title()} {number}", phone="9876543210", role=role,
            status=status, verification_status=verification, must_change_password=must_change_password,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        db.session.add(UserProfile(user_id=user.id, city="Testville"))
        if role == C.ROLE_VOLUNTEER:
            db.session.add(VolunteerProfile(
                user_id=user.id, skills="Dog walking", availability="Weekends",
                application_status=C.APPLICATION_APPROVED if approved else C.APPLICATION_PENDING))
        elif role == C.ROLE_RESCUER:
            db.session.add(RescuerProfile(user_id=user.id, service_area="Testville"))
        elif role == C.ROLE_VETERINARIAN:
            db.session.add(VeterinarianProfile(user_id=user.id, license_number=f"VET-{number}", qualification="BVSc"))
        elif role == C.ROLE_SHELTER:
            db.session.add(ShelterProfile(
                user_id=user.id, shelter_name=f"Test Shelter {number}", address="1 Test Road", city="Testville",
                capacity=capacity))
        db.session.commit()
        return user.id


def user_id_for(app, email):
    """The id of the account with this e-mail address, or ``None``."""
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        return user.id if user else None


def sign_in(client, email, password=PASSWORD):
    """Sign in through the real login form."""
    response = client.post("/login", data={"email": email, "password": password})
    assert response.status_code == 302, f"Sign-in failed for {email}: {response.get_data(as_text=True)[:300]}"
    return response


def login_as(app, client, role, **options):
    """Create an account of ``role``, sign in as it, and return its id."""
    email = options.pop("email", None) or f"{role}{next(_numbers)}@pawconnect.test"
    password = options.get("password", PASSWORD)
    user_id = create_user(app, role, email, **options)
    sign_in(client, email, password)
    return user_id


# ------------------------------------------------------------------ rescue reports
def report_data(**overrides):
    """Valid values for the rescue report form / service."""
    data = {
        "reporter_name": "Meena Rao", "reporter_phone": "98765 01234", "reporter_email": "",
        "animal_type": "Dog", "animal_count": 1,
        "animal_description": "A brown dog with an injured back leg near the bus stop.",
        "approximate_age": "", "animal_condition": "Injured", "emergency_level": "High",
        "location_name": "Gandhi Chowk", "address": "Opposite the bus stop, Gandhi Chowk, Testville",
        "latitude": "12.9716", "longitude": "77.5946", "additional_info": "",
    }
    data.update(overrides)
    return data


def create_report(app, reporter_id=None, **overrides):
    """Save a report through the service. Returns ``(id, report code)``."""
    with app.app_context():
        reporter = db.session.get(User, reporter_id) if reporter_id else None
        report = rescue_service.create_report(report_data(**overrides), reporter=reporter)
        return report.id, report.report_code


# ------------------------------------------------------------------ animals and adoption
def create_animal(app, *, shelter_user_id=None, status=C.ANIMAL_AVAILABLE, name="Buddy", animal_type="Dog"):
    """Register an animal (optionally housed in the shelter of ``shelter_user_id``) and return its id."""
    number = next(_numbers)
    with app.app_context():
        shelter = ShelterProfile.query.filter_by(user_id=shelter_user_id).first() if shelter_user_id else None
        animal = Animal(
            animal_code=f"ANM-TEST-{number:05d}", name=name, animal_type=animal_type, age_months=18, gender="Male",
            status=status, medical_status=C.MEDICAL_HEALTHY, shelter_id=shelter.id if shelter else None,
            available_since=utcnow() if status == C.ANIMAL_AVAILABLE else None,
        )
        db.session.add(animal)
        db.session.flush()
        if shelter is not None:
            db.session.add(ShelterAdmission(shelter_id=shelter.id, animal_id=animal.id))
        db.session.commit()
        return animal.id


def adoption_data(**overrides):
    """Valid values for an adoption application."""
    data = {
        "applicant_name": "Arjun Mehta", "applicant_email": "arjun@pawconnect.test", "applicant_phone": "9876512345",
        "address": "12 Garden Street", "city": "Testville", "state": "Karnataka", "pincode": "560001",
        "occupation": "Engineer", "housing_type": C.HOUSING_TYPES[0], "household_members": 3, "has_other_pets": False,
        "previous_experience": "Grew up with dogs.",
        "adoption_reason": "I have a fenced garden and plenty of time to care for a dog.",
        "agreed_to_terms": True,
    }
    data.update(overrides)
    return data


def create_application(app, animal_id, adopter_id, **overrides):
    """Submit an adoption application through the service and return its id."""
    with app.app_context():
        animal = db.session.get(Animal, animal_id)
        adopter = db.session.get(User, adopter_id)
        return adoption_service.submit_application(animal, adopter, adoption_data(**overrides)).id
