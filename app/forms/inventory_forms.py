from flask_babel import lazy_gettext as _l
from flask_wtf import FlaskForm
from wtforms import BooleanField, DecimalField, HiddenField, IntegerField, SelectField, SelectMultipleField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class PartForm(FlaskForm):
    sku = StringField(_l("SKU"), validators=[DataRequired(), Length(max=80)])
    barcode = StringField(_l("Barcode"), validators=[Optional(), Length(max=120)])
    name = StringField(_l("Part Name"), validators=[DataRequired(), Length(max=255)])
    category = StringField(_l("Category"), validators=[Optional(), Length(max=120)])
    supplier_sku = StringField(_l("Supplier SKU"), validators=[Optional(), Length(max=120)])
    default_supplier_id = SelectField(_l("Default Supplier"), validators=[Optional()], coerce=str)
    supplier_ids = SelectMultipleField(_l("Other Suppliers"), validators=[Optional()], coerce=str)
    category_ids = SelectMultipleField(_l("Categories"), validators=[Optional()], coerce=str)
    lead_time_days = IntegerField(_l("Lead Time (days)"), validators=[Optional(), NumberRange(min=0, max=365)])
    low_stock_threshold = IntegerField(_l("Low Stock Threshold"), validators=[Optional(), NumberRange(min=0, max=10000)], default=3)
    cost_price = DecimalField(_l("Cost Price"), validators=[Optional(), NumberRange(min=0)], places=2)
    sale_price = DecimalField(_l("Sale Price"), validators=[Optional(), NumberRange(min=0)], places=2)
    serial_tracking = BooleanField(_l("Serial Tracking"))
    description = TextAreaField(_l("Description"), validators=[Optional(), Length(max=5000)])
    image_url = StringField(_l("Image URL"), validators=[Optional(), Length(max=255)])
    notes = TextAreaField(_l("Notes"), validators=[Optional(), Length(max=5000)])
    is_active = BooleanField(_l("Active"), default=True)
    submit = SubmitField(_l("Save Part"))


class StockLocationForm(FlaskForm):
    branch_id = SelectField(_l("Branch"), validators=[DataRequired()], coerce=str)
    code = StringField(_l("Code"), validators=[DataRequired(), Length(max=50)])
    name = StringField(_l("Name"), validators=[DataRequired(), Length(max=120)])
    location_type = SelectField(
        _l("Location Type"),
        choices=[
            ("main_stock", _l("Main Stock")),
            ("front_desk", _l("Front Desk")),
            ("workshop_bench", _l("Workshop Bench")),
            ("back_room", _l("Back Room")),
            ("ordered_for_client", _l("Ordered For Client")),
            ("transit", _l("Transit")),
            ("bin", _l("Bin / Shelf")),
        ],
        validators=[DataRequired()],
    )
    submit = SubmitField(_l("Save Location"))


class StockAdjustmentForm(FlaskForm):
    part_id = HiddenField(_l("Part"), validators=[DataRequired()])
    branch_id = SelectField(_l("Branch"), validators=[DataRequired()], coerce=str)
    location_id = SelectField(_l("Location"), validators=[DataRequired()], coerce=str)
    movement_type = SelectField(
        _l("Movement Type"),
        choices=[
            ("inbound", _l("Inbound")),
            ("outbound", _l("Outbound")),
            ("transfer", _l("Transfer")),
            ("adjustment", _l("Adjustment")),
            ("reservation", _l("Reservation")),
            ("release", _l("Release")),
            ("install", _l("Install")),
        ],
        validators=[DataRequired()],
    )
    quantity = DecimalField(_l("Quantity"), validators=[DataRequired(), NumberRange(min=0.01)], places=2)
    notes = TextAreaField(_l("Notes"), validators=[Optional(), Length(max=5000)])
    submit = SubmitField(_l("Apply Movement"))


class StockReservationForm(FlaskForm):
    part_id = SelectField(_l("Part"), validators=[DataRequired()], coerce=str)
    location_id = SelectField(_l("Location"), validators=[DataRequired()], coerce=str)
    quantity = DecimalField(_l("Quantity"), validators=[DataRequired(), NumberRange(min=0.01)], places=2)
    submit = SubmitField(_l("Reserve Part"))


class PartCategoryForm(FlaskForm):
    name = StringField(_l("Category Name"), validators=[DataRequired(), Length(max=120)])
    code = StringField(_l("Code"), validators=[Optional(), Length(max=40)])
    description = TextAreaField(_l("Description"), validators=[Optional(), Length(max=1000)])
    submit = SubmitField(_l("Save Category"))
