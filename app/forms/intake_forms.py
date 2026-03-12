from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import BooleanField, HiddenField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, Optional


CATEGORY_CHOICES = [
    ("phones", "Phones"),
    ("laptops", "Laptops"),
    ("desktops", "Desktops"),
    ("game_consoles", "Game Consoles"),
    ("other", "Other"),
]


class InternalIntakeForm(FlaskForm):
    branch_id = SelectField("Branch", validators=[DataRequired()], coerce=str)
    category = SelectField("Device Category", choices=CATEGORY_CHOICES, validators=[DataRequired()])

    customer_name = StringField("Customer Name", validators=[DataRequired(), Length(max=120)])
    customer_phone = StringField("Customer Phone", validators=[Optional(), Length(max=50)])
    customer_email = StringField("Customer Email", validators=[Optional(), Email(check_deliverability=False), Length(max=255)])

    device_brand = StringField("Device Brand", validators=[DataRequired(), Length(max=80)])
    device_model = StringField("Device Model", validators=[DataRequired(), Length(max=120)])
    serial_number = StringField("Serial Number", validators=[Optional(), Length(max=120)])
    imei = StringField("IMEI", validators=[Optional(), Length(max=60)])

    reported_fault = TextAreaField("Reported Fault", validators=[DataRequired(), Length(max=5000)])
    accessories = TextAreaField("Accessories Included", validators=[Optional(), Length(max=2000)])
    intake_notes = TextAreaField("Intake Notes", validators=[Optional(), Length(max=5000)])

    accepted_disclaimer = BooleanField("Customer accepted intake disclaimer", validators=[DataRequired()])
    signature_data = HiddenField("Signature Data", validators=[Optional()])
    photo = FileField("Upload Photo", validators=[Optional(), FileAllowed(["jpg", "jpeg", "png", "webp"], "Images only")])

    submit = SubmitField("Create Intake")


class PublicIntakeForm(FlaskForm):
    branch_id = SelectField("Branch", validators=[DataRequired()], coerce=str)
    preferred_language = SelectField("Language", choices=[("en", "English"), ("es", "Español")], default="en")
    category = SelectField("Device Category", choices=CATEGORY_CHOICES, validators=[DataRequired()])

    customer_name = StringField("Customer Name", validators=[DataRequired(), Length(max=120)])
    customer_phone = StringField("Customer Phone", validators=[DataRequired(), Length(max=50)])
    customer_email = StringField("Customer Email", validators=[Optional(), Email(check_deliverability=False), Length(max=255)])
    preferred_contact_method = SelectField(
        "Preferred Contact",
        choices=[("phone", "Phone"), ("email", "Email")],
        validators=[DataRequired()],
    )

    device_brand = StringField("Device Brand", validators=[DataRequired(), Length(max=80)])
    device_model = StringField("Device Model", validators=[DataRequired(), Length(max=120)])
    serial_number = StringField("Serial Number", validators=[Optional(), Length(max=120)])
    imei = StringField("IMEI", validators=[Optional(), Length(max=60)])

    reported_fault = TextAreaField("Reported Fault", validators=[DataRequired(), Length(max=5000)])
    accessories = TextAreaField("Accessories Included", validators=[Optional(), Length(max=2000)])
    intake_notes = TextAreaField("Notes", validators=[Optional(), Length(max=5000)])

    accepted_disclaimer = BooleanField("I accept the intake disclaimer", validators=[DataRequired()])
    signature_data = HiddenField("Signature Data", validators=[Optional()])
    photo = FileField("Upload Photo", validators=[Optional(), FileAllowed(["jpg", "jpeg", "png", "webp"], "Images only")])

    submit = SubmitField("Submit Check-In")
