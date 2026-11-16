"""Shelter profile form (used by the shelter itself and by administrators)."""
from flask_wtf import FlaskForm
from wtforms import IntegerField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError

from app.forms.validators import email_format, phone_number
from app.forms.validators import latitude as latitude_check
from app.forms.validators import longitude as longitude_check


class ShelterProfileForm(FlaskForm):
    shelter_name = StringField("Shelter name", validators=[DataRequired(message="Please enter the shelter name."), Length(max=150)])
    registration_number = StringField("Registration number (optional)", validators=[Optional(), Length(max=60)])
    address = TextAreaField("Address", validators=[DataRequired(message="Please enter the shelter address."), Length(max=500)])
    city = StringField("City", validators=[DataRequired(message="Please enter the city."), Length(max=80)])
    state = StringField("State", validators=[Optional(), Length(max=80)])
    pincode = StringField("PIN code", validators=[Optional(), Length(max=10)])
    latitude = StringField("Latitude", validators=[Optional(), latitude_check])
    longitude = StringField("Longitude", validators=[Optional(), longitude_check])
    contact_phone = StringField("Contact phone", validators=[Optional(), Length(max=20), phone_number])
    contact_email = StringField("Contact e-mail", validators=[Optional(), Length(max=120), email_format])
    website = StringField("Website (optional)", validators=[Optional(), Length(max=200)])
    capacity = IntegerField(
        "Capacity (number of animals)",
        validators=[DataRequired(message="Please enter how many animals the shelter can house."),
                    NumberRange(min=1, max=5000, message="Capacity must be between 1 and 5000.")],
    )
    description = TextAreaField("About the shelter", validators=[Optional(), Length(max=2000)])

    def validate_website(self, field):
        if field.data and not field.data.strip().lower().startswith(("http://", "https://")):
            raise ValidationError("The website must start with http:// or https://")
