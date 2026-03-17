from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import DateTimeLocalField, SelectField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional


class TicketAssignmentForm(FlaskForm):
    assigned_technician_id = SelectField(_l("Assigned Technician"), validators=[Optional()], coerce=str)
    submit = SubmitField(_l("Assign Technician"))


class TicketNoteForm(FlaskForm):
    note_type = SelectField(
        _l("Note Type"),
        choices=[
            ("internal", _l("Internal Note")),
            ("customer", _l("Customer-Facing Note")),
            ("communication", _l("Communication / Call Log")),
        ],
        validators=[DataRequired()],
    )
    content = TextAreaField(_l("Note"), validators=[DataRequired(), Length(max=5000)])
    submit = SubmitField(_l("Add Note"))


class TicketStatusForm(FlaskForm):
    internal_status = SelectField(
        _l("Workflow Status"),
        choices=[
            ("unassigned", _l("Unassigned")),
            ("assigned", _l("Assigned")),
            ("awaiting_diagnostics", _l("Awaiting Diagnostics")),
            ("awaiting_quote_approval", _l("Awaiting Quote Approval")),
            ("awaiting_parts", _l("Awaiting Parts")),
            ("in_repair", _l("In Repair")),
            ("testing_qa", _l("Testing / QA")),
            ("ready_for_collection", _l("Ready for Collection")),
            ("completed", _l("Completed")),
            ("cancelled", _l("Cancelled")),
            ("archived", _l("Archived")),
        ],
        validators=[DataRequired()],
    )
    submit = SubmitField(_l("Update Status"))


class TicketMetaForm(FlaskForm):
    quoted_completion_at = DateTimeLocalField(_l("Promised Completion"), validators=[Optional()], format="%Y-%m-%dT%H:%M")
    issue_summary = TextAreaField(_l("Issue / Summary"), validators=[Length(max=5000)])
    submit = SubmitField(_l("Update Ticket Details"))
