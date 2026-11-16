"""Veterinary forms: examination records and vaccinations."""
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import DateField, FloatField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError

from app import constants as C
from app.forms import int_or_none
from app.utils.timeutil import local_today

DOCUMENT_TYPES = list(C.ALLOWED_DOCUMENT_EXTENSIONS)
OTHER_VACCINE = "Other"


def _past_date(_form, field):
    """Examination and vaccination dates describe something that already happened."""
    if field.data and field.data > local_today():
        raise ValidationError("The date cannot be in the future.")
    if field.data and field.data.year < 1990:
        raise ValidationError("Enter a valid date.")


def veterinarian_field_choices(blank_label="Choose the examining veterinarian"):
    from app.forms.animals import veterinarian_choices

    return veterinarian_choices(blank_label)


class MedicalRecordForm(FlaskForm):
    """One veterinary examination. Administrators also pick the examining veterinarian."""

    examination_date = DateField("Examination date", validators=[Optional(), _past_date], default=local_today)
    weight_kg = FloatField(
        "Weight (kg)", validators=[Optional(), NumberRange(min=0.01, max=2000, message="Enter a weight between 0.01 and 2000 kg.")],
    )
    symptoms = TextAreaField("Symptoms observed", validators=[Optional(), Length(max=2000)])
    diagnosis = TextAreaField("Diagnosis", validators=[DataRequired(message="Please enter the diagnosis."), Length(max=2000)])
    treatment = TextAreaField("Treatment given", validators=[Optional(), Length(max=2000)])
    medicines = TextAreaField("Medicines and doses", validators=[Optional(), Length(max=2000)])
    medical_status = SelectField(
        "Medical status after this examination", choices=C.choices(C.MEDICAL_STATUSES),
        validators=[DataRequired(message="Please choose the medical status.")],
    )
    follow_up_date = DateField("Follow-up examination (optional)", validators=[Optional()])
    notes = TextAreaField("Private notes", validators=[Optional(), Length(max=2000)])
    document = FileField(
        "Report or X-ray (optional)",
        validators=[FileAllowed(DOCUMENT_TYPES, "Upload a PDF, PNG or JPG file.")],
    )
    veterinarian_id = SelectField("Examining veterinarian", coerce=int_or_none, validate_choice=False)

    def validate_follow_up_date(self, field):
        examined = self.examination_date.data or local_today()
        if field.data and field.data < examined:
            raise ValidationError("The follow-up cannot be before the examination date.")


class VaccinationForm(FlaskForm):
    """One vaccine dose. ``vaccine_name`` is a list of common vaccines; "Other" asks for a free-text name."""

    vaccine_name = SelectField("Vaccine", choices=C.choices(C.COMMON_VACCINES), validators=[DataRequired()])
    custom_name = StringField("Name of the vaccine", validators=[Length(max=120)])  # no Optional(): checked below
    vaccination_date = DateField("Date given", validators=[Optional(), _past_date], default=local_today)
    next_due_date = DateField("Next dose due (optional)", validators=[Optional()])
    batch_number = StringField("Batch / lot number (optional)", validators=[Optional(), Length(max=60)])
    notes = TextAreaField("Notes (optional)", validators=[Optional(), Length(max=500)])

    def validate_custom_name(self, field):
        if self.vaccine_name.data == OTHER_VACCINE and not (field.data or "").strip():
            raise ValidationError("Please type the name of the vaccine.")

    def validate_next_due_date(self, field):
        given = self.vaccination_date.data or local_today()
        if field.data and field.data <= given:
            raise ValidationError("The next dose must be due after the date it was given.")

    def final_name(self):
        """The vaccine name to store (the typed name when "Other" was chosen)."""
        if self.vaccine_name.data == OTHER_VACCINE:
            return (self.custom_name.data or "").strip()
        return self.vaccine_name.data
