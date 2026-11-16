"""Adoption forms: the adopter's application and the staff decisions."""
from flask_wtf import FlaskForm
from wtforms import BooleanField, DateField, IntegerField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError

from app import constants as C
from app.forms.validators import email_format, phone_number
from app.utils.timeutil import local_today


class AdoptionApplicationForm(FlaskForm):
    """What a shelter needs to know before it hands an animal to someone."""

    applicant_name = StringField(
        "Full name", validators=[DataRequired(message="Please enter your full name."), Length(max=100)],
    )
    applicant_email = StringField(
        "E-mail", validators=[DataRequired(message="Please enter your e-mail address."), Length(max=120), email_format],
    )
    applicant_phone = StringField(
        "Phone number", validators=[DataRequired(message="Please enter your phone number."), Length(max=20), phone_number],
    )
    occupation = StringField("Occupation (optional)", validators=[Optional(), Length(max=100)])

    address = TextAreaField(
        "Home address", validators=[DataRequired(message="Please enter the address where the animal will live."), Length(max=500)],
    )
    city = StringField("City", validators=[DataRequired(message="Please enter your city."), Length(max=80)])
    state = StringField("State (optional)", validators=[Optional(), Length(max=80)])
    pincode = StringField("PIN code (optional)", validators=[Optional(), Length(max=10)])
    housing_type = SelectField(
        "Type of home", choices=C.blank_choices(C.HOUSING_TYPES, "Choose your type of home"),
        validators=[DataRequired(message="Please choose your type of home.")],
    )
    household_members = IntegerField(
        "People in your household (optional)",
        validators=[Optional(), NumberRange(min=1, max=50, message="Enter a number between 1 and 50.")],
    )

    has_other_pets = BooleanField("I already have other pets")
    other_pets_details = TextAreaField("Tell us about your pets", validators=[Optional(), Length(max=1000)])
    previous_experience = TextAreaField("Experience with animals (optional)", validators=[Optional(), Length(max=1500)])
    adoption_reason = TextAreaField(
        "Why do you want to adopt this animal?",
        validators=[
            DataRequired(message="Please tell us why you want to adopt."),
            Length(min=20, max=2000, message="Please write at least 20 characters so the shelter can get to know you."),
        ],
    )
    agreed_to_terms = BooleanField(
        "I confirm that the information above is true and that I will give this animal food, shelter, "
        "veterinary care and a safe, loving home.",
        validators=[DataRequired(message="Please accept the declaration to send your application.")],
    )


class ReviewCommentForm(FlaskForm):
    """Start a review or approve an application; the comment is optional and is shown to the applicant."""

    comment = TextAreaField("Comment for the applicant (optional)", validators=[Optional(), Length(max=1000)])


class RejectApplicationForm(FlaskForm):
    comment = TextAreaField(
        "Reason", validators=[DataRequired(message="Please explain the decision to the applicant."), Length(max=1000)],
    )


class CompleteAdoptionForm(FlaskForm):
    adoption_date = DateField("Adoption date", validators=[Optional()], default=local_today)
    final_notes = TextAreaField("Final notes (optional)", validators=[Optional(), Length(max=1500)])

    def validate_adoption_date(self, field):
        if field.data and field.data > local_today():
            raise ValidationError("The adoption date cannot be in the future.")
        if field.data and field.data.year < 2000:
            raise ValidationError("Enter a valid adoption date.")
