from flask_wtf import FlaskForm
from wtforms import DateTimeLocalField, DecimalField, FieldList, FormField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


ORDER_STATUS_CHOICES = [
    ("draft", "Draft"),
    ("ordered", "Ordered"),
    ("shipped", "Shipped"),
    ("partially_received", "Partially Received"),
    ("received", "Received"),
    ("cancelled", "Cancelled"),
]


class PartOrderLineForm(FlaskForm):
    class Meta:
        csrf = False

    part_id = SelectField("Part", validators=[Optional()], coerce=str)
    description_override = StringField("Description", validators=[Optional(), Length(max=255)])
    supplier_sku = StringField("Supplier SKU", validators=[Optional(), Length(max=120)])
    quantity = DecimalField("Quantity", validators=[Optional(), NumberRange(min=0.01)], places=2)
    unit_cost = DecimalField("Unit Cost", validators=[Optional(), NumberRange(min=0)], places=2)
    sale_price = DecimalField("Sale Price", validators=[Optional(), NumberRange(min=0)], places=2)


class PartOrderCreateForm(FlaskForm):
    ticket_id = SelectField("Repair Ticket (optional)", validators=[Optional()], coerce=str)
    supplier_id = SelectField("Supplier", validators=[DataRequired()], coerce=str)
    branch_id = SelectField("Branch", validators=[DataRequired()], coerce=str)
    status = SelectField("Status", choices=ORDER_STATUS_CHOICES, validators=[DataRequired()], default="draft")
    reference = StringField("Order Reference", validators=[Optional(), Length(max=120)])
    supplier_reference = StringField("Supplier Reference / PO", validators=[Optional(), Length(max=120)])
    tracking_number = StringField("Tracking Number", validators=[Optional(), Length(max=120)])
    ordered_at = DateTimeLocalField("Ordered At", validators=[Optional()], format="%Y-%m-%dT%H:%M")
    estimated_arrival_at = DateTimeLocalField("Estimated Arrival", validators=[Optional()], format="%Y-%m-%dT%H:%M")
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=5000)])
    lines = FieldList(FormField(PartOrderLineForm), min_entries=1, max_entries=50)
    submit = SubmitField("Save Part Order")


class PartOrderStatusForm(FlaskForm):
    event_type = SelectField("Order Status", choices=ORDER_STATUS_CHOICES, validators=[DataRequired()])
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=5000)])
    submit = SubmitField("Update Order Status")


class ReceiveOrderLineForm(FlaskForm):
    line_id = SelectField("Order Line", validators=[DataRequired()], coerce=str)
    location_id = SelectField("Receive Into Location", validators=[DataRequired()], coerce=str)
    quantity = DecimalField("Received Quantity", validators=[DataRequired(), NumberRange(min=0.01)], places=2)
    received_note = StringField("Delivery Note", validators=[Optional(), Length(max=255)])
    cost_price = DecimalField("Update Cost Price", validators=[Optional(), NumberRange(min=0)], places=2)
    sale_price = DecimalField("Update Sale Price", validators=[Optional(), NumberRange(min=0)], places=2)
    submit = SubmitField("Receive Stock")
