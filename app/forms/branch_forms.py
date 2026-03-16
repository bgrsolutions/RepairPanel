from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional


class BranchEditForm(FlaskForm):
    code = StringField("Branch Code", validators=[DataRequired(), Length(max=20)])
    name = StringField("Branch / Store Name", validators=[DataRequired(), Length(max=120)])
    company_id = SelectField("Company", validators=[Optional()], coerce=str)
    address_line_1 = StringField("Address Line 1", validators=[Optional(), Length(max=255)])
    address_line_2 = StringField("Address Line 2", validators=[Optional(), Length(max=255)])
    postcode = StringField("Postcode", validators=[Optional(), Length(max=20)])
    city = StringField("City", validators=[Optional(), Length(max=120)])
    island_or_region = StringField("Island / Region", validators=[Optional(), Length(max=120)])
    country = StringField("Country", validators=[Optional(), Length(max=80)])
    phone = StringField("Phone", validators=[Optional(), Length(max=50)])
    email = StringField("Email", validators=[Optional(), Email(), Length(max=255)])
    opening_hours = TextAreaField("Opening Hours", validators=[Optional()])
    ticket_prefix = StringField("Ticket Prefix", validators=[Optional(), Length(max=10)])
    quote_prefix = StringField("Quote Prefix", validators=[Optional(), Length(max=10)])
    submit = SubmitField("Save Branch")
