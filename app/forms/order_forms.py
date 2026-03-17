from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import DateTimeLocalField, DecimalField, FieldList, FormField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


ORDER_STATUS_CHOICES = [
    ("draft", _l("Draft")),
    ("ordered", _l("Ordered")),
    ("shipped", _l("Shipped")),
    ("partially_received", _l("Partially Received")),
    ("received", _l("Received")),
    ("cancelled", _l("Cancelled")),
]


class PartOrderLineForm(FlaskForm):
    class Meta:
        csrf = False

    part_id = SelectField(_l("Part"), validators=[Optional()], coerce=str)
    description_override = StringField(_l("Description"), validators=[Optional(), Length(max=255)])
    supplier_sku = StringField(_l("Supplier SKU"), validators=[Optional(), Length(max=120)])
    quantity = DecimalField(_l("Quantity"), validators=[Optional(), NumberRange(min=0.01)], places=2)
    unit_cost = DecimalField(_l("Unit Cost"), validators=[Optional(), NumberRange(min=0)], places=2)
    sale_price = DecimalField(_l("Sale Price"), validators=[Optional(), NumberRange(min=0)], places=2)


class PartOrderCreateForm(FlaskForm):
    ticket_id = SelectField(_l("Repair Ticket (optional)"), validators=[Optional()], coerce=str)
    supplier_id = SelectField(_l("Supplier"), validators=[DataRequired()], coerce=str)
    branch_id = SelectField(_l("Branch"), validators=[DataRequired()], coerce=str)
    status = SelectField(_l("Status"), choices=ORDER_STATUS_CHOICES, validators=[DataRequired()], default="draft")
    reference = StringField(_l("Order Reference"), validators=[Optional(), Length(max=120)])
    supplier_reference = StringField(_l("Supplier Reference / PO"), validators=[Optional(), Length(max=120)])
    tracking_number = StringField(_l("Tracking Number"), validators=[Optional(), Length(max=120)])
    ordered_at = DateTimeLocalField(_l("Ordered At"), validators=[Optional()], format="%Y-%m-%dT%H:%M")
    estimated_arrival_at = DateTimeLocalField(_l("Estimated Arrival"), validators=[Optional()], format="%Y-%m-%dT%H:%M")
    notes = TextAreaField(_l("Notes"), validators=[Optional(), Length(max=5000)])
    lines = FieldList(FormField(PartOrderLineForm), min_entries=1, max_entries=50)
    submit = SubmitField(_l("Save Part Order"))


class PartOrderStatusForm(FlaskForm):
    event_type = SelectField(_l("Order Status"), choices=ORDER_STATUS_CHOICES, validators=[DataRequired()])
    notes = TextAreaField(_l("Notes"), validators=[Optional(), Length(max=5000)])
    submit = SubmitField(_l("Update Order Status"))


class ReceiveOrderLineForm(FlaskForm):
    line_id = SelectField(_l("Order Line"), validators=[DataRequired()], coerce=str)
    location_id = SelectField(_l("Receive Into Location"), validators=[DataRequired()], coerce=str)
    quantity = DecimalField(_l("Received Quantity"), validators=[DataRequired(), NumberRange(min=0.01)], places=2)
    received_note = StringField(_l("Delivery Note"), validators=[Optional(), Length(max=255)])
    cost_price = DecimalField(_l("Update Cost Price"), validators=[Optional(), NumberRange(min=0)], places=2)
    sale_price = DecimalField(_l("Update Sale Price"), validators=[Optional(), NumberRange(min=0)], places=2)
    submit = SubmitField(_l("Receive Stock"))
