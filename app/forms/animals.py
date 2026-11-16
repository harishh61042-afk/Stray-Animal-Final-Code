"""Animal record forms."""
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, MultipleFileField
from wtforms import BooleanField, DateField, IntegerField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app import constants as C
from app.forms import int_or_none
from app.forms.validators import latitude as latitude_check
from app.forms.validators import longitude as longitude_check

IMAGE_TYPES = list(C.ALLOWED_IMAGE_EXTENSIONS)


def shelter_choices(blank_label=None):
    """Drop-down choices ``[(id, "Name (3 of 20 places free)")]`` for verified shelters (live occupancy)."""
    from app.services import animal_service  # imported lazily: forms are loaded before the services

    counts = animal_service.occupancy_counts()
    choices = [("", blank_label)] if blank_label else []
    for shelter in animal_service.verified_shelters():
        free = max(shelter.capacity - counts.get(shelter.id, 0), 0)
        choices.append((str(shelter.id), f"{shelter.shelter_name} ({free} of {shelter.capacity} places free)"))
    return choices


def veterinarian_choices(blank_label=None):
    from app.services import animal_service

    choices = [("", blank_label)] if blank_label else []
    choices.extend((str(vet.id), vet.full_name) for vet in animal_service.verified_veterinarians())
    return choices


def fill_registration_choices(form):
    """Fill the shelter / veterinarian drop-downs of an :class:`AnimalForm`."""
    form.shelter_id.choices = shelter_choices("Not admitted to a shelter yet")
    form.veterinarian_id.choices = veterinarian_choices("Assign later")


class AnimalForm(FlaskForm):
    """Register or edit an animal. ``shelter_id`` / ``veterinarian_id`` / ``status`` only matter when registering."""

    name = StringField("Name (optional)", validators=[Optional(), Length(max=80)])
    animal_type = SelectField("Type of animal", choices=C.choices(C.ANIMAL_TYPES), validators=[DataRequired()])
    breed = StringField("Breed (optional)", validators=[Optional(), Length(max=80)])
    gender = SelectField("Gender", choices=C.choices(C.GENDERS), default="Unknown")
    age_years = IntegerField("Age: years", validators=[Optional(), NumberRange(min=0, max=50, message="Years must be between 0 and 50.")])
    age_extra_months = IntegerField("and months", validators=[Optional(), NumberRange(min=0, max=11, message="Months must be between 0 and 11.")])
    color = StringField("Colour / markings", validators=[Optional(), Length(max=60)])
    temperament = StringField("Temperament", validators=[Optional(), Length(max=200)])
    description = TextAreaField("About the animal", validators=[Optional(), Length(max=3000)])

    rescue_date = DateField("Rescue date", validators=[Optional()])
    rescue_location = StringField("Where it was rescued", validators=[Optional(), Length(max=200)])
    latitude = StringField("Latitude", validators=[Optional(), latitude_check])
    longitude = StringField("Longitude", validators=[Optional(), longitude_check])

    health_condition = TextAreaField("Health condition when found", validators=[Optional(), Length(max=2000)])
    medical_status = SelectField("Medical status", choices=C.choices(C.MEDICAL_STATUSES), default=C.MEDICAL_OBSERVATION)
    rehabilitation_status = SelectField("Rehabilitation", choices=C.choices(C.REHAB_STATUSES), default="Not Started")
    rehabilitation_notes = TextAreaField("Rehabilitation notes", validators=[Optional(), Length(max=2000)])

    # registration only
    status = SelectField(
        "Starting status", choices=C.choices((C.ANIMAL_REPORTED, C.ANIMAL_RESCUED)), default=C.ANIMAL_RESCUED,
    )
    shelter_id = SelectField("Admit to a shelter now", coerce=int_or_none, validate_choice=False)
    veterinarian_id = SelectField("Assign a veterinarian", coerce=int_or_none, validate_choice=False)
    capacity_override = BooleanField("Admit even though the shelter is full (administrator only)")
    override_reason = StringField("Reason for exceeding the capacity", validators=[Optional(), Length(max=300)])

    images = MultipleFileField(
        "Photos (optional)",
        validators=[FileAllowed(IMAGE_TYPES, "Please choose PNG, JPG, GIF or WEBP pictures.")],
    )


class ConfirmForm(FlaskForm):
    """Nothing but the CSRF token: one-click actions such as "list for adoption" or "take this case"."""


class ImagesForm(FlaskForm):
    """Add more photos to an existing animal."""

    images = MultipleFileField(
        "Photos", validators=[FileAllowed(IMAGE_TYPES, "Please choose PNG, JPG, GIF or WEBP pictures.")],
    )


class StatusChangeForm(FlaskForm):
    status = SelectField("New status", validate_choice=False, validators=[DataRequired(message="Please choose a status.")])
    note = TextAreaField("Note (optional)", validators=[Optional(), Length(max=500)])


class AssignShelterForm(FlaskForm):
    shelter_id = SelectField("Shelter", coerce=int_or_none, validate_choice=False,
                             validators=[DataRequired(message="Please choose a shelter.")])
    capacity_override = BooleanField("Admit even though the shelter is full")
    override_reason = StringField("Reason for exceeding the capacity", validators=[Optional(), Length(max=300)])


class DischargeForm(FlaskForm):
    reason = SelectField("Reason", choices=C.choices(C.DISCHARGE_REASONS), validators=[DataRequired()])
    note = TextAreaField("Note (optional)", validators=[Optional(), Length(max=500)])


class AssignVetForm(FlaskForm):
    veterinarian_id = SelectField("Veterinarian", coerce=int_or_none, validate_choice=False,
                                  validators=[DataRequired(message="Please choose a veterinarian.")])


class RehabForm(FlaskForm):
    rehabilitation_status = SelectField("Rehabilitation status", choices=C.choices(C.REHAB_STATUSES), validators=[DataRequired()])
    rehabilitation_notes = TextAreaField("Rehabilitation notes", validators=[Optional(), Length(max=2000)])


class WithdrawForm(FlaskForm):
    note = TextAreaField("Reason (optional)", validators=[Optional(), Length(max=500)])
