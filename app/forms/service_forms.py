from flask_wtf import FlaskForm
from wtforms import BooleanField, DecimalField, IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class RepairServiceForm(FlaskForm):
    name = StringField("Service Name", validators=[DataRequired(), Length(max=200)])
    device_category = SelectField(
        "Device Category",
        choices=[
            ("", "-- Any --"),
            ("phones", "Phones"),
            ("tablets", "Tablets"),
            ("laptops", "Laptops"),
            ("desktops", "Desktops"),
            ("game_consoles", "Game Consoles"),
            ("other", "Other"),
        ],
        validators=[Optional()],
    )
    description = TextAreaField("Description", validators=[Optional()])
    default_part_id = SelectField("Default Part", validators=[Optional()], coerce=str)
    labour_minutes = IntegerField("Labour Time (minutes)", validators=[Optional(), NumberRange(min=0)])
    suggested_sale_price = DecimalField("Suggested Sale Price", validators=[Optional(), NumberRange(min=0)], places=2)
    is_active = BooleanField("Active", default=True)
    submit = SubmitField("Save Service")
