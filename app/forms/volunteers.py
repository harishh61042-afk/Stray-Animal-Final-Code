"""Volunteer forms: the application (resubmission) and the administrator's decision."""
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField
from wtforms.validators import AnyOf, DataRequired, Length, Optional

from app.forms.validators import phone_number


class VolunteerApplicationForm(FlaskForm):
    """The same questions as the registration form, so a volunteer can fix an application and apply again."""

    skills = TextAreaField(
        "Your skills", validators=[DataRequired(message="Please list your skills."), Length(max=1000)],
    )
    availability = StringField(
        "When are you available?", validators=[DataRequired(message="Please tell us when you are available."), Length(max=200)],
    )
    experience = TextAreaField("Experience with animals (optional)", validators=[Optional(), Length(max=1000)])
    motivation = TextAreaField("Why do you want to volunteer? (optional)", validators=[Optional(), Length(max=1000)])
    emergency_contact_name = StringField("Emergency contact name (optional)", validators=[Optional(), Length(max=100)])
    emergency_contact_phone = StringField(
        "Emergency contact phone (optional)", validators=[Optional(), Length(max=20), phone_number],
    )


class VolunteerReviewForm(FlaskForm):
    """Approve or reject an application. A rejection needs a note (checked by the service as well)."""

    decision = StringField("Decision", validators=[DataRequired(message="Please choose approve or reject."), AnyOf(("approve", "reject"))])
    note = TextAreaField("Note to the volunteer", validators=[Optional(), Length(max=1000)])
