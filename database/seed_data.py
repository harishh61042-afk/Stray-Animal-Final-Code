"""Sample accounts and demo data - FOR DEVELOPMENT AND DEMONSTRATIONS ONLY.

Everything in this file is invented: the people, shelters, animals, reports and phone numbers do not exist.
It is loaded only when you ask for it:

    python init_db.py --seed

Never load it into a database that holds real data, and never use these accounts on a public server:
every sample account shares the well-known password ``SAMPLE_PASSWORD`` below.
"""
import uuid
from datetime import timedelta

from flask import current_app

from app import constants as C
from app.extensions import db
from app.models import (
    AdoptionApplication, AdoptionRecord, Animal, AnimalReport, AnimalStatusHistory, ContactMessage, MedicalRecord,
    RescueActivity, RescueAssignment, RescuerProfile, ShelterAdmission, ShelterProfile, User, Vaccination,
    VeterinarianProfile, VolunteerProfile, VolunteerTask, VolunteerTaskAssignment,
)
from app.services import audit, notifications, rules
from app.services.common import link_for
from app.utils import validators as V
from app.utils.timeutil import local_today, utcnow

# DEVELOPMENT ONLY - every sample account uses this password.
SAMPLE_PASSWORD = "Paw@12345"

# (key, role, e-mail, name, phone). ".test" e-mail addresses can never belong to a real person.
ACCOUNTS = [
    ("rescuer1", C.ROLE_RESCUER, "rescuer@pawconnect.test", "Ravi Kumar", "+91 90000 10001"),
    ("rescuer2", C.ROLE_RESCUER, "rescuer2@pawconnect.test", "Sana Sheikh", "+91 90000 10002"),
    ("rescuer_new", C.ROLE_RESCUER, "newrescuer@pawconnect.test", "Kiran Patel", "+91 90000 10003"),  # waits for verification
    ("volunteer1", C.ROLE_VOLUNTEER, "volunteer@pawconnect.test", "Anita Desai", "+91 90000 20001"),
    ("volunteer2", C.ROLE_VOLUNTEER, "volunteer2@pawconnect.test", "Mohan Das", "+91 90000 20002"),
    ("volunteer_new", C.ROLE_VOLUNTEER, "newvolunteer@pawconnect.test", "Divya Rao", "+91 90000 20003"),  # waits for approval
    ("vet", C.ROLE_VETERINARIAN, "vet@pawconnect.test", "Dr. Meera Nair", "+91 90000 30001"),
    ("shelter1", C.ROLE_SHELTER, "shelter@pawconnect.test", "Happy Tails Shelter", "+91 90000 40001"),
    ("shelter2", C.ROLE_SHELTER, "shelter2@pawconnect.test", "Green Paws Sanctuary", "+91 90000 40002"),
    ("adopter1", C.ROLE_ADOPTER, "adopter@pawconnect.test", "Arjun Mehta", "+91 90000 50001"),
    ("adopter2", C.ROLE_ADOPTER, "adopter2@pawconnect.test", "Priya Sharma", "+91 90000 50002"),
]
FIRST_SAMPLE_EMAIL = ACCOUNTS[0][2]


# ---------------------------------------------------------------- small helpers
def _ago(days=0, hours=0):
    return utcnow() - timedelta(days=days, hours=hours)


def _day(days):
    """A calendar date ``days`` ago (negative numbers are in the future)."""
    return local_today() - timedelta(days=days)


def _save(record):
    db.session.add(record)
    db.session.flush()
    return record


def _save_coded(record, field, prefix):
    """Insert with a throw-away unique code, then replace it with the readable ``PREFIX-YEAR-00042`` code."""
    setattr(record, field, "TMP-" + uuid.uuid4().hex[:20])
    _save(record)
    setattr(record, field, V.format_code(prefix, local_today().year, record.id))
    return record


def _log(action, entity_type, entity, description, actor, days=0):
    entry = audit.log_action(action, entity_type, getattr(entity, "id", None), description, user=actor)
    entry.created_at = _ago(days=days)
    return entry


def _notice(user, title, message, category, link, days=0, read=False):
    note = notifications.notify(user, title, message, category, link)
    note.created_at = _ago(days=days)
    if read:
        note.is_read, note.read_at = True, note.created_at + timedelta(hours=3)
    return note


