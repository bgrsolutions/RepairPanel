from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField
from wtforms.validators import DataRequired


class TicketCreateForm(FlaskForm):
    customer_id = SelectField("Customer", validators=[DataRequired()], coerce=str)
    device_id = SelectField("Device", validators=[DataRequired()], coerce=str)
    branch_id = SelectField("Branch", validators=[DataRequired()], coerce=str)
    priority = SelectField(
        "Priority",
        choices=[("low", "Low"), ("normal", "Normal"), ("high", "High"), ("urgent", "Urgent")],
        default="normal",
    )
    submit = SubmitField("Create Ticket")
