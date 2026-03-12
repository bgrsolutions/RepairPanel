from flask_wtf import FlaskForm
from wtforms import DecimalField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class DiagnosticForm(FlaskForm):
    customer_reported_fault = TextAreaField("Customer Reported Fault", validators=[DataRequired(), Length(max=5000)])
    technician_diagnosis = TextAreaField("Technician Diagnosis", validators=[DataRequired(), Length(max=5000)])
    recommended_repair = TextAreaField("Recommended Repair", validators=[Optional(), Length(max=5000)])
    estimated_labour = DecimalField("Estimated Labour", validators=[Optional(), NumberRange(min=0)], places=2)
    repair_notes = TextAreaField("Repair Notes", validators=[Optional(), Length(max=5000)])
    submit = SubmitField("Save Diagnosis")
