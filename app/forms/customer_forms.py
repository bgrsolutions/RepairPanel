from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Optional


class CustomerEditForm(FlaskForm):
    full_name = StringField(_l("Full Name / Contact Person"), validators=[DataRequired()])
    phone = StringField(_l("Phone"), validators=[Optional()])
    email = StringField(_l("Email"), validators=[Optional()])
    preferred_language = SelectField(_l("Language"), choices=[("en", _l("English")), ("es", _l("Spanish"))], validators=[Optional()])

    # Business fields
    customer_type = SelectField(_l("Customer Type"), choices=[("individual", _l("Individual")), ("business", _l("Business"))], validators=[DataRequired()])
    company_name = StringField(_l("Company Name"), validators=[Optional()])
    cif_vat = StringField(_l("CIF / VAT Number"), validators=[Optional()])
    billing_address_line_1 = StringField(_l("Billing Address Line 1"), validators=[Optional()])
    billing_address_line_2 = StringField(_l("Billing Address Line 2"), validators=[Optional()])
    billing_postcode = StringField(_l("Billing Postcode"), validators=[Optional()])
    billing_city = StringField(_l("Billing City"), validators=[Optional()])
    billing_region = StringField(_l("Billing Region"), validators=[Optional()])
    billing_country = StringField(_l("Billing Country"), validators=[Optional()])
    billing_email = StringField(_l("Billing Email"), validators=[Optional()])
    billing_phone = StringField(_l("Billing Phone"), validators=[Optional()])
