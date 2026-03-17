from flask_wtf import FlaskForm
from wtforms import BooleanField, IntegerField, SelectField, TextAreaField
from wtforms.validators import DataRequired, NumberRange, Optional


class WarrantyForm(FlaskForm):
    """Form for capturing warranty terms on ticket completion/closure."""
    warranty_type = SelectField(
        "Warranty Type",
        choices=[
            ("standard", "Standard"),
            ("custom", "Custom"),
            ("no_warranty", "No Warranty"),
        ],
        default="standard",
        validators=[DataRequired()],
    )
    warranty_days = IntegerField(
        "Warranty Period (Days)",
        default=90,
        validators=[NumberRange(min=0, max=3650)],
    )
    covers_labour = BooleanField("Covers Labour", default=True)
    covers_parts = BooleanField("Covers Parts", default=True)
    terms = TextAreaField("Warranty Terms / Exclusions", validators=[Optional()])
    repair_summary = TextAreaField("Repair Summary", validators=[Optional()])


class WarrantyClaimForm(FlaskForm):
    """Form for recording a warranty claim."""
    claim_notes = TextAreaField("Claim Notes", validators=[DataRequired()])


class WarrantyVoidForm(FlaskForm):
    """Form for voiding a warranty."""
    voided_reason = TextAreaField("Reason for Voiding", validators=[DataRequired()])