# ------------------------------------------------------------------- the data
def _people(admin):
    probe = User()
    probe.set_password(SAMPLE_PASSWORD)  # hash once; every sample account shares it
    people = {"admin": admin}
    for index, (key, role, email, name, phone) in enumerate(ACCOUNTS):
        created = _ago(days=75 - 4 * index)
        user = User(email=email, full_name=name, phone=phone, role=role, status=C.ACCOUNT_ACTIVE,
                    must_change_password=False, password_hash=probe.password_hash, created_at=created)
        if role in C.VERIFICATION_REQUIRED_ROLES:
            if key.endswith("_new"):
                user.verification_status = C.VERIFY_PENDING
            else:
                user.verification_status = C.VERIFY_VERIFIED
                user.verified_by, user.verified_at = admin.id, created + timedelta(days=1)
        people[key] = _save(user)
        _log("user_registered", "User", user, email, user, days=75 - 4 * index)

    def uid(key):
        return people[key].id

    _save(RescuerProfile(user_id=uid("rescuer1"), organization="City Animal Aid", experience_years=6,
                         service_area="Banjara Hills, Tolichowki, Jubilee Hills", has_vehicle=True,
                         verification_details="Sample account created for demonstration."))
    _save(RescuerProfile(user_id=uid("rescuer2"), organization="Independent rescuer", experience_years=3,
                         service_area="Madhapur, Kondapur, Gachibowli", has_vehicle=False,
                         verification_details="Sample account created for demonstration."))
    _save(RescuerProfile(user_id=uid("rescuer_new"), organization="Street Friends Group", experience_years=1,
                         service_area="Secunderabad", has_vehicle=False,
                         verification_details="Sample account waiting for the administrator's decision."))
    _save(VeterinarianProfile(user_id=uid("vet"), clinic_name="Sample Care Animal Clinic", license_number="SAMPLE-VET-0001",
                              specialization="Small animals", qualification="BVSc & AH", experience_years=8,
                              clinic_address="12 Example Road, Banjara Hills, Hyderabad", consultation_hours="Mon-Sat, 10 am - 6 pm",
                              verification_details="Sample account created for demonstration."))
    _save(ShelterProfile(user_id=uid("shelter1"), shelter_name="Happy Tails Shelter", registration_number="SAMPLE-SH-001",
                         address="Plot 12, Example Lane, Banjara Hills", city="Hyderabad", state="Telangana", pincode="500034",
                         latitude=17.4126, longitude=78.4482, contact_phone="+91 90000 40001",
                         contact_email="shelter@pawconnect.test", capacity=15,
                         description="A sample shelter that gives rescued dogs and cats a safe place to recover.",
                         verification_details="Sample account created for demonstration."))
    _save(ShelterProfile(user_id=uid("shelter2"), shelter_name="Green Paws Sanctuary", registration_number="SAMPLE-SH-002",
                         address="Survey 45, Sample Road, Madhapur", city="Hyderabad", state="Telangana", pincode="500081",
                         latitude=17.4435, longitude=78.3772, contact_phone="+91 90000 40002",
                         contact_email="shelter2@pawconnect.test", capacity=8,
                         description="A small sample sanctuary with a garden for dogs waiting to be adopted.",
                         verification_details="Sample account created for demonstration."))
    for key, skills, availability, status in (
        ("volunteer1", "Dog handling, first aid, driving", "Weekends and weekday evenings", C.APPLICATION_APPROVED),
        ("volunteer2", "Feeding rounds, cleaning, social media", "Saturdays", C.APPLICATION_APPROVED),
        ("volunteer_new", "Photography, event help", "Sundays", C.APPLICATION_PENDING),
    ):
        approved = status == C.APPLICATION_APPROVED
        _save(VolunteerProfile(
            user_id=uid(key), skills=skills, experience="Sample volunteer profile created for demonstration.",
            availability=availability, motivation="Wants to help animals in the neighbourhood.",
            emergency_contact_name="Sample Contact", emergency_contact_phone="+91 90000 99999",
            application_status=status, applied_at=people[key].created_at,
            reviewed_by=admin.id if approved else None,
            reviewed_at=people[key].created_at + timedelta(days=1) if approved else None))
    shelters = {"shelter1": people["shelter1"].shelter_profile, "shelter2": people["shelter2"].shelter_profile}
    return people, shelters


