from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Optional


class CustomerEditForm(FlaskForm):
    full_name = StringField("Full Name / Contact Person", validators=[DataRequired()])
    phone = StringField("Phone", validators=[Optional()])
    email = StringField("Email", validators=[Optional()])
    preferred_language = SelectField("Language", choices=[("en", "English"), ("es", "Spanish")], validators=[Optional()])

    # Business fields
    customer_type = SelectField("Customer Type", choices=[("individual", "Individual"), ("business", "Business")], validators=[DataRequired()])
    company_name = StringField("Company Name", validators=[Optional()])
    cif_vat = StringField("CIF / VAT Number", validators=[Optional()])
    billing_address_line_1 = StringField("Billing Address Line 1", validators=[Optional()])
    billing_address_line_2 = StringField("Billing Address Line 2", validators=[Optional()])
    billing_postcode = StringField("Billing Postcode", validators=[Optional()])
    billing_city = StringField("Billing City", validators=[Optional()])
    billing_region = StringField("Billing Region", validators=[Optional()])
    billing_country = StringField("Billing Country", validators=[Optional()])
    billing_email = StringField("Billing Email", validators=[Optional()])
    billing_phone = StringField("Billing Phone", validators=[Optional()])
