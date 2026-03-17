from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import BooleanField, HiddenField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional


CATEGORY_CHOICES = [
    ("phones", _l("Phones")),
    ("laptops", _l("Laptops")),
    ("desktops", _l("Desktops")),
    ("game_consoles", _l("Game Consoles")),
    ("other", _l("Other")),
]


class InternalIntakeForm(FlaskForm):
    branch_id = SelectField(_l("Branch"), validators=[DataRequired()], coerce=str)
    category = SelectField(_l("Device Category"), choices=CATEGORY_CHOICES, validators=[DataRequired()])

    existing_customer_id = HiddenField(_l("Existing Customer"))
    customer_search = StringField(_l("Find Existing Customer"), validators=[Optional(), Length(max=255)])
    customer_name = StringField(_l("Customer Name"), validators=[DataRequired(), Length(max=120)])
    customer_phone = StringField(_l("Customer Phone"), validators=[Optional(), Length(max=50)])
    customer_email = StringField(_l("Customer Email"), validators=[Optional(), Email(check_deliverability=False), Length(max=255)])

    device_brand = StringField(_l("Device Brand"), validators=[DataRequired(), Length(max=80)])
    device_model = StringField(_l("Device Model"), validators=[DataRequired(), Length(max=120)])
    serial_number = StringField(_l("Serial Number"), validators=[Optional(), Length(max=120)])
    imei = StringField(_l("IMEI"), validators=[Optional(), Length(max=60)])

    reported_fault = TextAreaField(_l("Reported Fault"), validators=[DataRequired(), Length(max=5000)])
    device_condition = TextAreaField(_l("Device Condition at Intake"), validators=[Optional(), Length(max=2000)])
    accessories = TextAreaField(_l("Accessories Included"), validators=[Optional(), Length(max=2000)])
    intake_notes = TextAreaField(_l("Intake Notes"), validators=[Optional(), Length(max=5000)])

    # Quick diagnostics (optional at check-in)
    initial_diagnosis = TextAreaField(_l("Initial Diagnosis"), validators=[Optional(), Length(max=5000)])
    recommended_repair = TextAreaField(_l("Recommended Repair"), validators=[Optional(), Length(max=5000)])

    # Pre-repair check items (common quick checks at intake)
    check_powers_on = BooleanField(_l("Device powers on"))
    check_screen_condition = BooleanField(_l("Screen displays correctly"))
    check_charging = BooleanField(_l("Charging port functional"))
    check_buttons = BooleanField(_l("Physical buttons work"))
    check_water_damage = BooleanField(_l("No visible water damage"))

    accepted_disclaimer = BooleanField(_l("Customer accepted intake disclaimer"), validators=[DataRequired()])
    signature_data = HiddenField(_l("Signature Data"), validators=[Optional()])
    photo = FileField(_l("Upload Photo"), validators=[Optional(), FileAllowed(["jpg", "jpeg", "png", "webp"], "Images only")])

    submit = SubmitField(_l("Create Intake"))


class PublicIntakeForm(FlaskForm):
    branch_id = SelectField(_l("Branch"), validators=[DataRequired()], coerce=str)
    preferred_language = SelectField(_l("Language"), choices=[("en", _l("English")), ("es", _l("Español"))], default="en")
    category = SelectField(_l("Device Category"), choices=CATEGORY_CHOICES, validators=[DataRequired()])

    existing_customer_id = HiddenField(_l("Existing Customer"))
    customer_search = StringField(_l("Find Existing Customer"), validators=[Optional(), Length(max=255)])
    customer_name = StringField(_l("Customer Name"), validators=[DataRequired(), Length(max=120)])
    customer_phone = StringField(_l("Customer Phone"), validators=[DataRequired(), Length(max=50)])
    customer_email = StringField(_l("Customer Email"), validators=[Optional(), Email(check_deliverability=False), Length(max=255)])
    preferred_contact_method = SelectField(
        _l("Preferred Contact"),
        choices=[("phone", _l("Phone")), ("email", _l("Email"))],
        validators=[DataRequired()],
    )

    device_brand = StringField(_l("Device Brand"), validators=[DataRequired(), Length(max=80)])
    device_model = StringField(_l("Device Model"), validators=[DataRequired(), Length(max=120)])
    serial_number = StringField(_l("Serial Number"), validators=[Optional(), Length(max=120)])
    imei = StringField(_l("IMEI"), validators=[Optional(), Length(max=60)])

    reported_fault = TextAreaField(_l("Reported Fault"), validators=[DataRequired(), Length(max=5000)])
    accessories = TextAreaField(_l("Accessories Included"), validators=[Optional(), Length(max=2000)])
    intake_notes = TextAreaField(_l("Notes"), validators=[Optional(), Length(max=5000)])

    accepted_disclaimer = BooleanField(_l("I accept the intake disclaimer"), validators=[DataRequired()])
    signature_data = HiddenField(_l("Signature Data"), validators=[Optional()])
    photo = FileField(_l("Upload Photo"), validators=[Optional(), FileAllowed(["jpg", "jpeg", "png", "webp"], "Images only")])

    submit = SubmitField(_l("Submit Check-In"))
