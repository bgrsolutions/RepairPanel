from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import DateField, DecimalField, FieldList, FormField, HiddenField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


LINE_TYPES = [("labour", _l("Labour")), ("part", _l("Part")), ("fixed", _l("Fixed"))]


class QuoteLineForm(FlaskForm):
    class Meta:
        csrf = False

    line_type = SelectField(_l("Line Type"), choices=LINE_TYPES, validators=[Optional()], default="labour")
    linked_part_id = HiddenField(_l("Linked Part ID"), validators=[Optional()])
    description = StringField(_l("Description"), validators=[Optional(), Length(max=255)])
    quantity = DecimalField(_l("Qty"), validators=[Optional(), NumberRange(min=0)], places=2, default=1)
    unit_price = DecimalField(_l("Unit Price"), validators=[Optional(), NumberRange(min=0)], places=2, default=0)


class QuoteOptionForm(FlaskForm):
    class Meta:
        csrf = False

    name = StringField(_l("Option Name"), validators=[DataRequired(), Length(max=120)])
    lines = FieldList(FormField(QuoteLineForm), min_entries=1, max_entries=60)


class QuoteCreateForm(FlaskForm):
    currency = StringField(_l("Currency"), validators=[DataRequired(), Length(max=10)], default="EUR")
    language = SelectField(_l("Language"), choices=[("en", _l("English")), ("es", _l("Español"))], validators=[DataRequired()], default="en")
    expires_at = DateField(_l("Expires At"), validators=[Optional()], format="%Y-%m-%d")
    notes_snapshot = TextAreaField(_l("Quote Notes"), validators=[Optional(), Length(max=5000)])
    terms_snapshot = TextAreaField(_l("Terms Snapshot"), validators=[Optional(), Length(max=5000)])
    options = FieldList(FormField(QuoteOptionForm), min_entries=1, max_entries=5)
    submit = SubmitField(_l("Save Quote"))
