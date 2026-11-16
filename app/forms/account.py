"""Forms for the signed-in user's own account pages (profile and password)."""
from flask_wtf import FlaskForm
from wtforms import BooleanField, DateField, IntegerField, PasswordField, StringField, TextAreaField
from wtforms.validators import DataRequired, EqualTo, Length, NumberRange, Optional, ValidationError

from app.forms.validators import phone_number, strong_password
from app.utils.timeutil import local_today


def _not_in_future(_form, field):
    if field.data and field.data > local_today():
        raise ValidationError("The date cannot be in the future.")
    if field.data and field.data.year < 1900:
        raise ValidationError("Enter a valid date.")


class ProfileForm(FlaskForm):
    """One form for every role - the page only shows (and the route only saves) the fields of the user's role."""

    full_name = StringField("Full name", validators=[DataRequired(), Length(min=2, max=100)])
    phone = StringField("Phone number", validators=[DataRequired(), Length(max=20), phone_number])
    date_of_birth = DateField("Date of birth (optional)", validators=[Optional(), _not_in_future])
    address = TextAreaField("Address", validators=[Optional(), Length(max=500)])
    city = StringField("City", validators=[Optional(), Length(max=80)])
    state = StringField("State", validators=[Optional(), Length(max=80)])
    pincode = StringField("PIN code", validators=[Optional(), Length(max=10)])
    bio = TextAreaField("About you (optional)", validators=[Optional(), Length(max=1000)])
    # volunteer
    skills = TextAreaField("Your skills", validators=[Optional(), Length(max=1000)])
    availability = StringField("When are you available?", validators=[Optional(), Length(max=200)])
    experience = TextAreaField("Experience with animals", validators=[Optional(), Length(max=1000)])
    motivation = TextAreaField("Why you volunteer", validators=[Optional(), Length(max=1000)])
    emergency_contact_name = StringField("Emergency contact name", validators=[Optional(), Length(max=100)])
    emergency_contact_phone = StringField(
        "Emergency contact phone", validators=[Optional(), Length(max=20), phone_number])
    # rescuer
    organization = StringField("Organisation / NGO", validators=[Optional(), Length(max=150)])
    service_area = StringField("Area you can serve", validators=[Optional(), Length(max=150)])
    has_vehicle = BooleanField("I have a vehicle I can use for rescues")
    # rescuer and veterinarian
    experience_years = IntegerField("Years of experience", validators=[Optional(), NumberRange(min=0, max=70)])
    # veterinarian
    clinic_name = StringField("Clinic / hospital name", validators=[Optional(), Length(max=150)])
    specialization = StringField("Specialisation", validators=[Optional(), Length(max=100)])
    qualification = StringField("Qualification", validators=[Optional(), Length(max=150)])
    clinic_address = TextAreaField("Clinic address", validators=[Optional(), Length(max=500)])
    consultation_hours = StringField("Consultation hours", validators=[Optional(), Length(max=100)])


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current password", validators=[DataRequired()])
    new_password = PasswordField("New password", validators=[DataRequired(), strong_password])
    confirm_password = PasswordField(
        "Confirm new password",
        validators=[DataRequired(), EqualTo("new_password", message="The two passwords do not match.")],
    )
