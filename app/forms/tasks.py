"""Volunteer task forms: create / edit a task and the small progress forms."""
from flask_wtf import FlaskForm
from wtforms import DateTimeLocalField, FloatField, IntegerField, SelectField, SelectMultipleField, StringField, TextAreaField
from wtforms.validators import DataRequired, InputRequired, Length, NumberRange, Optional

from app import constants as C
from app.forms import int_or_none
from app.forms.validators import latitude as latitude_check
from app.forms.validators import longitude as longitude_check

DATETIME_FORMATS = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"]


class TaskForm(FlaskForm):
    """Create or edit a volunteer task. ``volunteer_ids`` is only used when creating."""

    title = StringField("Task title", validators=[DataRequired(message="Please enter a task title."), Length(max=150)])
    task_type = SelectField(
        "Type of task", choices=C.blank_choices(C.TASK_TYPES, "Choose a type of task"),
        validators=[DataRequired(message="Please choose a type of task.")],
    )
    description = TextAreaField("What needs to be done", validators=[Optional(), Length(max=2000)])
    instructions = TextAreaField("Instructions for volunteers (optional)", validators=[Optional(), Length(max=2000)])
    location_name = StringField("Place", validators=[Optional(), Length(max=150)])
    address = TextAreaField("Address (optional)", validators=[Optional(), Length(max=500)])
    latitude = StringField("Latitude", validators=[Optional(), latitude_check])
    longitude = StringField("Longitude", validators=[Optional(), longitude_check])
    due_at = DateTimeLocalField("Deadline (optional)", format=DATETIME_FORMATS, validators=[Optional()])
    volunteers_needed = IntegerField(
        "Volunteers needed", default=1,
        validators=[InputRequired(message="Enter how many volunteers you need."),
                    NumberRange(min=1, max=50, message="Volunteers needed must be between 1 and 50.")],
    )
    report_id = SelectField("Linked rescue report (optional)", coerce=int_or_none, validate_choice=False)
    animal_id = SelectField("Linked animal (optional)", coerce=int_or_none, validate_choice=False)
    shelter_id = SelectField("Linked shelter (optional)", coerce=int_or_none, validate_choice=False)
    volunteer_ids = SelectMultipleField("Assign volunteers now (optional)", coerce=int, validate_choice=False)


class TaskProgressForm(FlaskForm):
    progress_percent = IntegerField(
        "Progress (%)",
        validators=[InputRequired(message="Enter how far you have got."),
                    NumberRange(min=0, max=99, message="Progress must be between 0 and 99. Use \"Mark completed\" to finish.")],
    )
    note = TextAreaField("What have you done so far? (optional)", validators=[Optional(), Length(max=1000)])


class TaskCompleteForm(FlaskForm):
    notes = TextAreaField("Completion notes (optional)", validators=[Optional(), Length(max=1000)])
    hours = FloatField(
        "Hours spent (optional)", validators=[Optional(), NumberRange(min=0.1, max=100, message="Enter hours between 0.1 and 100.")],
    )


class TaskReasonForm(FlaskForm):
    """Decline a task or cancel one; the reason is optional."""

    reason = TextAreaField("Reason (optional)", validators=[Optional(), Length(max=500)])


class TaskAssignForm(FlaskForm):
    volunteer_id = SelectField(
        "Volunteer", coerce=int_or_none, validate_choice=False,
        validators=[DataRequired(message="Please choose a volunteer.")],
    )
