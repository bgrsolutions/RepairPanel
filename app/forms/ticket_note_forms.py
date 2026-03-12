from flask_wtf import FlaskForm
from wtforms import SelectField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length


class TicketAssignmentForm(FlaskForm):
    assigned_technician_id = SelectField("Assigned Technician", validators=[DataRequired()], coerce=str)
    submit = SubmitField("Assign Technician")


class TicketNoteForm(FlaskForm):
    note_type = SelectField(
        "Note Type",
        choices=[
            ("internal", "Internal Note"),
            ("customer", "Customer-Facing Note"),
            ("communication", "Communication / Call Log"),
        ],
        validators=[DataRequired()],
    )
    content = TextAreaField("Note", validators=[DataRequired(), Length(max=5000)])
    submit = SubmitField("Add Note")


class TicketStatusForm(FlaskForm):
    internal_status = SelectField(
        "Workflow Status",
        choices=[
            ("unassigned", "Unassigned"),
            ("assigned", "Assigned"),
            ("awaiting_diagnostics", "Awaiting Diagnostics"),
            ("awaiting_quote_approval", "Awaiting Quote Approval"),
            ("awaiting_parts", "Awaiting Parts"),
            ("in_repair", "In Repair"),
            ("testing_qa", "Testing / QA"),
            ("ready_for_collection", "Ready for Collection"),
            ("completed", "Completed"),
            ("cancelled", "Cancelled"),
        ],
        validators=[DataRequired()],
    )
    submit = SubmitField("Update Status")
