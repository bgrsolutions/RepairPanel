from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import BooleanField, IntegerField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional


class SupplierForm(FlaskForm):
    name = StringField(_l("Supplier Name"), validators=[DataRequired(), Length(max=120)])
    contact_name = StringField(_l("Contact Name"), validators=[Optional(), Length(max=120)])
    email = StringField(_l("Email"), validators=[Optional(), Email(check_deliverability=False), Length(max=255)])
    phone = StringField(_l("Phone"), validators=[Optional(), Length(max=50)])
    website = StringField(_l("Website"), validators=[Optional(), Length(max=255)])
    account_reference = StringField(_l("Account / Reference"), validators=[Optional(), Length(max=120)])
    default_lead_time_days = IntegerField(_l("Default Lead Time (days)"), validators=[Optional()])
    notes = TextAreaField(_l("Notes"), validators=[Optional(), Length(max=5000)])
    is_active = BooleanField(_l("Active"), default=True)
    submit = SubmitField(_l("Save Supplier"))
