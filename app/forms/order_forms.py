from flask_wtf import FlaskForm
from wtforms import DateField, DecimalField, FieldList, FormField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class PartOrderLineForm(FlaskForm):
    class Meta:
        csrf = False

    part_id = SelectField("Part", validators=[DataRequired()], coerce=str)
    quantity = DecimalField("Quantity", validators=[DataRequired(), NumberRange(min=0.01)], places=2)
    unit_cost = DecimalField("Unit Cost", validators=[Optional(), NumberRange(min=0)], places=2)


class PartOrderCreateForm(FlaskForm):
    supplier_id = SelectField("Supplier", validators=[DataRequired()], coerce=str)
    branch_id = SelectField("Branch", validators=[DataRequired()], coerce=str)
    reference = StringField("Order Reference", validators=[Optional(), Length(max=120)])
    shipping_reference = StringField("Shipping Reference", validators=[Optional(), Length(max=120)])
    eta_date = DateField("ETA", validators=[Optional()], format="%Y-%m-%d")
    lines = FieldList(FormField(PartOrderLineForm), min_entries=1, max_entries=10)
    submit = SubmitField("Create Part Order")


class PartOrderStatusForm(FlaskForm):
    event_type = SelectField(
        "Order Status",
        choices=[
            ("ordered", "Ordered"),
            ("shipped", "Shipped"),
            ("delayed", "Delayed"),
            ("partially_arrived", "Partially Arrived"),
            ("arrived", "Arrived"),
            ("installed", "Installed"),
        ],
        validators=[DataRequired()],
    )
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=5000)])
    submit = SubmitField("Update Order Status")