# key, days ago, reporter key (None = a visitor without an account), visitor name, animal type, condition, emergency
# level, animals, description, place, address, (latitude, longitude), final status
REPORTS = [
    ("critical", 1, None, "Neha Verma", "Dog", "Hit by vehicle", C.EMERGENCY_CRITICAL, 1,
     "Brown dog lying at the roadside after being hit by a vehicle. It is breathing but cannot stand.",
     "Tolichowki Main Road", "Near the bus stop, Tolichowki, Hyderabad", (17.4031, 78.4140), C.REPORT_PENDING),
    ("kittens", 2, "adopter1", None, "Cat", "Newborn / Orphaned", C.EMERGENCY_MEDIUM, 4,
     "A mother cat and three kittens under a parked car. Nobody seems to be feeding them.",
     "Jubilee Hills Road No. 36", "Behind the corner tea stall, Jubilee Hills, Hyderabad", (17.4325, 78.4071), C.REPORT_PENDING),
    ("assigned", 3, None, "Rahul Singh", "Dog", "Injured", C.EMERGENCY_HIGH, 1,
     "Black dog with a deep cut on its front leg near the market entrance.",
     "Kukatpally Housing Board", "Market entrance, KPHB Colony, Hyderabad", (17.4948, 78.3996), C.REPORT_ASSIGNED),
    ("progress", 4, "adopter2", None, "Cow", "Trapped / Stuck", C.EMERGENCY_HIGH, 1,
     "A calf has slipped into a drain beside the road and cannot climb out.",
     "Madhapur Cyber Towers road", "Drain beside the service road, Madhapur, Hyderabad", (17.4504, 78.3808), C.REPORT_IN_PROGRESS),
    ("rescued", 40, None, "Sunita Reddy", "Dog", "Injured", C.EMERGENCY_HIGH, 1,
     "Medium-sized dog dragging its back leg behind a petrol pump.",
     "Banjara Hills Road No. 12", "Behind the petrol pump, Banjara Hills, Hyderabad", (17.4156, 78.4347), C.REPORT_RESCUED),
    ("closed", 62, None, "Imran Khan", "Dog", "Hungry / Malnourished", C.EMERGENCY_MEDIUM, 1,
     "Thin puppy wandering alone in the vegetable market in the evenings.",
     "Tolichowki vegetable market", "Main lane, Tolichowki, Hyderabad", (17.3989, 78.4136), C.REPORT_CLOSED),
    ("rejected", 20, None, "Vikram Joshi", "Dog", "Abandoned", C.EMERGENCY_LOW, 1,
     "Dog sitting outside a shop.",
     "Secunderabad Station Road", "Opposite the station gate, Secunderabad", (17.4337, 78.5014), C.REPORT_REJECTED),
]


def _reports(people):
    admin = people["admin"]
    rescuer1, rescuer2 = people["rescuer1"], people["rescuer2"]
    reports = {}
    for key, days, reporter, visitor, kind, condition, level, count, text, place, address, (lat, lng), status in REPORTS:
        owner = people.get(reporter)
        report = _save_coded(AnimalReport(
            reporter_id=owner.id if owner else None, reporter_name=owner.full_name if owner else visitor,
            reporter_phone=owner.phone if owner else "+91 90000 60001", reporter_email=owner.email if owner else None,
            animal_type=kind, animal_description=text, animal_condition=condition, emergency_level=level,
            animal_count=count, location_name=place, address=address, latitude=lat, longitude=lng, status=status,
            created_at=_ago(days=days), rejection_reason=("Duplicate of an earlier report, so no new rescue is needed."
                                                          if status == C.REPORT_REJECTED else None),
            closed_at=_ago(days=days - 3) if status in (C.REPORT_CLOSED, C.REPORT_REJECTED) else None),
            "report_code", "RPT")
        reports[key] = report

        def step(kind_, note, old, new, hours, actor=None, _report=report, _days=days):
            _save(RescueActivity(report_id=_report.id, actor_id=getattr(actor, "id", None), activity_type=kind_,
                                 old_status=old, new_status=new, note=note, created_at=_ago(days=_days) + timedelta(hours=hours)))

        step("report_submitted", "Report submitted", None, C.REPORT_PENDING, 0, owner)
        _log("report_submitted", "AnimalReport", report, f"{report.report_code} - {place}", owner, days=days)

        def assign(rescuer, assignment_status, hours, completed=False, _report=report, _days=days):
            return _save(RescueAssignment(
                report_id=_report.id, rescuer_id=rescuer.id, assigned_by=admin.id, status=assignment_status,
                deadline=_ago(days=_days) + timedelta(hours=hours + 24),
                instructions="Please call the reporter on arrival and take a carrier.",
                assigned_at=_ago(days=_days) + timedelta(hours=hours),
                responded_at=(_ago(days=_days) + timedelta(hours=hours + 1)
                              if assignment_status != C.ASSIGNMENT_ASSIGNED else None),
                completed_at=(_ago(days=_days) + timedelta(hours=hours + 6) if completed else None),
                completion_details="Animal brought to the shelter and registered." if completed else None))

        if key == "assigned":
            assign(rescuer1, C.ASSIGNMENT_ASSIGNED, 2)
            step("assigned", f"Assigned to {rescuer1.full_name}", C.REPORT_PENDING, C.REPORT_ASSIGNED, 2, admin)
            _log("rescuer_assigned", "AnimalReport", report, f"{report.report_code} -> {rescuer1.full_name}", admin, days=days)
        elif key == "progress":
            assign(rescuer2, C.ASSIGNMENT_ACCEPTED, 2)
            step("assigned", f"Assigned to {rescuer2.full_name}", C.REPORT_PENDING, C.REPORT_ASSIGNED, 2, admin)
            step("accepted", f"{rescuer2.full_name} is on the way", C.REPORT_ASSIGNED, C.REPORT_IN_PROGRESS, 3, rescuer2)
            _log("rescuer_assigned", "AnimalReport", report, f"{report.report_code} -> {rescuer2.full_name}", admin, days=days)
            _log("assignment_accepted", "AnimalReport", report, report.report_code, rescuer2, days=days)
        elif key in ("rescued", "closed"):
            rescuer = rescuer1 if key == "rescued" else rescuer2
            assign(rescuer, C.ASSIGNMENT_COMPLETED, 2, completed=True)
            step("assigned", f"Assigned to {rescuer.full_name}", C.REPORT_PENDING, C.REPORT_ASSIGNED, 2, admin)
            step("accepted", f"{rescuer.full_name} is on the way", C.REPORT_ASSIGNED, C.REPORT_IN_PROGRESS, 3, rescuer)
            step("completed", "Rescue completed", C.REPORT_IN_PROGRESS, C.REPORT_RESCUED, 8, rescuer)
            _log("rescuer_assigned", "AnimalReport", report, f"{report.report_code} -> {rescuer.full_name}", admin, days=days)
            _log("rescue_completed", "AnimalReport", report, report.report_code, rescuer, days=days)
            if key == "closed":
                step("status_changed", "Animal is settled in the shelter", C.REPORT_RESCUED, C.REPORT_CLOSED, 72, admin)
        elif key == "rejected":
            step("status_changed", report.rejection_reason, C.REPORT_PENDING, C.REPORT_REJECTED, 5, admin)
    return reports


