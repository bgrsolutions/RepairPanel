from flask_wtf import FlaskForm
from wtforms import DateField, DecimalField, FieldList, FormField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


LINE_TYPES = [("labour", "Labour"), ("part", "Part"), ("fixed", "Fixed")]


class QuoteLineForm(FlaskForm):
    class Meta:
        csrf = False

    line_type = SelectField("Line Type", choices=LINE_TYPES, validators=[DataRequired()])
    description = StringField("Description", validators=[DataRequired(), Length(max=255)])
    quantity = DecimalField("Qty", validators=[DataRequired(), NumberRange(min=0)], places=2, default=1)
    unit_price = DecimalField("Unit Price", validators=[DataRequired(), NumberRange(min=0)], places=2, default=0)


class QuoteOptionForm(FlaskForm):
    class Meta:
        csrf = False

    name = StringField("Option Name", validators=[DataRequired(), Length(max=120)])
    lines = FieldList(FormField(QuoteLineForm), min_entries=1, max_entries=10)


class QuoteCreateForm(FlaskForm):
    currency = StringField("Currency", validators=[DataRequired(), Length(max=10)], default="EUR")
    language = SelectField("Language", choices=[("en", "English"), ("es", "Español")], validators=[DataRequired()], default="en")
    expires_at = DateField("Expires At", validators=[Optional()], format="%Y-%m-%d")
    notes_snapshot = TextAreaField("Quote Notes", validators=[Optional(), Length(max=5000)])
    terms_snapshot = TextAreaField("Terms Snapshot", validators=[Optional(), Length(max=5000)])
    options = FieldList(FormField(QuoteOptionForm), min_entries=1, max_entries=3)
    submit = SubmitField("Create Quote")
