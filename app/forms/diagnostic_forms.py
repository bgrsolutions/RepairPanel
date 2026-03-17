from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import DecimalField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class DiagnosticForm(FlaskForm):
    customer_reported_fault = TextAreaField(_l("Customer Reported Fault"), validators=[DataRequired(), Length(max=5000)])
    technician_diagnosis = TextAreaField(_l("Technician Diagnosis"), validators=[DataRequired(), Length(max=5000)])
    recommended_repair = TextAreaField(_l("Recommended Repair"), validators=[Optional(), Length(max=5000)])
    estimated_labour = DecimalField(_l("Estimated Labour"), validators=[Optional(), NumberRange(min=0)], places=2)
    repair_notes = TextAreaField(_l("Repair Notes"), validators=[Optional(), Length(max=5000)])
    submit = SubmitField(_l("Save Diagnosis"))