# key, name, type, breed, age (months), gender, colour, description, temperament, shelter, rescuer, report, rescued
# days ago, rescue place, (lat, lng), status path [(status, days ago)], medical status, vaccination status,
# rehabilitation status, vet looks after it
ANIMALS = [
    ("bruno", "Bruno", "Dog", "Indian Pariah", 14, "Male", "Brown",
     "Friendly young dog who loves walks and plays gently with children.", "Friendly, playful, good with children",
     "shelter1", "rescuer2", "closed", 62, "Tolichowki vegetable market", (17.3989, 78.4136),
     [(C.ANIMAL_RESCUED, 62), (C.ANIMAL_IN_SHELTER, 61), (C.ANIMAL_AVAILABLE, 40)],
     C.MEDICAL_HEALTHY, C.VACC_FULL, "Completed", True),
    ("mimi", "Mimi", "Cat", "Domestic Shorthair", 8, "Female", "Grey",
     "Calm grey cat who enjoys sunny windows and being brushed.", "Calm, affectionate",
     "shelter1", "rescuer1", None, 45, "Jubilee Hills", (17.4325, 78.4071),
     [(C.ANIMAL_RESCUED, 45), (C.ANIMAL_IN_SHELTER, 44), (C.ANIMAL_AVAILABLE, 30)],
     C.MEDICAL_HEALTHY, C.VACC_FULL, "Completed", True),
    ("rocky", "Rocky", "Dog", "Labrador mix", 30, "Male", "Golden",
     "Strong, loyal dog who already knows how to sit and shake hands.", "Loyal, energetic, needs daily exercise",
     "shelter2", "rescuer2", None, 55, "Gachibowli", (17.4401, 78.3489),
     [(C.ANIMAL_RESCUED, 55), (C.ANIMAL_IN_SHELTER, 54), (C.ANIMAL_AVAILABLE, 35)],
     C.MEDICAL_HEALTHY, C.VACC_DUE, "Completed", True),
    ("luna", "Luna", "Dog", "Indian Pariah", 5, "Female", "Black and white",
     "Curious puppy who follows everyone around the garden.", "Curious, gentle",
     "shelter2", "rescuer1", None, 30, "Kondapur", (17.4600, 78.3636),
     [(C.ANIMAL_RESCUED, 30), (C.ANIMAL_IN_SHELTER, 29), (C.ANIMAL_AVAILABLE, 12)],
     C.MEDICAL_HEALTHY, C.VACC_PARTIAL, "Completed", True),
    ("coco", "Coco", "Cat", "Domestic Longhair", 3, "Female", "Cream",
     "Small kitten recovering from a chest infection.", "Shy at first, loves warmth",
     "shelter1", "rescuer1", None, 18, "Kukatpally", (17.4849, 78.4138),
     [(C.ANIMAL_RESCUED, 18), (C.ANIMAL_IN_SHELTER, 17), (C.ANIMAL_RECOVERING, 10)],
     C.MEDICAL_RECOVERING, C.VACC_PARTIAL, "In Progress", True),
    ("sheru", "Sheru", "Dog", "Mixed breed", 48, "Male", "Black",
     "Gentle adult dog healing from a leg fracture. Not yet ready for adoption.", "Gentle, patient",
     "shelter1", "rescuer1", "rescued", 40, "Banjara Hills Road No. 12", (17.4156, 78.4347),
     [(C.ANIMAL_RESCUED, 40), (C.ANIMAL_TREATMENT, 40), (C.ANIMAL_IN_SHELTER, 38), (C.ANIMAL_TREATMENT, 30)],
     C.MEDICAL_TREATMENT, C.VACC_NONE, "Not Started", True),
    ("gopi", "Gopi", "Cow", "Local breed", 24, "Male", "White",
     "Young bull found wandering on a highway, waiting for a place at a farm sanctuary.", "Calm",
     None, "rescuer2", None, 6, "Outer Ring Road", (17.4239, 78.3425),
     [(C.ANIMAL_RESCUED, 6)],
     C.MEDICAL_OBSERVATION, C.VACC_NONE, "Not Started", False),
    ("tara", "Tara", "Dog", "Indian Pariah", 36, "Female", "Fawn",
     "Loving dog who found her family through PawConnect.", "Loving, loyal",
     "shelter2", "rescuer1", None, 80, "Hitech City", (17.4435, 78.3772),
     [(C.ANIMAL_RESCUED, 80), (C.ANIMAL_IN_SHELTER, 79), (C.ANIMAL_AVAILABLE, 60), (C.ANIMAL_ADOPTED, 10)],
     C.MEDICAL_HEALTHY, C.VACC_FULL, "Completed", True),
]


