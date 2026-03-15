from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional


class PublicStatusLookupForm(FlaskForm):
    ticket_number = StringField("Ticket Number", validators=[DataRequired(), Length(max=50)])
    verifier = StringField("Phone or Email", validators=[DataRequired(), Length(max=255)])
    submit = SubmitField("Check Status")


class PublicContactUpdateForm(FlaskForm):
    contact_person = StringField("Contact Person", validators=[Optional(), Length(max=120)])
    contact_phone = StringField("Contact Phone", validators=[Optional(), Length(max=50)])
    contact_email = StringField("Contact Email", validators=[Optional(), Length(max=255)])
    remarks = TextAreaField("Collection/Contact Remarks", validators=[Optional(), Length(max=1000)])
    submit = SubmitField("Save Contact Preferences")


class PublicQuoteApprovalForm(FlaskForm):
    class Meta:
        csrf = False

    actor_name = StringField("Your Name", validators=[DataRequired(), Length(max=120)])
    actor_contact = StringField("Phone/Email", validators=[DataRequired(), Length(max=255)])
    language = SelectField("Language", choices=[("en", "English"), ("es", "Español")], default="en")
    payment_choice = SelectField("Payment", choices=[("pay_in_store", "Pay in store"), ("pay_now", "Pay now online")], default="pay_in_store")
    declined_reason = TextAreaField("Decline reason", validators=[Optional(), Length(max=2000)])
    decision = SelectField("Decision", choices=[("approved", "Approve Quote"), ("declined", "Decline Quote")], validators=[DataRequired()])
    submit = SubmitField("Submit Decision")
