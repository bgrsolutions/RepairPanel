"""Phase 18: Device intelligence, secure access, service catalog, pre-checks

Revision ID: a1b2c3d4e5f7
Revises: b2c3d4e5f6a7
Create Date: 2026-03-18 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f7"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade():
    # --- Device: richer details ---
    with op.batch_alter_table("devices") as batch_op:
        batch_op.add_column(sa.Column("storage", sa.String(60), nullable=True))
        batch_op.add_column(sa.Column("color", sa.String(60), nullable=True))
        batch_op.add_column(sa.Column("carrier_lock", sa.String(120), nullable=True))
        batch_op.add_column(sa.Column("fmi_status", sa.String(60), nullable=True))
        batch_op.add_column(sa.Column("cosmetic_condition", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("battery_health", sa.String(60), nullable=True))
        batch_op.add_column(sa.Column("cpu", sa.String(120), nullable=True))
        batch_op.add_column(sa.Column("ram", sa.String(60), nullable=True))
        batch_op.add_column(sa.Column("storage_type", sa.String(60), nullable=True))
        batch_op.add_column(sa.Column("gpu", sa.String(120), nullable=True))
        batch_op.add_column(sa.Column("os_info", sa.String(200), nullable=True))
        batch_op.add_column(sa.Column("device_notes", sa.Text(), nullable=True))
        # Secure access data
        batch_op.add_column(sa.Column("unlock_type", sa.String(30), nullable=True))
        batch_op.add_column(sa.Column("unlock_value_encrypted", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("unlock_notes", sa.Text(), nullable=True))
        # IMEI lookup cache
        batch_op.add_column(sa.Column("imei_lookup_data", sa.Text(), nullable=True))

    # --- RepairService: service_code and labour_price ---
    with op.batch_alter_table("repair_services") as batch_op:
        batch_op.add_column(sa.Column("service_code", sa.String(40), nullable=True))
        batch_op.add_column(sa.Column("labour_price", sa.Numeric(10, 2), nullable=True))

    # --- Device pre-check templates ---
    op.create_table(
        "device_precheck_templates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("device_category", sa.String(50), nullable=False, index=True),
        sa.Column("check_key", sa.String(80), nullable=False),
        sa.Column("label_en", sa.String(200), nullable=False),
        sa.Column("label_es", sa.String(200), nullable=True),
        sa.Column("position", sa.Integer(), default=0, nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    # --- Service-parts linking ---
    op.create_table(
        "service_part_links",
        sa.Column("service_id", sa.Uuid(), sa.ForeignKey("repair_services.id"), primary_key=True),
        sa.Column("part_id", sa.Uuid(), sa.ForeignKey("parts.id"), primary_key=True),
        sa.Column("quantity", sa.Numeric(10, 2), default=1, nullable=False),
    )

    # --- Seed default pre-check templates ---
    op.execute("""
        INSERT INTO device_precheck_templates (id, device_category, check_key, label_en, label_es, position, is_active, created_at, updated_at) VALUES
        -- Phones
        (gen_random_uuid(), 'phones', 'powers_on', 'Device powers on', 'El dispositivo enciende', 1, true, now(), now()),
        (gen_random_uuid(), 'phones', 'screen_condition', 'Screen displays correctly', 'La pantalla muestra correctamente', 2, true, now(), now()),
        (gen_random_uuid(), 'phones', 'touch_responsive', 'Touch screen responsive', 'Pantalla táctil responde', 3, true, now(), now()),
        (gen_random_uuid(), 'phones', 'charging_port', 'Charging port functional', 'Puerto de carga funcional', 4, true, now(), now()),
        (gen_random_uuid(), 'phones', 'buttons_work', 'Physical buttons work', 'Botones físicos funcionan', 5, true, now(), now()),
        (gen_random_uuid(), 'phones', 'speakers_mic', 'Speakers and microphone work', 'Altavoces y micrófono funcionan', 6, true, now(), now()),
        (gen_random_uuid(), 'phones', 'cameras', 'Cameras functional', 'Cámaras funcionan', 7, true, now(), now()),
        (gen_random_uuid(), 'phones', 'wifi_bluetooth', 'WiFi/Bluetooth working', 'WiFi/Bluetooth funciona', 8, true, now(), now()),
        (gen_random_uuid(), 'phones', 'water_damage', 'No visible water damage', 'Sin daño por agua visible', 9, true, now(), now()),
        (gen_random_uuid(), 'phones', 'biometrics', 'Biometrics (Face ID/fingerprint) functional', 'Biometría (Face ID/huella) funcional', 10, true, now(), now()),
        -- Laptops
        (gen_random_uuid(), 'laptops', 'powers_on', 'Device powers on', 'El dispositivo enciende', 1, true, now(), now()),
        (gen_random_uuid(), 'laptops', 'screen_condition', 'Screen displays correctly', 'La pantalla muestra correctamente', 2, true, now(), now()),
        (gen_random_uuid(), 'laptops', 'keyboard', 'Keyboard functional', 'Teclado funcional', 3, true, now(), now()),
        (gen_random_uuid(), 'laptops', 'trackpad', 'Trackpad functional', 'Trackpad funcional', 4, true, now(), now()),
        (gen_random_uuid(), 'laptops', 'charging', 'Charges correctly', 'Carga correctamente', 5, true, now(), now()),
        (gen_random_uuid(), 'laptops', 'battery_holds', 'Battery holds charge', 'Batería mantiene carga', 6, true, now(), now()),
        (gen_random_uuid(), 'laptops', 'wifi_bluetooth', 'WiFi/Bluetooth working', 'WiFi/Bluetooth funciona', 7, true, now(), now()),
        (gen_random_uuid(), 'laptops', 'usb_ports', 'USB/ports functional', 'Puertos USB funcionales', 8, true, now(), now()),
        (gen_random_uuid(), 'laptops', 'speakers_mic', 'Speakers and microphone work', 'Altavoces y micrófono funcionan', 9, true, now(), now()),
        (gen_random_uuid(), 'laptops', 'webcam', 'Webcam functional', 'Webcam funcional', 10, true, now(), now()),
        (gen_random_uuid(), 'laptops', 'hinges', 'Hinges intact', 'Bisagras intactas', 11, true, now(), now()),
        -- Desktops
        (gen_random_uuid(), 'desktops', 'powers_on', 'System powers on', 'El sistema enciende', 1, true, now(), now()),
        (gen_random_uuid(), 'desktops', 'display_output', 'Display output working', 'Salida de video funcional', 2, true, now(), now()),
        (gen_random_uuid(), 'desktops', 'usb_ports', 'USB/ports functional', 'Puertos USB funcionales', 3, true, now(), now()),
        (gen_random_uuid(), 'desktops', 'fans_cooling', 'Fans/cooling working', 'Ventiladores/refrigeración funciona', 4, true, now(), now()),
        (gen_random_uuid(), 'desktops', 'storage_detected', 'Storage drives detected', 'Unidades de almacenamiento detectadas', 5, true, now(), now()),
        (gen_random_uuid(), 'desktops', 'network', 'Network connectivity', 'Conectividad de red', 6, true, now(), now()),
        -- Game consoles
        (gen_random_uuid(), 'game_consoles', 'powers_on', 'Console powers on', 'La consola enciende', 1, true, now(), now()),
        (gen_random_uuid(), 'game_consoles', 'display_output', 'Display output working', 'Salida de video funcional', 2, true, now(), now()),
        (gen_random_uuid(), 'game_consoles', 'disc_drive', 'Disc drive functional', 'Unidad de disco funcional', 3, true, now(), now()),
        (gen_random_uuid(), 'game_consoles', 'controllers', 'Controllers connect', 'Controles se conectan', 4, true, now(), now()),
        (gen_random_uuid(), 'game_consoles', 'wifi', 'WiFi working', 'WiFi funciona', 5, true, now(), now()),
        (gen_random_uuid(), 'game_consoles', 'fans_cooling', 'Fans/cooling working', 'Ventiladores/refrigeración funciona', 6, true, now(), now()),
        -- Tablets (similar to phones)
        (gen_random_uuid(), 'tablets', 'powers_on', 'Device powers on', 'El dispositivo enciende', 1, true, now(), now()),
        (gen_random_uuid(), 'tablets', 'screen_condition', 'Screen displays correctly', 'La pantalla muestra correctamente', 2, true, now(), now()),
        (gen_random_uuid(), 'tablets', 'touch_responsive', 'Touch screen responsive', 'Pantalla táctil responde', 3, true, now(), now()),
        (gen_random_uuid(), 'tablets', 'charging_port', 'Charging port functional', 'Puerto de carga funcional', 4, true, now(), now()),
        (gen_random_uuid(), 'tablets', 'buttons_work', 'Physical buttons work', 'Botones físicos funcionan', 5, true, now(), now()),
        (gen_random_uuid(), 'tablets', 'cameras', 'Cameras functional', 'Cámaras funcionan', 6, true, now(), now()),
        (gen_random_uuid(), 'tablets', 'wifi_bluetooth', 'WiFi/Bluetooth working', 'WiFi/Bluetooth funciona', 7, true, now(), now()),
        -- Smartwatches
        (gen_random_uuid(), 'smartwatches', 'powers_on', 'Device powers on', 'El dispositivo enciende', 1, true, now(), now()),
        (gen_random_uuid(), 'smartwatches', 'screen_condition', 'Screen displays correctly', 'La pantalla muestra correctamente', 2, true, now(), now()),
        (gen_random_uuid(), 'smartwatches', 'charging', 'Charges correctly', 'Carga correctamente', 3, true, now(), now()),
        (gen_random_uuid(), 'smartwatches', 'heart_rate', 'Heart rate sensor works', 'Sensor de ritmo cardíaco funciona', 4, true, now(), now()),
        (gen_random_uuid(), 'smartwatches', 'buttons_crown', 'Buttons/crown functional', 'Botones/corona funcionales', 5, true, now(), now()),
        -- Other
        (gen_random_uuid(), 'other', 'powers_on', 'Device powers on', 'El dispositivo enciende', 1, true, now(), now()),
        (gen_random_uuid(), 'other', 'basic_function', 'Basic function works', 'Función básica funciona', 2, true, now(), now()),
        (gen_random_uuid(), 'other', 'physical_condition', 'Physical condition noted', 'Condición física registrada', 3, true, now(), now())
    """)


def downgrade():
    op.drop_table("service_part_links")
    op.drop_table("device_precheck_templates")

    with op.batch_alter_table("repair_services") as batch_op:
        batch_op.drop_column("labour_price")
        batch_op.drop_column("service_code")

    with op.batch_alter_table("devices") as batch_op:
        batch_op.drop_column("imei_lookup_data")
        batch_op.drop_column("unlock_notes")
        batch_op.drop_column("unlock_value_encrypted")
        batch_op.drop_column("unlock_type")
        batch_op.drop_column("device_notes")
        batch_op.drop_column("os_info")
        batch_op.drop_column("gpu")
        batch_op.drop_column("storage_type")
        batch_op.drop_column("ram")
        batch_op.drop_column("cpu")
        batch_op.drop_column("battery_health")
        batch_op.drop_column("cosmetic_condition")
        batch_op.drop_column("fmi_status")
        batch_op.drop_column("carrier_lock")
        batch_op.drop_column("color")
        batch_op.drop_column("storage")