def _animals(people, shelters, reports):
    animals = {}
    vet = people["vet"]
    for (key, name, kind, breed, age, gender, colour, text, temperament, shelter_key, rescuer_key, report_key,
         rescued_days, place, (lat, lng), path, medical, vaccination, rehab, has_vet) in ANIMALS:
        assert path[-1][0] in C.ANIMAL_STATUSES, key
        shelter = shelters.get(shelter_key)
        rescuer = people[rescuer_key]
        available = next((days for status, days in path if status == C.ANIMAL_AVAILABLE), None)
        animal = _save_coded(Animal(
            name=name, animal_type=kind, breed=breed, age_months=age, gender=gender, color=colour, description=text,
            temperament=temperament, rescue_date=_day(rescued_days), rescue_location=place + ", Hyderabad",
            latitude=lat, longitude=lng, report_id=reports[report_key].id if report_key else None,
            shelter_id=shelter.id if shelter else None, veterinarian_id=vet.id if has_vet else None,
            rescuer_id=rescuer.id, registered_by=(people[shelter_key].id if shelter_key else rescuer.id),
            health_condition="See the medical records for details.", vaccination_status=vaccination,
            medical_status=medical, rehabilitation_status=rehab, status=path[-1][0],
            available_since=_ago(days=available) if available is not None and path[-1][0] == C.ANIMAL_AVAILABLE else None,
            created_at=_ago(days=rescued_days)), "animal_code", "ANM")
        animals[key] = animal
        _log("animal_registered", "Animal", animal, f"{animal.animal_code} - {name}", rescuer, days=rescued_days)

        previous = None
        for status, days in path:
            _save(AnimalStatusHistory(animal_id=animal.id, old_status=previous, new_status=status,
                                      changed_by=rescuer.id, changed_at=_ago(days=days),
                                      note="Registered by the rescue team." if previous is None else None))
            previous = status

        if shelter is not None:
            admitted = next((days for status, days in path if status == C.ANIMAL_IN_SHELTER), rescued_days)
            adopted = next((days for status, days in path if status == C.ANIMAL_ADOPTED), None)
            _save(ShelterAdmission(shelter_id=shelter.id, animal_id=animal.id, admitted_by=people[shelter_key].id,
                                   admitted_at=_ago(days=admitted),
                                   discharged_at=_ago(days=adopted) if adopted is not None else None,
                                   discharge_reason="Adopted" if adopted is not None else None,
                                   note="Admitted after the rescue."))
            _log("animal_admitted", "Animal", animal, f"{animal.animal_code} -> {shelter.shelter_name}",
                 people[shelter_key], days=admitted)
    return animals


