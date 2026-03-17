from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional


class BranchEditForm(FlaskForm):
    code = StringField(_l("Branch Code"), validators=[DataRequired(), Length(max=20)])
    name = StringField(_l("Branch / Store Name"), validators=[DataRequired(), Length(max=120)])
    company_id = SelectField(_l("Company"), validators=[Optional()], coerce=str)
    address_line_1 = StringField(_l("Address Line 1"), validators=[Optional(), Length(max=255)])
    address_line_2 = StringField(_l("Address Line 2"), validators=[Optional(), Length(max=255)])
    postcode = StringField(_l("Postcode"), validators=[Optional(), Length(max=20)])
    city = StringField(_l("City"), validators=[Optional(), Length(max=120)])
    island_or_region = StringField(_l("Island / Region"), validators=[Optional(), Length(max=120)])
    country = StringField(_l("Country"), validators=[Optional(), Length(max=80)])
    phone = StringField(_l("Phone"), validators=[Optional(), Length(max=50)])
    email = StringField(_l("Email"), validators=[Optional(), Email(), Length(max=255)])
    opening_hours = TextAreaField(_l("Opening Hours"), validators=[Optional()])
    ticket_prefix = StringField(_l("Ticket Prefix"), validators=[Optional(), Length(max=10)])
    quote_prefix = StringField(_l("Quote Prefix"), validators=[Optional(), Length(max=10)])
    submit = SubmitField(_l("Save Branch"))
