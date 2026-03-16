from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional


class CompanyForm(FlaskForm):
    legal_name = StringField("Legal Name", validators=[DataRequired(), Length(max=200)])
    trading_name = StringField("Trading Name", validators=[Optional(), Length(max=200)])
    cif_nif = StringField("CIF / NIF", validators=[Optional(), Length(max=30)])
    tax_mode = SelectField(
        "Tax Mode",
        choices=[("IGIC", "IGIC (Canary Islands)"), ("VAT", "VAT / IVA"), ("none", "No Tax")],
        default="IGIC",
    )
    phone = StringField("Phone", validators=[Optional(), Length(max=50)])
    email = StringField("Email", validators=[Optional(), Email(), Length(max=255)])
    website = StringField("Website", validators=[Optional(), Length(max=255)])
    default_quote_terms = TextAreaField("Default Quote Terms", validators=[Optional()])
    default_repair_terms = TextAreaField("Default Repair Terms", validators=[Optional()])
    document_footer = TextAreaField("Document Footer", validators=[Optional()])
    submit = SubmitField("Save Company")