# animal, days ago, diagnosis, symptoms, treatment, medicines, medical status, follow-up in days, weight (kg)
MEDICAL = [
    ("sheru", 38, "Fractured left hind leg", "Limping, swelling and pain", "Leg splinted; strict rest in a quiet kennel",
     "Pain relief and antibiotics as prescribed", C.MEDICAL_TREATMENT, None, 18.5),
    ("sheru", 4, "Fracture healing as expected", "Bearing a little weight on the leg", "Splint changed; short supervised walks",
     "Pain relief until the next check", C.MEDICAL_TREATMENT, 6, 19.0),
    ("coco", 16, "Upper respiratory infection", "Sneezing and watery eyes", "Warm resting place and eye cleaning",
     "Antibiotic drops as prescribed", C.MEDICAL_TREATMENT, None, 0.9),
    ("coco", 5, "Recovering well", "Eating normally, eyes clear", "Continue warm resting place", None,
     C.MEDICAL_RECOVERING, 3, 1.1),
    ("bruno", 58, "General health check", "Thin but alert", "Deworming and a balanced feeding plan", "Deworming tablets",
     C.MEDICAL_HEALTHY, None, 14.2),
    ("mimi", 40, "General health check", "None", "Flea treatment", "Flea control", C.MEDICAL_HEALTHY, None, 2.8),
    ("gopi", 5, "Minor skin abrasions", "Scratches on the legs", "Wounds cleaned and treated", "Antiseptic ointment",
     C.MEDICAL_OBSERVATION, 2, None),
]

# animal, vaccine, given days ago, next due in days (negative = overdue)
VACCINATIONS = [
    ("bruno", "Rabies", 50, 315), ("bruno", "DHPP (Distemper, Hepatitis, Parvo, Parainfluenza)", 50, 315),
    ("mimi", "FVRCP (Feline)", 40, 325), ("rocky", "DHPP (Distemper, Hepatitis, Parvo, Parainfluenza)", 355, 10),
    ("luna", "DHPP (Distemper, Hepatitis, Parvo, Parainfluenza)", 20, 8), ("coco", "FVRCP (Feline)", 28, -2),
    ("tara", "Rabies", 100, 265),
]


def _medical(people, animals):
    vet = people["vet"]
    first_record = {}
    for key, days, diagnosis, symptoms, treatment, medicines, status, follow_up, weight in MEDICAL:
        animal = animals[key]
        record = _save(MedicalRecord(
            animal_id=animal.id, veterinarian_id=vet.id, created_by=vet.id, examination_date=_day(days),
            weight_kg=weight, symptoms=symptoms, diagnosis=diagnosis, treatment=treatment, medicines=medicines,
            medical_status=status, follow_up_date=_day(-follow_up) if follow_up is not None else None,
            notes="Sample record created for demonstration.", created_at=_ago(days=days)))
        first_record.setdefault(key, record)
        _log("medical_record_added", "MedicalRecord", record, f"{animal.animal_code} - {diagnosis}", vet, days=days)
    for key, vaccine, given, due in VACCINATIONS:
        animal = animals[key]
        _save(Vaccination(
            animal_id=animal.id, medical_record_id=first_record[key].id if key in first_record else None,
            vaccine_name=vaccine, vaccination_date=_day(given), next_due_date=_day(-due), administered_by=vet.id,
            notes="Sample record created for demonstration.", created_at=_ago(days=given)))
        _log("vaccination_added", "Animal", animal, f"{animal.animal_code} - {vaccine}", vet, days=given)
    return first_record


