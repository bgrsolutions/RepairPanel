from flask_wtf import FlaskForm
from wtforms import DateTimeLocalField, HiddenField, SelectField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Optional


class BookingForm(FlaskForm):
    location_id = SelectField("Location", validators=[DataRequired()], coerce=str)
    customer_id = HiddenField("Customer", validators=[Optional()])
    repair_service_id = SelectField("Repair Service", validators=[Optional()], coerce=str)
    start_time = DateTimeLocalField("Start Time", validators=[DataRequired()], format="%Y-%m-%dT%H:%M")
    end_time = DateTimeLocalField("End Time", validators=[DataRequired()], format="%Y-%m-%dT%H:%M")
    status = SelectField(
        "Status",
        choices=[
            ("scheduled", "Scheduled"),
            ("confirmed", "Confirmed"),
            ("in_progress", "In Progress"),
            ("completed", "Completed"),
            ("cancelled", "Cancelled"),
            ("no_show", "No Show"),
        ],
        default="scheduled",
    )
    notes = TextAreaField("Notes", validators=[Optional()])
    submit = SubmitField("Save Booking")
