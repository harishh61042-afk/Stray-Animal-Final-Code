"""Profile tables: one general profile plus one table per specialised role."""
from app import constants as C
from app.extensions import db
from app.services import rules
from app.utils.timeutil import utcnow


class UserProfile(db.Model):
    """Optional personal details shared by every role."""

    __tablename__ = "user_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    address = db.Column(db.Text, nullable=True)
    city = db.Column(db.String(80), nullable=True)
    state = db.Column(db.String(80), nullable=True)
    pincode = db.Column(db.String(10), nullable=True)
    date_of_birth = db.Column(db.Date, nullable=True)
    bio = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    user = db.relationship("User", backref=db.backref("profile", uselist=False, cascade="all, delete-orphan"))


class VolunteerProfile(db.Model):
    __tablename__ = "volunteer_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    skills = db.Column(db.Text, nullable=True)
    experience = db.Column(db.Text, nullable=True)
    availability = db.Column(db.String(200), nullable=True)
    motivation = db.Column(db.Text, nullable=True)
    emergency_contact_name = db.Column(db.String(100), nullable=True)
    emergency_contact_phone = db.Column(db.String(20), nullable=True)
    application_status = db.Column(db.String(20), nullable=False, default="Pending", index=True)
    applied_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    review_note = db.Column(db.Text, nullable=True)

    user = db.relationship(
        "User", foreign_keys=[user_id],
        backref=db.backref("volunteer_profile", uselist=False, cascade="all, delete-orphan"),
    )
    reviewer = db.relationship("User", foreign_keys=[reviewed_by])

    @property
    def is_approved(self):
        return self.application_status == C.APPLICATION_APPROVED


class RescuerProfile(db.Model):
    __tablename__ = "rescuer_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    organization = db.Column(db.String(150), nullable=True)
    experience_years = db.Column(db.Integer, nullable=True)
    service_area = db.Column(db.String(150), nullable=True)
    has_vehicle = db.Column(db.Boolean, nullable=False, default=False)
    verification_details = db.Column(db.Text, nullable=True)
    verification_document = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    user = db.relationship("User", backref=db.backref("rescuer_profile", uselist=False, cascade="all, delete-orphan"))


class VeterinarianProfile(db.Model):
    __tablename__ = "veterinarian_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    clinic_name = db.Column(db.String(150), nullable=True)
    license_number = db.Column(db.String(60), nullable=True)
    specialization = db.Column(db.String(100), nullable=True)
    qualification = db.Column(db.String(150), nullable=True)
    experience_years = db.Column(db.Integer, nullable=True)
    clinic_address = db.Column(db.Text, nullable=True)
    consultation_hours = db.Column(db.String(100), nullable=True)
    verification_details = db.Column(db.Text, nullable=True)
    verification_document = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    user = db.relationship("User", backref=db.backref("veterinarian_profile", uselist=False, cascade="all, delete-orphan"))


class ShelterProfile(db.Model):
    __tablename__ = "shelter_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    shelter_name = db.Column(db.String(150), nullable=False, index=True)
    registration_number = db.Column(db.String(60), nullable=True)
    address = db.Column(db.Text, nullable=True)
    city = db.Column(db.String(80), nullable=True, index=True)
    state = db.Column(db.String(80), nullable=True)
    pincode = db.Column(db.String(10), nullable=True)
    latitude = db.Column(db.Float(53), nullable=True)
    longitude = db.Column(db.Float(53), nullable=True)
    contact_phone = db.Column(db.String(20), nullable=True)
    contact_email = db.Column(db.String(120), nullable=True)
    website = db.Column(db.String(200), nullable=True)
    capacity = db.Column(db.Integer, nullable=False, default=20)
    description = db.Column(db.Text, nullable=True)
    verification_details = db.Column(db.Text, nullable=True)
    verification_document = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    user = db.relationship("User", backref=db.backref("shelter_profile", uselist=False, cascade="all, delete-orphan"))

    # ------------------------------------------------------------ capacity
    @property
    def current_count(self):
        """Animals currently housed here (adopted animals have left)."""
        from app.models.animal import Animal

        return Animal.query.filter(
            Animal.shelter_id == self.id, Animal.status != C.ANIMAL_ADOPTED
        ).count()

    @property
    def available_capacity(self):
        return rules.available_capacity(self.capacity, self.current_count)

    @property
    def is_full(self):
        return not rules.has_capacity(self.capacity, self.current_count)

    @property
    def occupancy_percent(self):
        return rules.occupancy_percent(self.capacity, self.current_count)

    @property
    def is_verified(self):
        return self.user is not None and self.user.is_verified and self.user.is_active

    @property
    def has_location(self):
        return self.latitude is not None and self.longitude is not None

    def __repr__(self):
        return f"<Shelter {self.id} {self.shelter_name}>"
