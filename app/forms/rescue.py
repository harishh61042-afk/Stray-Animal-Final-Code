"""Rescue reporting and coordination forms."""
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import DateTimeLocalField, IntegerField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, InputRequired, Length, NumberRange, Optional

from app import constants as C
from app.forms import int_or_none
from app.forms.validators import email_format, phone_number
from app.forms.validators import latitude as latitude_check
from app.forms.validators import longitude as longitude_check

IMAGE_TYPES = list(C.ALLOWED_IMAGE_EXTENSIONS)
DATETIME_FORMATS = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"]


class ReportForm(FlaskForm):
    """The public "report an animal" form (guests and signed-in users)."""

    reporter_name = StringField("Your name", validators=[DataRequired(), Length(min=2, max=100)])
    reporter_phone = StringField("Your phone number", validators=[DataRequired(), Length(max=20), phone_number])
    reporter_email = StringField("Your e-mail (optional)", validators=[Optional(), Length(max=120), email_format])

    animal_type = SelectField(
        "Type of animal", choices=C.blank_choices(C.ANIMAL_TYPES, "Select the animal"),
        validators=[DataRequired(message="Please choose the type of animal.")],
    )
    animal_count = IntegerField(
        "How many animals?", default=1,
        validators=[InputRequired(message="Please enter how many animals there are."),
                    NumberRange(min=1, max=50, message="Enter a number between 1 and 50.")],
    )
    animal_description = TextAreaField(
        "Describe the animal",
        validators=[DataRequired(), Length(min=10, max=2000, message="Please describe the animal in 10 to 2000 characters.")],
    )
    approximate_age = StringField("Approximate age (optional)", validators=[Optional(), Length(max=50)])
    animal_condition = SelectField(
        "What is wrong?", choices=C.blank_choices(C.ANIMAL_CONDITIONS, "Select the condition"),
        validators=[DataRequired(message="Please choose the animal's condition.")],
    )
    emergency_level = SelectField(
        "How urgent is it?", choices=C.choices(C.EMERGENCY_LEVELS), default=C.EMERGENCY_MEDIUM,
        validators=[DataRequired(message="Please choose how urgent it is.")],
    )

    location_name = StringField("Place or area", validators=[DataRequired(), Length(max=150)])
    address = TextAreaField("Full address or nearest landmark", validators=[DataRequired(), Length(max=500)])
    latitude = StringField("Latitude", validators=[Optional(), latitude_check])
    longitude = StringField("Longitude", validators=[Optional(), longitude_check])

    additional_info = TextAreaField("Anything else we should know? (optional)", validators=[Optional(), Length(max=2000)])
    image = FileField(
        "Photo of the animal (optional)",
        validators=[FileAllowed(IMAGE_TYPES, "Please choose a PNG, JPG, GIF or WEBP picture.")],
    )
    website = StringField("Leave this field empty", validators=[Optional(), Length(max=100)])  # honeypot for bots


class TrackForm(FlaskForm):
    code = StringField("Report ID", validators=[DataRequired(), Length(max=30)])
    contact = StringField("Phone number or e-mail used in the report", validators=[DataRequired(), Length(max=120)])


class AssignForm(FlaskForm):
    """Administrator assigns a rescuer (the choices are validated by the service)."""

    rescuer_id = SelectField(
        "Rescuer", coerce=int_or_none, validate_choice=False,
        validators=[DataRequired(message="Please choose a rescuer.")],
    )
    deadline = DateTimeLocalField("Complete by (optional)", format=DATETIME_FORMATS, validators=[Optional()])
    instructions = TextAreaField("Instructions for the rescuer (optional)", validators=[Optional(), Length(max=1000)])


class StatusForm(FlaskForm):
    status = SelectField("New status", validate_choice=False, validators=[DataRequired(message="Please choose a status.")])
    note = TextAreaField("Note (optional)", validators=[Optional(), Length(max=1000)])


class NoteForm(FlaskForm):
    note = TextAreaField("Note", validators=[DataRequired(message="Please write a note first."), Length(max=1000)])


class RespondForm(FlaskForm):
    decision = SelectField(
        "Your answer", choices=[("accept", "Accept"), ("decline", "Decline")],
        validators=[DataRequired(message="Please accept or decline the case.")],
    )
    note = TextAreaField("Note (required when declining)", validators=[Optional(), Length(max=500)])


class CompleteForm(FlaskForm):
    outcome = SelectField(
        "Outcome",
        choices=[("rescued", "The animal was rescued"), ("not_found", "The animal could not be found or rescued")],
        default="rescued", validators=[DataRequired()],
    )
    details = TextAreaField(
        "What happened?",
        validators=[DataRequired(message="Please describe the outcome."), Length(min=5, max=2000)],
    )
