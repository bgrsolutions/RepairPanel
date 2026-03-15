from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, SelectMultipleField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, Length, Optional


class UserCreateForm(FlaskForm):
    full_name = StringField("Full Name", validators=[DataRequired(), Length(max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(check_deliverability=False), Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, max=128)])
    preferred_language = StringField("Preferred Language", validators=[Optional(), Length(max=5)], default="en")
    role_ids = SelectMultipleField("Roles", validators=[DataRequired()], coerce=str)
    branch_ids = SelectMultipleField("Branch Access", coerce=str)
    is_active = BooleanField("Active", default=True)
    submit = SubmitField("Create User")


class UserEditForm(FlaskForm):
    full_name = StringField("Full Name", validators=[DataRequired(), Length(max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(check_deliverability=False), Length(max=255)])
    password = PasswordField("Reset Password", validators=[Optional(), Length(min=8, max=128)])
    preferred_language = StringField("Preferred Language", validators=[Optional(), Length(max=5)], default="en")
    role_ids = SelectMultipleField("Roles", validators=[DataRequired()], coerce=str)
    branch_ids = SelectMultipleField("Branch Access", coerce=str)
    is_active = BooleanField("Active")
    submit = SubmitField("Save Changes")
