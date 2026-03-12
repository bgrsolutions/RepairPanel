from flask_wtf import FlaskForm
from wtforms import BooleanField, IntegerField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional


class SupplierForm(FlaskForm):
    name = StringField("Supplier Name", validators=[DataRequired(), Length(max=120)])
    contact_name = StringField("Contact Name", validators=[Optional(), Length(max=120)])
    email = StringField("Email", validators=[Optional(), Email(check_deliverability=False), Length(max=255)])
    phone = StringField("Phone", validators=[Optional(), Length(max=50)])
    website = StringField("Website", validators=[Optional(), Length(max=255)])
    account_reference = StringField("Account / Reference", validators=[Optional(), Length(max=120)])
    default_lead_time_days = IntegerField("Default Lead Time (days)", validators=[Optional()])
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=5000)])
    is_active = BooleanField("Active", default=True)
    submit = SubmitField("Save Supplier")
