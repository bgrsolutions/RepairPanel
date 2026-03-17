from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional


class PublicStatusLookupForm(FlaskForm):
    ticket_number = StringField(_l("Ticket Number"), validators=[DataRequired(), Length(max=50)])
    verifier = StringField(_l("Phone or Email"), validators=[DataRequired(), Length(max=255)])
    submit = SubmitField(_l("Check Status"))


class PublicContactUpdateForm(FlaskForm):
    contact_person = StringField(_l("Contact Person"), validators=[Optional(), Length(max=120)])
    contact_phone = StringField(_l("Contact Phone"), validators=[Optional(), Length(max=50)])
    contact_email = StringField(_l("Contact Email"), validators=[Optional(), Length(max=255)])
    remarks = TextAreaField(_l("Collection/Contact Remarks"), validators=[Optional(), Length(max=1000)])
    submit = SubmitField(_l("Save Contact Preferences"))


class PublicQuoteApprovalForm(FlaskForm):
    class Meta:
        csrf = False

    actor_name = StringField(_l("Your Name"), validators=[DataRequired(), Length(max=120)])
    actor_contact = StringField(_l("Phone/Email"), validators=[DataRequired(), Length(max=255)])
    language = SelectField(_l("Language"), choices=[("en", _l("English")), ("es", _l("Español"))], default="en")
    payment_choice = SelectField(_l("Payment"), choices=[("pay_in_store", _l("Pay in store")), ("pay_now", _l("Pay now online"))], default="pay_in_store")
    declined_reason = TextAreaField(_l("Decline reason"), validators=[Optional(), Length(max=2000)])
    decision = SelectField(_l("Decision"), choices=[("approved", _l("Approve Quote")), ("declined", _l("Decline Quote"))], validators=[DataRequired()])
    submit = SubmitField(_l("Submit Decision"))
