"""WTForms validators built on the pure helpers in ``app.utils.validators``.

They are plain callables ``(form, field)`` so they can be mixed with the
built-in WTForms validators, e.g. ``validators=[Optional(), phone_number]``.
"""
from wtforms.validators import ValidationError

from app.utils import validators as V


def phone_number(_form, field):
    if field.data and not V.is_valid_phone(field.data):
        raise ValidationError("Enter a valid phone number (7-15 digits).")


def email_format(_form, field):
    if field.data and not V.is_valid_email(field.data):
        raise ValidationError("Enter a valid e-mail address.")


def strong_password(_form, field):
    problems = V.password_problems(field.data)
    if problems:
        raise ValidationError(problems[0])


def latitude(_form, field):
    if field.data not in (None, "") and not V.is_valid_latitude(field.data):
        raise ValidationError("Latitude must be between -90 and 90.")


def longitude(_form, field):
    if field.data not in (None, "") and not V.is_valid_longitude(field.data):
        raise ValidationError("Longitude must be between -180 and 180.")
