from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, Length


class LoginForm(FlaskForm):
    # Syntax validation only; canonical demo account is a standard .com address.
    email = StringField(_l("Email"), validators=[DataRequired(), Email(check_deliverability=False), Length(max=255)])
    password = PasswordField(_l("Password"), validators=[DataRequired(), Length(min=8, max=128)])
    submit = SubmitField(_l("Sign In"))