def _tasks(people, animals, shelters, reports):
    admin = people["admin"]
    here = shelters["shelter1"]
    specs = [
        # key, title, type, days ago, due in days, place, address, (lat, lng), volunteers needed, report, animal,
        # shelter, [(volunteer key, assignment status, progress %, hours, completed days ago)], description
        ("feeding", "Weekend feeding drive", "Animal Food Distribution", 3, 6, "Banjara Hills Road No. 12",
         "Behind the petrol pump, Banjara Hills, Hyderabad", (17.4156, 78.4347), 3, None, None, None, [],
         "Hand out food and fresh water at the usual street feeding points."),
        ("kennels", "Clean the kennels at Happy Tails", "Shelter Cleaning", 8, 2, here.shelter_name, here.address,
         (here.latitude, here.longitude), 2, None, None, "shelter1", [("volunteer1", C.TA_IN_PROGRESS, 40, None, None)],
         "Wash and disinfect the kennels and refill the water bowls."),
        ("transport", "Take Mimi to the clinic for her check-up", "Transportation Support", 40, -38, here.shelter_name,
         here.address, (here.latitude, here.longitude), 1, None, "mimi", "shelter1",
         [("volunteer2", C.TA_COMPLETED, 100, 2.5, 38)], "Drive Mimi to the clinic and bring her back."),
        ("event", "Help at the Sunday adoption event", "Adoption Event Assistance", 2, 5, "Green Paws Sanctuary",
         shelters["shelter2"].address, (shelters["shelter2"].latitude, shelters["shelter2"].longitude), 1, None, None,
         "shelter2", [("volunteer1", C.TA_ASSIGNED, 0, None, None)],
         "Welcome visitors, walk the dogs and answer questions about adoption."),
    ]
    tasks = {}
    for key, title, kind, days, due, place, address, (lat, lng), needed, report, animal, shelter, team, text in specs:
        statuses = [status for _v, status, _p, _h, _c in team]
        task = _save(VolunteerTask(
            title=title, description=text, task_type=kind, location_name=place, address=address, latitude=lat,
            longitude=lng, instructions="Wear closed shoes and bring a water bottle.", due_at=_ago(days=-due),
            volunteers_needed=needed, report_id=reports[report].id if report else None,
            animal_id=animals[animal].id if animal else None, shelter_id=shelters[shelter].id if shelter else None,
            created_by=admin.id, status=rules.compute_task_status(C.TASK_AVAILABLE, statuses, needed),
            created_at=_ago(days=days)))
        tasks[key] = task
        _log("task_created", "VolunteerTask", task, title, admin, days=days)
        for volunteer_key, status, progress, hours, completed in team:
            volunteer = people[volunteer_key]
            _save(VolunteerTaskAssignment(
                task_id=task.id, volunteer_id=volunteer.id, assigned_by=admin.id, status=status,
                progress_percent=progress, progress_note="Started cleaning the first row of kennels."
                if status == C.TA_IN_PROGRESS else None,
                assigned_at=_ago(days=days), responded_at=None if status == C.TA_ASSIGNED else _ago(days=days),
                started_at=None if status == C.TA_ASSIGNED else _ago(days=days),
                completed_at=_ago(days=completed) if completed is not None else None, hours_spent=hours,
                completion_notes="Mimi was calm in the car and the check-up went well." if completed is not None else None))
            _log("task_assigned", "VolunteerTask", task, f"{title} -> {volunteer.full_name}", admin, days=days)
            if completed is not None:
                _log("task_completed", "VolunteerTask", task, title, volunteer, days=completed)
        if rules.compute_task_status(C.TASK_AVAILABLE, statuses, needed) == C.TASK_COMPLETED:
            task.completed_at = _ago(days=team[0][4])
    return tasks


def _application(adopter, animal, status, days, reason, housing, members, pets, comment=None, reviewer=None):
    return _save_coded(AdoptionApplication(
        animal_id=animal.id, adopter_id=adopter.id, applicant_name=adopter.full_name, applicant_email=adopter.email,
        applicant_phone=adopter.phone, address="Flat 4B, Sample Residency, Example Nagar", city="Hyderabad",
        state="Telangana", pincode="500032", occupation="Software engineer", housing_type=housing,
        household_members=members, has_other_pets=pets, other_pets_details="One older cat" if pets else None,
        previous_experience="Grew up with pets at home.", adoption_reason=reason, agreed_to_terms=True,
        status=status, review_comment=comment, reviewed_by=reviewer.id if reviewer else None,
        reviewed_at=_ago(days=days - 1) if reviewer else None, created_at=_ago(days=days)),
        "application_code", "ADP")


def _adoptions(people, animals, shelters):
    one, two = people["adopter1"], people["adopter2"]
    shelter1, shelter2 = people["shelter1"], people["shelter2"]
    done = _application(two, animals["tara"], C.ADOPTION_COMPLETED, 25, "We have a garden and time for daily walks.",
                        "Own house", 3, False, "Home visit went well. Welcome to the family!", shelter2)
    _save(AdoptionRecord(application_id=done.id, animal_id=animals["tara"].id, adopter_id=two.id,
                         shelter_id=shelters["shelter2"].id, adoption_date=_day(10), completed_by=shelter2.id,
                         final_notes="Adoption completed. Tara went home with her new family."))
    _log("adoption_applied", "AdoptionApplication", done, done.application_code, two, days=25)
    _log("adoption_approved", "AdoptionApplication", done, done.application_code, shelter2, days=20)
    _log("adoption_completed", "AdoptionApplication", done, done.application_code, shelter2, days=10)

    pending = _application(one, animals["bruno"], C.ADOPTION_PENDING, 2, "I would like a friendly dog to join my family.",
                           "Apartment / Flat", 2, False)
    review = _application(one, animals["mimi"], C.ADOPTION_UNDER_REVIEW, 5, "A calm cat would be perfect company at home.",
                          "Apartment / Flat", 2, False, "We would like to call you for a short chat.", shelter1)
    declined = _application(two, animals["rocky"], C.ADOPTION_REJECTED, 15, "I want a big dog to go jogging with.",
                            "Rented house", 1, True, "Rocky needs a home with a garden. Please consider Luna instead.", shelter2)
    for application in (pending, review, declined):
        _log("adoption_applied", "AdoptionApplication", application, application.application_code, application.adopter,
             days=(utcnow() - application.created_at).days)
    _log("adoption_under_review", "AdoptionApplication", review, review.application_code, shelter1, days=4)
    _log("adoption_rejected", "AdoptionApplication", declined, declined.application_code, shelter2, days=14)
    return {"done": done, "pending": pending, "review": review, "declined": declined}


