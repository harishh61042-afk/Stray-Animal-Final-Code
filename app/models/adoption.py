"""Adoption applications and the final adoption record."""
from app import constants as C
from app.extensions import db
from app.utils.timeutil import utcnow


class AdoptionApplication(db.Model):
    __tablename__ = "adoption_applications"
    __table_args__ = (db.Index("ix_adoption_applications_animal_status", "animal_id", "status"),)

    id = db.Column(db.Integer, primary_key=True)
    application_code = db.Column(db.String(30), nullable=False, unique=True, index=True)  # e.g. ADP-2026-00012
    animal_id = db.Column(db.Integer, db.ForeignKey("animals.id", ondelete="CASCADE"), nullable=False)
    adopter_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    applicant_name = db.Column(db.String(100), nullable=False)
    applicant_email = db.Column(db.String(120), nullable=False)
    applicant_phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.Text, nullable=False)
    city = db.Column(db.String(80), nullable=False)
    state = db.Column(db.String(80), nullable=True)
    pincode = db.Column(db.String(10), nullable=True)
    occupation = db.Column(db.String(100), nullable=True)
    housing_type = db.Column(db.String(40), nullable=False)
    household_members = db.Column(db.Integer, nullable=True)
    has_other_pets = db.Column(db.Boolean, nullable=False, default=False)
    other_pets_details = db.Column(db.Text, nullable=True)
    previous_experience = db.Column(db.Text, nullable=True)
    adoption_reason = db.Column(db.Text, nullable=False)
    agreed_to_terms = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(20), nullable=False, default="Pending", index=True)
    review_comment = db.Column(db.Text, nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    animal = db.relationship("Animal", backref=db.backref("applications", order_by="AdoptionApplication.id", cascade="all, delete-orphan"))
    adopter = db.relationship("User", foreign_keys=[adopter_id], backref=db.backref("adoption_applications"))
    reviewer = db.relationship("User", foreign_keys=[reviewed_by])

    @property
    def is_active(self):
        return self.status in C.ACTIVE_ADOPTION_STATUSES

    @property
    def can_be_cancelled(self):
        return self.status in C.ACTIVE_ADOPTION_STATUSES


class AdoptionRecord(db.Model):
    """Written once when an adoption is completed.

    ``animal_id`` is UNIQUE, so the database itself refuses a second
    completed adoption for the same animal.
    """

    __tablename__ = "adoption_records"

    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("adoption_applications.id", ondelete="RESTRICT"), nullable=False, unique=True)
    animal_id = db.Column(db.Integer, db.ForeignKey("animals.id", ondelete="RESTRICT"), nullable=False, unique=True)
    adopter_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    shelter_id = db.Column(db.Integer, db.ForeignKey("shelter_profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    adoption_date = db.Column(db.Date, nullable=False)
    completed_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    final_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    application = db.relationship("AdoptionApplication", backref=db.backref("record", uselist=False))
    animal = db.relationship("Animal", backref=db.backref("adoption_record", uselist=False))
    adopter = db.relationship("User", foreign_keys=[adopter_id], backref=db.backref("adoptions"))
    shelter = db.relationship("ShelterProfile", backref=db.backref("adoption_records"))
    completer = db.relationship("User", foreign_keys=[completed_by])
