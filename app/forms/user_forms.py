from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, SelectMultipleField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, Length, Optional


class UserCreateForm(FlaskForm):
    full_name = StringField(_l("Full Name"), validators=[DataRequired(), Length(max=120)])
    email = StringField(_l("Email"), validators=[DataRequired(), Email(check_deliverability=False), Length(max=255)])
    password = PasswordField(_l("Password"), validators=[DataRequired(), Length(min=8, max=128)])
    preferred_language = StringField(_l("Preferred Language"), validators=[Optional(), Length(max=5)], default="en")
    role_ids = SelectMultipleField(_l("Roles"), validators=[DataRequired()], coerce=str)
    branch_ids = SelectMultipleField(_l("Branch Access"), coerce=str)
    is_active = BooleanField(_l("Active"), default=True)
    submit = SubmitField(_l("Create User"))


class UserEditForm(FlaskForm):
    full_name = StringField(_l("Full Name"), validators=[DataRequired(), Length(max=120)])
    email = StringField(_l("Email"), validators=[DataRequired(), Email(check_deliverability=False), Length(max=255)])
    password = PasswordField(_l("Reset Password"), validators=[Optional(), Length(min=8, max=128)])
    preferred_language = StringField(_l("Preferred Language"), validators=[Optional(), Length(max=5)], default="en")
    role_ids = SelectMultipleField(_l("Roles"), validators=[DataRequired()], coerce=str)
    branch_ids = SelectMultipleField(_l("Branch Access"), coerce=str)
    is_active = BooleanField(_l("Active"))
    submit = SubmitField(_l("Save Changes"))
