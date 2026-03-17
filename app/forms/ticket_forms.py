from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import DateTimeLocalField, HiddenField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional


class TicketCreateForm(FlaskForm):
    customer_id = HiddenField(_l("Customer"), validators=[DataRequired()])
    device_id = SelectField(_l("Device"), validators=[DataRequired()], coerce=str)
    branch_id = SelectField(_l("Branch"), validators=[DataRequired()], coerce=str)
    repair_service_id = SelectField(_l("Repair Service"), validators=[Optional()], coerce=str)
    assigned_technician_id = SelectField(_l("Assigned Technician"), validators=[Optional()], coerce=str)
    internal_status = SelectField(
        _l("Workflow Status"),
        choices=[
            ("", _l("Auto")),
            ("unassigned", _l("Unassigned")),
            ("assigned", _l("Assigned")),
            ("awaiting_diagnostics", _l("Awaiting Diagnostics")),
            ("awaiting_parts", _l("Awaiting Parts")),
            ("in_repair", _l("In Repair")),
            ("ready_for_collection", _l("Ready for Collection")),
        ],
        validators=[Optional()],
    )
    priority = SelectField(
        _l("Priority"),
        choices=[("low", _l("Low")), ("normal", _l("Normal")), ("high", _l("High")), ("urgent", _l("Urgent"))],
        default="normal",
    )
    issue_summary = TextAreaField(_l("Issue / Summary"), validators=[Optional(), Length(max=5000)])
    device_condition = TextAreaField(_l("Device Condition"), validators=[Optional(), Length(max=2000)])
    accessories = StringField(_l("Accessories Received"), validators=[Optional(), Length(max=500)])
    customer_notes = TextAreaField(_l("Customer Notes"), validators=[Optional(), Length(max=2000)])
    quoted_completion_at = DateTimeLocalField(_l("Promised Completion"), validators=[Optional()], format="%Y-%m-%dT%H:%M")
    submit = SubmitField(_l("Check In Device"))
