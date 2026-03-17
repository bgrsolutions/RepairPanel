from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional


class CompanyForm(FlaskForm):
    legal_name = StringField(_l("Legal Name"), validators=[DataRequired(), Length(max=200)])
    trading_name = StringField(_l("Trading Name"), validators=[Optional(), Length(max=200)])
    cif_nif = StringField(_l("CIF / NIF"), validators=[Optional(), Length(max=30)])
    tax_mode = SelectField(
        _l("Tax Mode"),
        choices=[("IGIC", _l("IGIC (Canary Islands)")), ("VAT", _l("VAT / IVA")), ("none", _l("No Tax"))],
        default="IGIC",
    )
    phone = StringField(_l("Phone"), validators=[Optional(), Length(max=50)])
    email = StringField(_l("Email"), validators=[Optional(), Email(), Length(max=255)])
    website = StringField(_l("Website"), validators=[Optional(), Length(max=255)])
    default_quote_terms = TextAreaField(_l("Default Quote Terms"), validators=[Optional()])
    default_repair_terms = TextAreaField(_l("Default Repair Terms"), validators=[Optional()])
    document_footer = TextAreaField(_l("Document Footer"), validators=[Optional()])
    submit = SubmitField(_l("Save Company"))
