from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional


class PublicStatusLookupForm(FlaskForm):
    ticket_number = StringField("Ticket Number", validators=[DataRequired(), Length(max=50)])
    verifier = StringField("Phone or Email", validators=[DataRequired(), Length(max=255)])
    submit = SubmitField("Check Status")


class PublicQuoteApprovalForm(FlaskForm):
    actor_name = StringField("Your Name", validators=[DataRequired(), Length(max=120)])
    actor_contact = StringField("Phone/Email", validators=[DataRequired(), Length(max=255)])
    language = SelectField("Language", choices=[("en", "English"), ("es", "Español")], default="en")
    declined_reason = TextAreaField("Decline reason", validators=[Optional(), Length(max=5000)])
    decision = SelectField("Decision", choices=[("approved", "Approve"), ("declined", "Decline")], validators=[DataRequired()])
    submit = SubmitField("Submit")
