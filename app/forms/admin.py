"""Forms for the administrator pages."""
from flask_wtf import FlaskForm
from wtforms import BooleanField, IntegerField, PasswordField, SelectField, StringField, TextAreaField
from wtforms.validators import AnyOf, DataRequired, Length, NumberRange, Optional, ValidationError

from app import constants as C
from app.forms.validators import email_format, phone_number, strong_password

ROLE_CHOICES = [(role, C.ROLE_LABELS[role]) for role in C.ALL_ROLES]
STATUS_CHOICES = [(status, status.title()) for status in C.ACCOUNT_STATUSES]


def internal_link(_form, field):
    """A notice may only link to a page of this site (never to another website)."""
    value = (field.data or "").strip()
    if value and (not value.startswith("/") or value.startswith("//") or "\\" in value or " " in value):
        raise ValidationError("Use a page of this site, for example /adopt.")


class AdminUserForm(FlaskForm):
    """Create an account of any type. The fields of the chosen type are checked by ``user_service.admin_create_user``."""

    role = SelectField("Account type", choices=ROLE_CHOICES, default=C.ROLE_ADOPTER)
    full_name = StringField("Full name", validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField("E-mail address", validators=[DataRequired(), Length(max=120), email_format])
    phone = StringField("Phone number", validators=[DataRequired(), Length(max=20), phone_number])
    password = PasswordField("Password (optional)", validators=[Optional(), strong_password])
    must_change_password = BooleanField("Ask the person to choose a new password at the first sign-in", default=True)
    # volunteer
    skills = TextAreaField("Skills", validators=[Optional(), Length(max=1000)])
    availability = StringField("Availability", validators=[Optional(), Length(max=200)])
    # rescuer
    organization = StringField("Organisation / NGO", validators=[Optional(), Length(max=150)])
    service_area = StringField("Area served", validators=[Optional(), Length(max=150)])
    has_vehicle = BooleanField("Has a vehicle for rescues")
    # veterinarian
    license_number = StringField("Licence / registration number", validators=[Optional(), Length(max=60)])
    qualification = StringField("Qualification", validators=[Optional(), Length(max=150)])
    clinic_name = StringField("Clinic / hospital", validators=[Optional(), Length(max=150)])
    # shelter
    shelter_name = StringField("Shelter name", validators=[Optional(), Length(max=150)])
    registration_number = StringField("Registration number", validators=[Optional(), Length(max=60)])
    address = TextAreaField("Shelter address", validators=[Optional(), Length(max=500)])
    city = StringField("City", validators=[Optional(), Length(max=80)])
    state = StringField("State", validators=[Optional(), Length(max=80)])
    pincode = StringField("PIN code", validators=[Optional(), Length(max=10)])
    capacity = IntegerField("Capacity (animals)", validators=[Optional(), NumberRange(min=1, max=5000)])


class UserStatusForm(FlaskForm):
    status = SelectField("Status", choices=STATUS_CHOICES, validators=[DataRequired()])
    reason = TextAreaField("Reason (shown to the person)", validators=[Optional(), Length(max=300)])


class VerificationForm(FlaskForm):
    decision = StringField("Decision", validators=[AnyOf(("approve", "reject"), message="Choose approve or reject.")])
    note = TextAreaField("Note", validators=[Optional(), Length(max=1000)])


class NotificationForm(FlaskForm):
    target = SelectField(
        "Send to",
        choices=[("all", "Everyone with an active account"), ("role", "All accounts of one type"), ("user", "One person")],
        default="all",
    )
    role = SelectField("Account type", choices=[("", "Choose an account type...")] + ROLE_CHOICES, default="")
    user_email = StringField("Person's e-mail address", validators=[Optional(), Length(max=120), email_format])
    title = StringField("Title", validators=[DataRequired(), Length(min=3, max=150)])
    message = TextAreaField("Message", validators=[DataRequired(), Length(min=5, max=1000)])
    link = StringField("Link to a page (optional)", validators=[Optional(), Length(max=255), internal_link])


class ContactStatusForm(FlaskForm):
    status = StringField("Status", validators=[AnyOf(C.CONTACT_STATUSES, message="Invalid status.")])
