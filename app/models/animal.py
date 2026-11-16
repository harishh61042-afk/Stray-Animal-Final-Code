"""Rescued animals, their photographs, status history and shelter admissions."""
from app import constants as C
from app.extensions import db
from app.services import rules
from app.utils.timeutil import utcnow


class Animal(db.Model):
    __tablename__ = "animals"

    id = db.Column(db.Integer, primary_key=True)
    animal_code = db.Column(db.String(30), nullable=False, unique=True, index=True)  # e.g. ANM-2026-00007
    name = db.Column(db.String(80), nullable=True, index=True)
    animal_type = db.Column(db.String(30), nullable=False, index=True)
    breed = db.Column(db.String(80), nullable=True)
    age_months = db.Column(db.Integer, nullable=True)
    gender = db.Column(db.String(10), nullable=False, default="Unknown")
    color = db.Column(db.String(60), nullable=True)
    description = db.Column(db.Text, nullable=True)
    temperament = db.Column(db.String(200), nullable=True)
    rescue_date = db.Column(db.Date, nullable=True)
    rescue_location = db.Column(db.String(200), nullable=True)
    latitude = db.Column(db.Float(53), nullable=True)
    longitude = db.Column(db.Float(53), nullable=True)
    report_id = db.Column(db.Integer, db.ForeignKey("animal_reports.id", ondelete="SET NULL"), nullable=True, index=True)
    shelter_id = db.Column(db.Integer, db.ForeignKey("shelter_profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    veterinarian_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    rescuer_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    registered_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    health_condition = db.Column(db.Text, nullable=True)
    vaccination_status = db.Column(db.String(30), nullable=False, default="Not Vaccinated")
    medical_status = db.Column(db.String(30), nullable=False, default="Under Observation", index=True)
    rehabilitation_status = db.Column(db.String(30), nullable=False, default="Not Started")
    rehabilitation_notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), nullable=False, default="Rescued", index=True)
    available_since = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    report = db.relationship("AnimalReport", backref=db.backref("animals"))
    shelter = db.relationship("ShelterProfile", backref=db.backref("animals"))
    veterinarian = db.relationship("User", foreign_keys=[veterinarian_id], backref=db.backref("assigned_animals"))
    rescuer = db.relationship("User", foreign_keys=[rescuer_id], backref=db.backref("rescued_animals"))
    registrar = db.relationship("User", foreign_keys=[registered_by])

    # ---------------------------------------------------------- display helpers
    @property
    def display_name(self):
        return self.name or f"Unnamed {self.animal_type.lower()}"

    @property
    def age_display(self):
        return rules.age_text(self.age_months)

    @property
    def age_group(self):
        return rules.age_group(self.age_months)

    @property
    def is_available(self):
        return self.status == C.ANIMAL_AVAILABLE

    @property
    def is_adopted(self):
        return self.status == C.ANIMAL_ADOPTED

    @property
    def has_location(self):
        return self.latitude is not None and self.longitude is not None

    @property
    def primary_image(self):
        """The cover photo (an ``AnimalImage``) or ``None``."""
        if not self.images:
            return None
        for image in self.images:
            if image.is_primary:
                return image
        return self.images[0]

    def __repr__(self):
        return f"<Animal {self.animal_code} {self.name!r} {self.status}>"


class AnimalImage(db.Model):
    __tablename__ = "animal_images"

    id = db.Column(db.Integer, primary_key=True)
    animal_id = db.Column(db.Integer, db.ForeignKey("animals.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    caption = db.Column(db.String(200), nullable=True)
    is_primary = db.Column(db.Boolean, nullable=False, default=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    animal = db.relationship("Animal", backref=db.backref("images", order_by="AnimalImage.id", cascade="all, delete-orphan"))


class AnimalStatusHistory(db.Model):
    """Audit trail of every status change an animal goes through."""

    __tablename__ = "animal_status_history"

    id = db.Column(db.Integer, primary_key=True)
    animal_id = db.Column(db.Integer, db.ForeignKey("animals.id", ondelete="CASCADE"), nullable=False, index=True)
    old_status = db.Column(db.String(30), nullable=True)
    new_status = db.Column(db.String(30), nullable=False)
    changed_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    note = db.Column(db.Text, nullable=True)
    changed_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    animal = db.relationship("Animal", backref=db.backref("status_history", order_by="AnimalStatusHistory.id", cascade="all, delete-orphan"))
    changer = db.relationship("User", foreign_keys=[changed_by])


class ShelterAdmission(db.Model):
    """Admission / accommodation record: when an animal entered and left a shelter."""

    __tablename__ = "shelter_admissions"
    __table_args__ = (db.Index("ix_shelter_admissions_shelter_discharged", "shelter_id", "discharged_at"),)

    id = db.Column(db.Integer, primary_key=True)
    shelter_id = db.Column(db.Integer, db.ForeignKey("shelter_profiles.id", ondelete="CASCADE"), nullable=False)
    animal_id = db.Column(db.Integer, db.ForeignKey("animals.id", ondelete="CASCADE"), nullable=False, index=True)
    admitted_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    admitted_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    discharged_at = db.Column(db.DateTime, nullable=True)
    discharge_reason = db.Column(db.String(60), nullable=True)
    capacity_override = db.Column(db.Boolean, nullable=False, default=False)
    override_reason = db.Column(db.Text, nullable=True)
    note = db.Column(db.Text, nullable=True)

    shelter = db.relationship("ShelterProfile", backref=db.backref("admissions"))
    animal = db.relationship("Animal", backref=db.backref("admissions", order_by="ShelterAdmission.id", cascade="all, delete-orphan"))
    admitter = db.relationship("User", foreign_keys=[admitted_by])

    @property
    def is_current(self):
        return self.discharged_at is None
