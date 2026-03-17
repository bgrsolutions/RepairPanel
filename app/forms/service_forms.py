from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import BooleanField, DecimalField, IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class RepairServiceForm(FlaskForm):
    name = StringField(_l("Service Name"), validators=[DataRequired(), Length(max=200)])
    device_category = SelectField(
        _l("Device Category"),
        choices=[
            ("", _l("-- Any --")),
            ("phones", _l("Phones")),
            ("tablets", _l("Tablets")),
            ("laptops", _l("Laptops")),
            ("desktops", _l("Desktops")),
            ("game_consoles", _l("Game Consoles")),
            ("other", _l("Other")),
        ],
        validators=[Optional()],
    )
    description = TextAreaField(_l("Description"), validators=[Optional()])
    default_part_id = SelectField(_l("Default Part"), validators=[Optional()], coerce=str)
    labour_minutes = IntegerField(_l("Labour Time (minutes)"), validators=[Optional(), NumberRange(min=0)])
    suggested_sale_price = DecimalField(_l("Suggested Sale Price"), validators=[Optional(), NumberRange(min=0)], places=2)
    is_active = BooleanField(_l("Active"), default=True)
    submit = SubmitField(_l("Save Service"))
