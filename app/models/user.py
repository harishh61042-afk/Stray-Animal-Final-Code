"""User accounts and role profiles."""
from flask import current_app
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import constants as C
from app.extensions import db
from app.utils.timeutil import utcnow


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    role = db.Column(db.String(20), nullable=False, index=True)
    # Account state: active / inactive / suspended (only "active" may sign in)
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    # Admin verification for rescuer / veterinarian / shelter accounts
    verification_status = db.Column(db.String(20), nullable=False, default="Not Required")
    verification_note = db.Column(db.Text, nullable=True)
    verified_at = db.Column(db.DateTime, nullable=True)
    verified_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)
    failed_login_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    last_login_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    # ---------------------------------------------------------- passwords
    def set_password(self, password):
        method = "pbkdf2:sha256"
        try:
            method = current_app.config.get("PASSWORD_HASH_METHOD", method)
        except RuntimeError:  # no application context
            pass
        self.password_hash = generate_password_hash(password, method=method)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password or "")

    # ---------------------------------------------------- role / state helpers
    @property
    def is_active(self):  # used by Flask-Login
        return self.status == C.ACCOUNT_ACTIVE

    @property
    def is_admin(self):
        return self.role == C.ROLE_ADMIN

    def has_role(self, *roles):
        return self.role in roles

    @property
    def role_label(self):
        return C.ROLE_LABELS.get(self.role, self.role.title())

    @property
    def needs_verification(self):
        return self.role in C.VERIFICATION_REQUIRED_ROLES

    @property
    def is_verified(self):
        """True when the account has its full permissions.

        Rescuers, veterinarians and shelters need an administrator's
        verification; every other role is considered verified.
        """
        if self.needs_verification:
            return self.verification_status == C.VERIFY_VERIFIED
        return True

    @property
    def is_locked(self):
        return bool(self.locked_until and self.locked_until > utcnow())

    @property
    def is_approved_volunteer(self):
        profile = self.volunteer_profile
        return self.role == C.ROLE_VOLUNTEER and profile is not None and profile.application_status == C.APPLICATION_APPROVED

    @property
    def role_profile(self):
        return {
            C.ROLE_VOLUNTEER: self.volunteer_profile,
            C.ROLE_RESCUER: self.rescuer_profile,
            C.ROLE_VETERINARIAN: self.veterinarian_profile,
            C.ROLE_SHELTER: self.shelter_profile,
        }.get(self.role)

    @property
    def initials(self):
        parts = [p for p in (self.full_name or "?").split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    @property
    def first_name(self):
        return (self.full_name or "").split(" ")[0] if self.full_name else ""

    def __repr__(self):
        return f"<User {self.id} {self.email} ({self.role})>"