def _messages():
    for name, email, subject, text, status, days in (
        ("Meena Iyer", "meena@example.test", "Can I donate food?",
         "I run a small shop and would like to donate dry food every month. Who can I speak to?", C.CONTACT_NEW, 1),
        ("Farhan Ali", "farhan@example.test", "Volunteering on weekdays",
         "Is there any way to help with feeding rounds on weekday mornings?", C.CONTACT_RESOLVED, 12),
    ):
        _save(ContactMessage(name=name, email=email, subject=subject, message=text, status=status, created_at=_ago(days=days)))


def _notices(people, animals, reports, applications, tasks):
    admin = people["admin"]
    _notice(admin, "Rescuer waiting for verification", "Kiran Patel registered as a rescuer and waits for your decision.",
            C.NOTIFY_ACCOUNT, link_for("admin.verifications"), days=1)
    _notice(admin, "New critical rescue report", f"{reports['critical'].report_code} was reported near Tolichowki.",
            C.NOTIFY_RESCUE, link_for("reports.detail", report_id=reports["critical"].id), days=1)
    _notice(people["rescuer1"], "New rescue assignment", f"You were assigned {reports['assigned'].report_code}.",
            C.NOTIFY_RESCUE, link_for("reports.detail", report_id=reports["assigned"].id), days=3)
    _notice(people["rescuer2"], "Rescue in progress", f"Thank you for taking {reports['progress'].report_code}.",
            C.NOTIFY_RESCUE, link_for("reports.detail", report_id=reports["progress"].id), days=4, read=True)
    _notice(people["volunteer1"], "A task was assigned to you", "Please open the Sunday adoption event task and respond.",
            C.NOTIFY_TASK, link_for("tasks.detail", task_id=tasks["event"].id), days=2)
    _notice(people["vet"], "Follow-up due soon", "Sheru has a follow-up examination coming up.", C.NOTIFY_MEDICAL,
            link_for("animals.detail", animal_id=animals["sheru"].id), days=1)
    _notice(people["shelter1"], "New adoption application", f"{applications['pending'].application_code} was received for Bruno.",
            C.NOTIFY_ADOPTION, link_for("adoption.detail", application_id=applications["pending"].id), days=2)
    _notice(people["adopter1"], "Your application is being reviewed", "Happy Tails Shelter started reviewing your application for Mimi.",
            C.NOTIFY_ADOPTION, link_for("adoption.detail", application_id=applications["review"].id), days=4)
    _notice(people["adopter2"], "Congratulations on adopting Tara!", "Your adoption was completed. We wish you many happy years together.",
            C.NOTIFY_ADOPTION, link_for("adoption.detail", application_id=applications["done"].id), days=10, read=True)


def seed():
    """Add the sample data once.

    Returns ``[(role label, e-mail, name), ...]`` for the new accounts, or ``[]`` when the sample data is already there.
    """
    if User.query.filter_by(email=FIRST_SAMPLE_EMAIL).first() is not None:
        return []
    admin = User.query.filter_by(role=C.ROLE_ADMIN).order_by(User.id).first()
    if admin is None:
        raise RuntimeError("Create the administrator first: run  python init_db.py")
    with current_app.test_request_context():  # lets the notification links use url_for
        people, shelters = _people(admin)
        reports = _reports(people)
        animals = _animals(people, shelters, reports)
        _medical(people, animals)
        tasks = _tasks(people, animals, shelters, reports)
        applications = _adoptions(people, animals, shelters)
        _messages()
        _notices(people, animals, reports, applications, tasks)
        db.session.commit()
    return [(C.ROLE_LABELS[role], email, name) for _key, role, email, name, _phone in ACCOUNTS]
