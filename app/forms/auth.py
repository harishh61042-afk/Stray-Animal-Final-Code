"""Sign-in and registration forms."""
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import BooleanField, IntegerField, PasswordField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, EqualTo, Length, NumberRange, Optional

from app import constants as C
from app.forms.validators import email_format, latitude, longitude, phone_number, strong_password

SELF_REGISTER_ROLES = (C.ROLE_ADOPTER, C.ROLE_RESCUER, C.ROLE_VETERINARIAN, C.ROLE_SHELTER)
DOCUMENT_TYPES = list(C.ALLOWED_DOCUMENT_EXTENSIONS)


class LoginForm(FlaskForm):
    email = StringField("E-mail address", validators=[DataRequired(), Length(max=120), email_format])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Keep me signed in on this device")


class AccountForm(FlaskForm):
    """Fields every new account needs."""

    full_name = StringField("Full name", validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField("E-mail address", validators=[DataRequired(), Length(max=120), email_format])
    phone = StringField("Phone number", validators=[DataRequired(), Length(max=20), phone_number])
    password = PasswordField("Password", validators=[DataRequired(), strong_password])
    confirm_password = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="The two passwords do not match.")],
    )
    accept_terms = BooleanField(
        "I confirm that the information I give is true and I will use PawConnect responsibly.",
        validators=[DataRequired(message="Please accept this to create your account.")],
    )


class RegisterForm(AccountForm):
    """Adopter / rescuer / veterinarian / shelter registration (role specific blocks are optional here;
    the service checks the ones that belong to the chosen role)."""

    role = SelectField(
        "I want to join as",
        choices=[(role, C.ROLE_LABELS[role]) for role in SELF_REGISTER_ROLES],
        default=C.ROLE_ADOPTER,
    )
    # rescuer
    organization = StringField("Organisation / NGO (optional)", validators=[Optional(), Length(max=150)])
    experience_years = IntegerField("Years of experience", validators=[Optional(), NumberRange(min=0, max=70)])
    service_area = StringField("Area you can serve", validators=[Optional(), Length(max=150)])
    has_vehicle = BooleanField("I have a vehicle I can use for rescues")
    # veterinarian
    license_number = StringField("Licence / registration number", validators=[Optional(), Length(max=60)])
    qualification = StringField("Qualification", validators=[Optional(), Length(max=150)])
    clinic_name = StringField("Clinic / hospital name", validators=[Optional(), Length(max=150)])
    specialization = StringField("Specialisation", validators=[Optional(), Length(max=100)])
    clinic_address = TextAreaField("Clinic address", validators=[Optional(), Length(max=500)])
    consultation_hours = StringField("Consultation hours", validators=[Optional(), Length(max=100)])
    # shelter
    shelter_name = StringField("Shelter name", validators=[Optional(), Length(max=150)])
    registration_number = StringField("Registration number", validators=[Optional(), Length(max=60)])
    address = TextAreaField("Shelter address", validators=[Optional(), Length(max=500)])
    city = StringField("City", validators=[Optional(), Length(max=80)])
    state = StringField("State", validators=[Optional(), Length(max=80)])
    pincode = StringField("PIN code", validators=[Optional(), Length(max=10)])
    latitude = StringField("Latitude", validators=[Optional(), latitude])
    longitude = StringField("Longitude", validators=[Optional(), longitude])
    contact_phone = StringField("Shelter contact phone", validators=[Optional(), Length(max=20), phone_number])
    contact_email = StringField("Shelter contact e-mail", validators=[Optional(), Length(max=120), email_format])
    website = StringField("Website", validators=[Optional(), Length(max=200)])
    capacity = IntegerField("Capacity (animals)", validators=[Optional(), NumberRange(min=1, max=5000)])
    description = TextAreaField("About the shelter", validators=[Optional(), Length(max=2000)])
    # rescuer / veterinarian / shelter
    verification_details = TextAreaField(
        "Verification details", validators=[Optional(), Length(max=2000)],
        description="Tell the administrator who you are: licences, past work, references...",
    )
    verification_document = FileField(
        "Verification document (optional)",
        validators=[FileAllowed(DOCUMENT_TYPES, "Upload a PDF, PNG or JPG file.")],
    )


class VolunteerRegisterForm(AccountForm):
    skills = TextAreaField("Your skills", validators=[DataRequired(), Length(max=1000)])
    availability = StringField("When are you available?", validators=[DataRequired(), Length(max=200)])
    experience = TextAreaField("Experience with animals (optional)", validators=[Optional(), Length(max=1000)])
    motivation = TextAreaField("Why do you want to volunteer? (optional)", validators=[Optional(), Length(max=1000)])
    emergency_contact_name = StringField("Emergency contact name", validators=[Optional(), Length(max=100)])
    emergency_contact_phone = StringField(
        "Emergency contact phone", validators=[Optional(), Length(max=20), phone_number]
    )
