from flask_wtf import FlaskForm
from wtforms import BooleanField, DecimalField, IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class PartForm(FlaskForm):
    sku = StringField("SKU", validators=[DataRequired(), Length(max=80)])
    barcode = StringField("Barcode", validators=[Optional(), Length(max=120)])
    name = StringField("Part Name", validators=[DataRequired(), Length(max=255)])
    category = StringField("Category", validators=[Optional(), Length(max=120)])
    supplier_sku = StringField("Supplier SKU", validators=[Optional(), Length(max=120)])
    default_supplier_id = SelectField("Default Supplier", validators=[Optional()], coerce=str)
    lead_time_days = IntegerField("Lead Time (days)", validators=[Optional(), NumberRange(min=0, max=365)])
    cost_price = DecimalField("Cost Price", validators=[Optional(), NumberRange(min=0)], places=2)
    sale_price = DecimalField("Sale Price", validators=[Optional(), NumberRange(min=0)], places=2)
    serial_tracking = BooleanField("Serial Tracking")
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=5000)])
    is_active = BooleanField("Active", default=True)
    submit = SubmitField("Save Part")


class StockLocationForm(FlaskForm):
    branch_id = SelectField("Branch", validators=[DataRequired()], coerce=str)
    code = StringField("Code", validators=[DataRequired(), Length(max=50)])
    name = StringField("Name", validators=[DataRequired(), Length(max=120)])
    location_type = SelectField(
        "Location Type",
        choices=[
            ("main_stock", "Main Stock"),
            ("front_desk", "Front Desk"),
            ("workshop_bench", "Workshop Bench"),
            ("back_room", "Back Room"),
            ("ordered_for_client", "Ordered For Client"),
            ("transit", "Transit"),
            ("bin", "Bin / Shelf"),
        ],
        validators=[DataRequired()],
    )
    submit = SubmitField("Save Location")


class StockAdjustmentForm(FlaskForm):
    part_id = SelectField("Part", validators=[DataRequired()], coerce=str)
    branch_id = SelectField("Branch", validators=[DataRequired()], coerce=str)
    location_id = SelectField("Location", validators=[DataRequired()], coerce=str)
    movement_type = SelectField(
        "Movement Type",
        choices=[
            ("inbound", "Inbound"),
            ("outbound", "Outbound"),
            ("transfer", "Transfer"),
            ("adjustment", "Adjustment"),
            ("reservation", "Reservation"),
            ("release", "Release"),
            ("install", "Install"),
        ],
        validators=[DataRequired()],
    )
    quantity = DecimalField("Quantity", validators=[DataRequired(), NumberRange(min=0.01)], places=2)
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=5000)])
    submit = SubmitField("Apply Movement")


class StockReservationForm(FlaskForm):
    part_id = SelectField("Part", validators=[DataRequired()], coerce=str)
    location_id = SelectField("Location", validators=[DataRequired()], coerce=str)
    quantity = DecimalField("Quantity", validators=[DataRequired(), NumberRange(min=0.01)], places=2)
    submit = SubmitField("Reserve Part")
