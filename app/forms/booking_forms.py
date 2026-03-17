from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import DateTimeLocalField, HiddenField, SelectField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Optional


class BookingForm(FlaskForm):
    location_id = SelectField(_l("Location"), validators=[DataRequired()], coerce=str)
    customer_id = HiddenField(_l("Customer"), validators=[Optional()])
    repair_service_id = SelectField(_l("Repair Service"), validators=[Optional()], coerce=str)
    start_time = DateTimeLocalField(_l("Start Time"), validators=[DataRequired()], format="%Y-%m-%dT%H:%M")
    end_time = DateTimeLocalField(_l("End Time"), validators=[DataRequired()], format="%Y-%m-%dT%H:%M")
    status = SelectField(
        _l("Status"),
        choices=[
            ("scheduled", _l("Scheduled")),
            ("confirmed", _l("Confirmed")),
            ("in_progress", _l("In Progress")),
            ("completed", _l("Completed")),
            ("cancelled", _l("Cancelled")),
            ("no_show", _l("No Show")),
        ],
        default="scheduled",
    )
    notes = TextAreaField(_l("Notes"), validators=[Optional()])
    submit = SubmitField(_l("Save Booking"))
