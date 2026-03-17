from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import DateTimeLocalField, HiddenField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional


class BookingForm(FlaskForm):
    location_id = SelectField(_l("Location"), validators=[DataRequired()], coerce=str)
    customer_id = HiddenField(_l("Customer"), validators=[Optional()])
    device_id = SelectField(_l("Device"), validators=[Optional()], coerce=str)
    repair_service_id = SelectField(_l("Repair Service"), validators=[Optional()], coerce=str)
    start_time = DateTimeLocalField(_l("Start Time"), validators=[DataRequired()], format="%Y-%m-%dT%H:%M")
    end_time = DateTimeLocalField(_l("End Time"), validators=[DataRequired()], format="%Y-%m-%dT%H:%M")
    status = SelectField(
        _l("Status"),
        choices=[
            ("new", _l("New")),
            ("confirmed", _l("Confirmed")),
            ("arrived", _l("Arrived")),
            ("no_show", _l("No Show")),
            ("converted", _l("Converted")),
            ("cancelled", _l("Cancelled")),
        ],
        default="new",
    )
    customer_name = StringField(_l("Customer Name"), validators=[Optional(), Length(max=200)])
    customer_phone = StringField(_l("Customer Phone"), validators=[Optional(), Length(max=50)])
    notes = TextAreaField(_l("Notes"), validators=[Optional()])
    staff_notes = TextAreaField(_l("Staff Notes"), validators=[Optional()])
    submit = SubmitField(_l("Save Booking"))


class BookingConvertForm(FlaskForm):
    """Form for converting a booking to a ticket."""
    device_id = SelectField(_l("Device"), validators=[DataRequired()], coerce=str)
    branch_id = HiddenField(validators=[Optional()])
    repair_service_id = SelectField(_l("Repair Service"), validators=[Optional()], coerce=str)
    issue_summary = TextAreaField(_l("Issue / Summary"), validators=[Optional(), Length(max=5000)])
    device_condition = TextAreaField(_l("Device Condition"), validators=[Optional(), Length(max=2000)])
    accessories = StringField(_l("Accessories Received"), validators=[Optional(), Length(max=500)])
    submit = SubmitField(_l("Create Ticket from Booking"))
