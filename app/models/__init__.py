"""Importing this package registers every table with SQLAlchemy."""
from app.models.user import User
from app.models.profiles import (
    RescuerProfile, ShelterProfile, UserProfile, VeterinarianProfile, VolunteerProfile,
)
from app.models.rescue import AnimalReport, RescueActivity, RescueAssignment
from app.models.animal import Animal, AnimalImage, AnimalStatusHistory, ShelterAdmission
from app.models.medical import MedicalRecord, Vaccination
from app.models.volunteer import VolunteerTask, VolunteerTaskAssignment
from app.models.adoption import AdoptionApplication, AdoptionRecord
from app.models.system import AuditLog, ContactMessage, Notification

__all__ = [
    "User", "UserProfile", "VolunteerProfile", "RescuerProfile", "VeterinarianProfile", "ShelterProfile",
    "AnimalReport", "RescueAssignment", "RescueActivity",
    "Animal", "AnimalImage", "AnimalStatusHistory", "ShelterAdmission",
    "MedicalRecord", "Vaccination",
    "VolunteerTask", "VolunteerTaskAssignment",
    "AdoptionApplication", "AdoptionRecord",
    "Notification", "AuditLog", "ContactMessage",
]
