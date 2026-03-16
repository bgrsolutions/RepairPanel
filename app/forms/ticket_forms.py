from flask_wtf import FlaskForm
from wtforms import DateTimeLocalField, HiddenField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional


class TicketCreateForm(FlaskForm):
    customer_id = HiddenField("Customer", validators=[DataRequired()])
    device_id = SelectField("Device", validators=[DataRequired()], coerce=str)
    branch_id = SelectField("Branch", validators=[DataRequired()], coerce=str)
    repair_service_id = SelectField("Repair Service", validators=[Optional()], coerce=str)
    assigned_technician_id = SelectField("Assigned Technician", validators=[Optional()], coerce=str)
    internal_status = SelectField(
        "Workflow Status",
        choices=[
            ("", "Auto"),
            ("unassigned", "Unassigned"),
            ("assigned", "Assigned"),
            ("awaiting_diagnostics", "Awaiting Diagnostics"),
            ("awaiting_parts", "Awaiting Parts"),
            ("in_repair", "In Repair"),
            ("ready_for_collection", "Ready for Collection"),
        ],
        validators=[Optional()],
    )
    priority = SelectField(
        "Priority",
        choices=[("low", "Low"), ("normal", "Normal"), ("high", "High"), ("urgent", "Urgent")],
        default="normal",
    )
    issue_summary = TextAreaField("Issue / Summary", validators=[Optional(), Length(max=5000)])
    device_condition = TextAreaField("Device Condition", validators=[Optional(), Length(max=2000)])
    accessories = StringField("Accessories Received", validators=[Optional(), Length(max=500)])
    customer_notes = TextAreaField("Customer Notes", validators=[Optional(), Length(max=2000)])
    quoted_completion_at = DateTimeLocalField("Promised Completion", validators=[Optional()], format="%Y-%m-%dT%H:%M")
    submit = SubmitField("Check In Device")
