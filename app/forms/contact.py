"""Public contact form."""
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional

from app.forms.validators import email_format


class ContactForm(FlaskForm):
    name = StringField("Your name", validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField("Your e-mail address", validators=[DataRequired(), Length(max=120), email_format])
    subject = StringField("Subject", validators=[DataRequired(), Length(min=3, max=150)])
    message = TextAreaField("Message", validators=[DataRequired(), Length(min=10, max=3000)])
    # Honeypot: hidden with CSS, so only automated form fillers type something here.
    website = StringField("Leave this field empty", validators=[Optional(), Length(max=200)])
