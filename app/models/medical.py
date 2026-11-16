"""Veterinary examination records and vaccinations."""
from app.extensions import db
from app.utils.timeutil import utcnow


class MedicalRecord(db.Model):
    __tablename__ = "medical_records"
    __table_args__ = (db.Index("ix_medical_records_animal_date", "animal_id", "examination_date"),)

    id = db.Column(db.Integer, primary_key=True)
    animal_id = db.Column(db.Integer, db.ForeignKey("animals.id", ondelete="CASCADE"), nullable=False)
    veterinarian_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    examination_date = db.Column(db.Date, nullable=False)
    weight_kg = db.Column(db.Float, nullable=True)
    symptoms = db.Column(db.Text, nullable=True)
    diagnosis = db.Column(db.Text, nullable=False)
    treatment = db.Column(db.Text, nullable=True)
    medicines = db.Column(db.Text, nullable=True)
    medical_status = db.Column(db.String(30), nullable=False, default="Under Observation")
    notes = db.Column(db.Text, nullable=True)
    follow_up_date = db.Column(db.Date, nullable=True, index=True)
    document_filename = db.Column(db.String(255), nullable=True)
    document_original_name = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    animal = db.relationship("Animal", backref=db.backref("medical_records", order_by="MedicalRecord.examination_date", cascade="all, delete-orphan"))
    veterinarian = db.relationship("User", foreign_keys=[veterinarian_id], backref=db.backref("medical_records"))
    creator = db.relationship("User", foreign_keys=[created_by])
    updater = db.relationship("User", foreign_keys=[updated_by])


class Vaccination(db.Model):
    __tablename__ = "vaccinations"

    id = db.Column(db.Integer, primary_key=True)
    animal_id = db.Column(db.Integer, db.ForeignKey("animals.id", ondelete="CASCADE"), nullable=False, index=True)
    medical_record_id = db.Column(db.Integer, db.ForeignKey("medical_records.id", ondelete="SET NULL"), nullable=True)
    vaccine_name = db.Column(db.String(120), nullable=False)
    vaccination_date = db.Column(db.Date, nullable=False)
    next_due_date = db.Column(db.Date, nullable=True, index=True)
    administered_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    batch_number = db.Column(db.String(60), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    reminder_sent = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    animal = db.relationship("Animal", backref=db.backref("vaccinations", order_by="Vaccination.vaccination_date", cascade="all, delete-orphan"))
    medical_record = db.relationship("MedicalRecord", backref=db.backref("vaccinations"))
    administrator = db.relationship("User", foreign_keys=[administered_by])
