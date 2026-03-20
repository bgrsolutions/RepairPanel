"""Phase 18.5.1 tests: IMEI Regression Fix, Rich Field Mapping Restore,
and Unified Pre-Repair Checklist Alignment.

Tests cover:
  - Primary Apple lookup: serial, storage, color restored
  - Secondary FMI/carrier/blacklist/warranty parsing success
  - Broadened _parse_response success criteria
  - merge_results logic (preserves base, merges useful extras)
  - cache_lookup_result core + extended field persistence
  - Unified checklist alignment (DEFAULT_CHECKLISTS == _FALLBACK_CHECKS)
  - Structured checklist carry-through intake → ticket
  - Post-repair checklist alignment
"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Unit tests: _parse_response broadened success criteria
# ---------------------------------------------------------------------------

class TestParseResponseSuccessCriteria:
    """Verify _parse_response accepts narrow secondary check results."""

    def test_brand_model_only(self):
        from app.services.imei_lookup_service import _parse_response
        data = {"properties": {"brand": "Apple", "modelName": "iPhone 14"}}
        result = _parse_response("353456789012345", data)
        assert result.success is True
        assert result.brand == "Apple"
        assert result.model == "iPhone 14"

    def test_fmi_only_succeeds(self):
        """A narrow FMI check returning only fmi_status should succeed."""
        from app.services.imei_lookup_service import _parse_response
        data = {"properties": {"findMyIphone": "ON"}}
        result = _parse_response("353456789012345", data)
        assert result.success is True
        assert result.fmi_status != ""

    def test_carrier_only_succeeds(self):
        from app.services.imei_lookup_service import _parse_response
        data = {"properties": {"simLock": "Locked", "carrier": "AT&T"}}
        result = _parse_response("353456789012345", data)
        assert result.success is True
        assert result.carrier_lock != ""

    def test_blacklist_only_succeeds(self):
        from app.services.imei_lookup_service import _parse_response
        data = {"properties": {"blacklistStatus": "Clean"}}
        result = _parse_response("353456789012345", data)
        assert result.success is True
        assert result.blacklist_status != ""

    def test_warranty_only_succeeds(self):
        from app.services.imei_lookup_service import _parse_response
        data = {"properties": {"warrantyStatus": "Active"}}
        result = _parse_response("353456789012345", data)
        assert result.success is True
        assert result.warranty_status == "Active"

    def test_serial_storage_color_restored(self):
        """Primary Apple lookup: serial, storage, color populated."""
        from app.services.imei_lookup_service import _parse_response
        data = {"properties": {
            "brand": "Apple",
            "modelName": "iPhone 14 Pro",
            "serial": "DNQXYZ123456",
            "internalMemory": "256GB",
            "color": "Space Black",
            "simLock": "Unlocked",
            "findMyIphone": "OFF",
        }}
        result = _parse_response("353456789012345", data)
        assert result.success is True
        assert result.serial_number == "DNQXYZ123456"
        assert result.storage == "256GB"
        assert result.color == "Space Black"
        assert result.brand == "Apple"
        assert result.model == "iPhone 14 Pro"
        assert result.fields_populated >= 7

    def test_empty_properties_fails(self):
        from app.services.imei_lookup_service import _parse_response
        data = {"properties": {}}
        result = _parse_response("353456789012345", data)
        assert result.success is False
        assert result.error is not None

    def test_no_properties_key_fails(self):
        from app.services.imei_lookup_service import _parse_response
        data = {"status": "error"}
        result = _parse_response("353456789012345", data)
        assert result.success is False

    def test_purchase_country_only_succeeds(self):
        from app.services.imei_lookup_service import _parse_response
        data = {"properties": {"purchaseCountry": "United States"}}
        result = _parse_response("353456789012345", data)
        assert result.success is True
        assert result.purchase_country == "United States"

    def test_activation_status_only_succeeds(self):
        from app.services.imei_lookup_service import _parse_response
        data = {"properties": {"activationStatus": "Activated"}}
        result = _parse_response("353456789012345", data)
        assert result.success is True
        assert result.activation_status == "Activated"

    def test_extended_apple_fields(self):
        """Phase 18.5 richer fields: imei2, eid, applecare, etc."""
        from app.services.imei_lookup_service import _parse_response
        data = {"properties": {
            "brand": "Apple",
            "modelName": "iPhone 15 Pro",
            "imei2": "354567890123456",
            "eid": "EID123456",
            "modelNumber": "MU7T3LL/A",
            "activationStatus": "Activated",
            "purchaseCountry": "US",
            "appleCareEligible": "Yes",
            "technicalSupportStatus": "Active",
            "soldBy": "Apple Store",
            "productionDate": "2024-01",
            "buyerCode": "BC123",
        }}
        result = _parse_response("353456789012345", data)
        assert result.success is True
        assert result.imei2 == "354567890123456"
        assert result.eid == "EID123456"
        assert result.model_number == "MU7T3LL/A"
        assert result.applecare_eligible == "Yes"
        assert result.technical_support == "Active"
        assert result.sold_by == "Apple Store"
        assert result.production_date == "2024-01"
        assert result.buyer_code == "BC123"


# ---------------------------------------------------------------------------
# Unit tests: merge_results
# ---------------------------------------------------------------------------

class TestMergeResults:
    """Verify merge_results correctly merges extras into base."""

    def test_merges_fmi_into_base(self):
        from app.services.imei_lookup_service import IMEILookupResult, merge_results
        base = IMEILookupResult(success=True, brand="Apple", model="iPhone 14")
        extra = IMEILookupResult(success=True, fmi_status="OFF")
        merged = merge_results(base, extra)
        assert merged.fmi_status == "OFF"
        assert merged.brand == "Apple"  # base preserved

    def test_does_not_overwrite_base_values(self):
        from app.services.imei_lookup_service import IMEILookupResult, merge_results
        base = IMEILookupResult(success=True, brand="Apple", model="iPhone 14")
        extra = IMEILookupResult(success=True, brand="Samsung", model="Galaxy")
        merged = merge_results(base, extra)
        assert merged.brand == "Apple"
        assert merged.model == "iPhone 14"

    def test_merges_unsuccessful_extra_with_data(self):
        """Key regression fix: merge should work even when extra.success=False."""
        from app.services.imei_lookup_service import IMEILookupResult, merge_results
        base = IMEILookupResult(success=True, brand="Apple")
        extra = IMEILookupResult(success=False, blacklist_status="Clean",
                                  error="IMEI lookup returned no device details")
        merged = merge_results(base, extra)
        assert merged.blacklist_status == "Clean"
        assert merged.success is True  # base stays successful

    def test_skips_empty_extra(self):
        from app.services.imei_lookup_service import IMEILookupResult, merge_results
        base = IMEILookupResult(success=True, brand="Apple")
        extra = IMEILookupResult(success=False)
        merged = merge_results(base, extra)
        assert merged.brand == "Apple"

    def test_upgrades_base_success_when_merging(self):
        """If base.success=False but merge brings data, auto-upgrade."""
        from app.services.imei_lookup_service import IMEILookupResult, merge_results
        base = IMEILookupResult(success=False, error="No data")
        extra = IMEILookupResult(success=True, brand="Apple", model="iPhone 14",
                                  warranty_status="Active")
        merged = merge_results(base, extra)
        assert merged.success is True
        assert merged.error is None
        assert merged.brand == "Apple"

    def test_recounts_fields_after_merge(self):
        from app.services.imei_lookup_service import IMEILookupResult, merge_results
        base = IMEILookupResult(success=True, brand="Apple", fields_populated=1)
        extra = IMEILookupResult(success=True, warranty_status="Active",
                                  purchase_country="US")
        merged = merge_results(base, extra)
        # brand(1) + warranty(1) + country(1) = 3
        assert merged.fields_populated >= 3


# ---------------------------------------------------------------------------
# Unit tests: cache_lookup_result
# ---------------------------------------------------------------------------

class TestCacheLookupResult:
    """Verify cache_lookup_result persists both core and extended fields."""

    def test_core_fields_persisted(self):
        from app.services.imei_lookup_service import IMEILookupResult, cache_lookup_result
        device = MagicMock()
        device.brand = ""
        device.model = ""
        device.serial_number = ""
        device.storage = ""
        device.color = ""
        device.carrier_lock = ""
        device.fmi_status = ""
        device.imei_lookup_data = None
        device.last_lookup_at = None

        result = IMEILookupResult(
            success=True,
            brand="Apple",
            model="iPhone 14 Pro",
            serial_number="DNQXYZ123456",
            storage="256GB",
            color="Space Black",
            carrier_lock="Unlocked",
            fmi_status="OFF",
            raw_data={"test": True},
        )
        cache_lookup_result(device, result)

        assert device.brand == "Apple"
        assert device.model == "iPhone 14 Pro"
        assert device.serial_number == "DNQXYZ123456"
        assert device.storage == "256GB"
        assert device.color == "Space Black"
        assert device.carrier_lock == "Unlocked"
        assert device.fmi_status == "OFF"
        assert device.last_lookup_at is not None

    def test_extended_fields_persisted(self):
        from app.services.imei_lookup_service import IMEILookupResult, cache_lookup_result
        device = MagicMock()
        device.imei_lookup_data = None
        device.last_lookup_at = None

        result = IMEILookupResult(
            success=True,
            imei2="354567890123456",
            model_number="MU7T3LL/A",
            purchase_country="US",
            warranty_status="Active",
            blacklist_status="Clean",
            activation_status="Activated",
            applecare_eligible="Yes",
            technical_support="Active",
            sold_by="Apple Store",
            production_date="2024-01",
            buyer_code="BC123",
            eid="EID123",
        )
        cache_lookup_result(device, result)

        assert device.imei2 == "354567890123456"
        assert device.model_number == "MU7T3LL/A"
        assert device.purchase_country == "US"
        assert device.warranty_status == "Active"
        assert device.blacklist_status == "Clean"
        assert device.activation_status == "Activated"
        assert device.applecare_eligible == "Yes"
        assert device.eid == "EID123"

    def test_does_not_blank_existing_values(self):
        """cache_lookup_result should never overwrite with empty strings."""
        from app.services.imei_lookup_service import IMEILookupResult, cache_lookup_result
        device = MagicMock()
        device.brand = "Apple"
        device.model = "iPhone 14"
        device.serial_number = "EXISTING"
        device.imei_lookup_data = None
        device.last_lookup_at = None

        result = IMEILookupResult(success=True, brand="", model="", serial_number="")
        cache_lookup_result(device, result)

        # Existing values preserved — empty result shouldn't blank them
        assert device.brand == "Apple"
        assert device.model == "iPhone 14"
        assert device.serial_number == "EXISTING"


# ---------------------------------------------------------------------------
# Unit tests: Unified checklist alignment
# ---------------------------------------------------------------------------

class TestChecklistAlignment:
    """Verify DEFAULT_CHECKLISTS pre_repair labels match _FALLBACK_CHECKS."""

    def test_phones_checklist_matches_fallback(self):
        from app.models.checklist import DEFAULT_CHECKLISTS
        from app.services.precheck_service import _FALLBACK_CHECKS
        dc_labels = DEFAULT_CHECKLISTS["phones"]["pre_repair"]
        fb_labels = [item[1] for item in _FALLBACK_CHECKS["phones"]]
        assert dc_labels == fb_labels

    def test_tablets_checklist_matches_fallback(self):
        from app.models.checklist import DEFAULT_CHECKLISTS
        from app.services.precheck_service import _FALLBACK_CHECKS
        dc_labels = DEFAULT_CHECKLISTS["tablets"]["pre_repair"]
        fb_labels = [item[1] for item in _FALLBACK_CHECKS["tablets"]]
        assert dc_labels == fb_labels

    def test_laptops_checklist_matches_fallback(self):
        from app.models.checklist import DEFAULT_CHECKLISTS
        from app.services.precheck_service import _FALLBACK_CHECKS
        dc_labels = DEFAULT_CHECKLISTS["laptops"]["pre_repair"]
        fb_labels = [item[1] for item in _FALLBACK_CHECKS["laptops"]]
        assert dc_labels == fb_labels

    def test_desktops_checklist_matches_fallback(self):
        from app.models.checklist import DEFAULT_CHECKLISTS
        from app.services.precheck_service import _FALLBACK_CHECKS
        dc_labels = DEFAULT_CHECKLISTS["desktops"]["pre_repair"]
        fb_labels = [item[1] for item in _FALLBACK_CHECKS["desktops"]]
        assert dc_labels == fb_labels

    def test_game_consoles_checklist_matches_fallback(self):
        from app.models.checklist import DEFAULT_CHECKLISTS
        from app.services.precheck_service import _FALLBACK_CHECKS
        dc_labels = DEFAULT_CHECKLISTS["game_consoles"]["pre_repair"]
        fb_labels = [item[1] for item in _FALLBACK_CHECKS["game_consoles"]]
        assert dc_labels == fb_labels

    def test_smartwatches_checklist_matches_fallback(self):
        from app.models.checklist import DEFAULT_CHECKLISTS
        from app.services.precheck_service import _FALLBACK_CHECKS
        dc_labels = DEFAULT_CHECKLISTS["smartwatches"]["pre_repair"]
        fb_labels = [item[1] for item in _FALLBACK_CHECKS["smartwatches"]]
        assert dc_labels == fb_labels

    def test_other_checklist_matches_fallback(self):
        from app.models.checklist import DEFAULT_CHECKLISTS
        from app.services.precheck_service import _FALLBACK_CHECKS
        dc_labels = DEFAULT_CHECKLISTS["other"]["pre_repair"]
        fb_labels = [item[1] for item in _FALLBACK_CHECKS["other"]]
        assert dc_labels == fb_labels

    def test_all_categories_present_in_both(self):
        """Every category in _FALLBACK_CHECKS has a matching DEFAULT_CHECKLISTS entry."""
        from app.models.checklist import DEFAULT_CHECKLISTS
        from app.services.precheck_service import _FALLBACK_CHECKS
        for cat in _FALLBACK_CHECKS:
            assert cat in DEFAULT_CHECKLISTS, f"Missing category: {cat}"
            assert "pre_repair" in DEFAULT_CHECKLISTS[cat]
            assert "post_repair" in DEFAULT_CHECKLISTS[cat]

    def test_item_counts_match(self):
        """Count of pre_repair items must match for every category."""
        from app.models.checklist import DEFAULT_CHECKLISTS
        from app.services.precheck_service import _FALLBACK_CHECKS
        for cat in _FALLBACK_CHECKS:
            dc_count = len(DEFAULT_CHECKLISTS[cat]["pre_repair"])
            fb_count = len(_FALLBACK_CHECKS[cat])
            assert dc_count == fb_count, (
                f"{cat}: DEFAULT_CHECKLISTS has {dc_count} items, "
                f"_FALLBACK_CHECKS has {fb_count}"
            )


# ---------------------------------------------------------------------------
# Integration tests: Structured checklist carry-through
# ---------------------------------------------------------------------------

class TestChecklistCarryThrough:
    """Test that intake pre-checks carry through to ticket checklist."""

    def _get_app_and_ids(self, monkeypatch):
        """Set up test app, DB tables, and seed data."""
        monkeypatch.setattr('app.services.auth_service.log_action', lambda *a, **kw: None)
        monkeypatch.setattr('app.services.audit_service.log_action', lambda *a, **kw: None)
        monkeypatch.setattr('app.blueprints.intake.routes.log_action', lambda *a, **kw: None)
        monkeypatch.setattr('app.blueprints.tickets.routes.log_action', lambda *a, **kw: None)
        monkeypatch.setattr('app.services.booking_service.log_action', lambda *a, **kw: None)
        monkeypatch.setattr('app.blueprints.bookings.routes.log_action', lambda *a, **kw: None)

        from app import create_app
        from app.extensions import db
        from app.models import (
            Branch, Company, Customer, Device, Role, User,
            AppSetting, RepairChecklist, ChecklistItem, Ticket,
            IntakeSubmission, PortalToken, Diagnostic, Quote,
            QuoteOption, QuoteLine, QuoteApproval, TicketNote,
            Supplier, Part, PartCategory, PartOrder, PartOrderLine,
            PartOrderEvent, StockLocation, StockLevel, StockMovement,
            StockReservation, StockLayer, RepairService, Booking,
            DevicePreCheckTemplate, IntakeDisclaimerAcceptance,
            service_part_links,
        )
        from app.models.intake import IntakeSignature, Attachment
        from app.models.role import role_permissions
        from app.models.user import user_roles, user_branch_access
        from app.models.inventory import part_category_links

        class TestCfg:
            TESTING = True
            SECRET_KEY = "test-secret-key"
            SQLALCHEMY_DATABASE_URI = "sqlite://"
            WTF_CSRF_ENABLED = False
            SERVER_NAME = "localhost"
            DEFAULT_TICKET_SLA_DAYS = 5
            DEFAULT_IGIC_RATE = 0.07
            SUPPORTED_LOCALES = ["en", "es"]
            BABEL_DEFAULT_LOCALE = "en"
            BABEL_DEFAULT_TIMEZONE = "UTC"
            MAIL_TRANSPORT = "log"
            DEFAULT_INTAKE_DISCLAIMER_TEXT = "Test disclaimer"
            IMEICHECK_API_KEY = ""
            IMEICHECK_ENABLED = False
            IMEICHECK_SERIAL_LOOKUP_BRANDS = ["apple", "samsung"]

        app = create_app(TestCfg)
        with app.app_context():
            tables = [
                Company.__table__, Branch.__table__, Role.__table__, Customer.__table__,
                User.__table__, role_permissions, user_roles, user_branch_access,
                Device.__table__, Ticket.__table__, IntakeSubmission.__table__,
                IntakeDisclaimerAcceptance.__table__, IntakeSignature.__table__,
                Attachment.__table__, PortalToken.__table__,
                Diagnostic.__table__, Quote.__table__, QuoteOption.__table__,
                QuoteLine.__table__, QuoteApproval.__table__, TicketNote.__table__,
                Supplier.__table__, PartCategory.__table__, part_category_links,
                Part.__table__, StockLocation.__table__, StockLevel.__table__,
                StockMovement.__table__, StockReservation.__table__, StockLayer.__table__,
                PartOrder.__table__, PartOrderLine.__table__, PartOrderEvent.__table__,
                AppSetting.__table__, RepairChecklist.__table__, ChecklistItem.__table__,
                RepairService.__table__, Booking.__table__,
                DevicePreCheckTemplate.__table__, service_part_links,
            ]
            for t in tables:
                t.create(bind=db.engine, checkfirst=True)
            role = Role(name="Admin")
            db.session.add(role)
            branch = Branch(code="HQ", name="HQ", is_active=True)
            db.session.add(branch)
            db.session.flush()
            user = User(full_name="Tester", email="t@t.com", is_active=True,
                        default_branch_id=branch.id)
            user.password_hash = "pbkdf2:sha256:600000$x$x"
            user.roles.append(role)
            db.session.add(user)
            customer = Customer(full_name="Jane Doe", phone="555-9999",
                                email="j@e.com", primary_branch_id=branch.id)
            db.session.add(customer)
            db.session.flush()
            device = Device(customer_id=customer.id, category="phones",
                            brand="Apple", model="iPhone 14")
            db.session.add(device)
            db.session.flush()
            ids = {
                "branch_id": branch.id,
                "user_id": str(user.id),
                "customer_id": customer.id,
                "device_id": device.id,
            }
            db.session.commit()

        client = app.test_client()
        with client.session_transaction() as sess:
            sess['_user_id'] = ids["user_id"]
        return app, client, ids, db

    def test_intake_conversion_creates_unified_checklist(self, monkeypatch):
        """When intake is converted to ticket, the pre-repair checklist
        uses DEFAULT_CHECKLISTS items (same family as intake)."""
        app, client, ids, database = self._get_app_and_ids(monkeypatch)
        from app.models import IntakeSubmission, RepairChecklist
        from app.models.checklist import DEFAULT_CHECKLISTS

        with app.app_context():
            # Create intake with precheck data (3 of 10 phone items passed)
            precheck_data = json.dumps([
                {"check_key": "powers_on", "label": "Device powers on", "passed": True},
                {"check_key": "screen_condition", "label": "Screen displays correctly", "passed": True},
                {"check_key": "touch_responsive", "label": "Touch screen responsive", "passed": False},
                {"check_key": "charging_port", "label": "Charging port functional", "passed": True},
                {"check_key": "buttons_work", "label": "Physical buttons work", "passed": False},
            ])
            intake = IntakeSubmission(
                reference="INT-CARRY-001",
                customer_id=ids["customer_id"],
                device_id=ids["device_id"],
                branch_id=ids["branch_id"],
                status="pending",
                category="phones",
                customer_name="Jane Doe",
                device_brand="Apple",
                device_model="iPhone 14",
                reported_fault="Screen cracked",
                precheck_data=precheck_data,
            )
            database.session.add(intake)
            database.session.commit()
            intake_id = intake.id

        # Convert intake to ticket
        resp = client.post(f"/intake/{intake_id}/convert", data={
            "csrf_token": "",
        }, follow_redirects=False)
        # Should redirect to ticket detail
        assert resp.status_code in (302, 200)

        with app.app_context():
            intake = database.session.get(IntakeSubmission, intake_id)
            assert intake.status == "converted"
            ticket_id = intake.converted_ticket_id
            assert ticket_id is not None

            # Find the pre-repair checklist
            checklist = RepairChecklist.query.filter_by(
                ticket_id=ticket_id, checklist_type="pre_repair"
            ).first()
            assert checklist is not None
            assert checklist.device_category == "phones"

            # Items should match DEFAULT_CHECKLISTS phones pre_repair
            expected_labels = DEFAULT_CHECKLISTS["phones"]["pre_repair"]
            actual_labels = [item.label for item in checklist.items]
            assert actual_labels == expected_labels

            # Intake-checked items should carry through
            checked = {item.label for item in checklist.items if item.is_checked}
            assert "Device powers on" in checked
            assert "Screen displays correctly" in checked
            assert "Charging port functional" in checked
            assert "Touch screen responsive" not in checked
            assert "Physical buttons work" not in checked


# ---------------------------------------------------------------------------
# Unit tests: Post-repair checklists exist for all categories
# ---------------------------------------------------------------------------

class TestPostRepairChecklists:
    """Verify post-repair checklists exist and are non-empty."""

    def test_all_categories_have_post_repair(self):
        from app.models.checklist import DEFAULT_CHECKLISTS
        for cat, data in DEFAULT_CHECKLISTS.items():
            assert "post_repair" in data, f"{cat} missing post_repair"
            assert len(data["post_repair"]) > 0, f"{cat} has empty post_repair"

    def test_post_repair_items_are_strings(self):
        from app.models.checklist import DEFAULT_CHECKLISTS
        for cat, data in DEFAULT_CHECKLISTS.items():
            for item in data["post_repair"]:
                assert isinstance(item, str), f"{cat}: {item} is not a string"
                assert len(item) > 0


# ---------------------------------------------------------------------------
# Unit tests: brand-aware service routing
# ---------------------------------------------------------------------------

class TestBrandRouting:
    """Verify secondary service config and routing."""

    def test_get_secondary_services_returns_config(self):
        from app.services.imei_lookup_service import get_secondary_services
        from app import create_app

        class Cfg:
            TESTING = True
            SECRET_KEY = "x"
            SQLALCHEMY_DATABASE_URI = "sqlite://"
            SUPPORTED_LOCALES = ["en"]
            BABEL_DEFAULT_LOCALE = "en"
            BABEL_DEFAULT_TIMEZONE = "UTC"
            MAIL_TRANSPORT = "log"
            IMEICHECK_SECONDARY_SERVICES = {"fmi": 10, "carrier": 11}

        app = create_app(Cfg)
        with app.app_context():
            result = get_secondary_services()
            assert result["fmi"] == 10
            assert result["carrier"] == 11

    def test_get_secondary_services_empty_when_not_configured(self):
        from app.services.imei_lookup_service import get_secondary_services
        from app import create_app

        class Cfg:
            TESTING = True
            SECRET_KEY = "x"
            SQLALCHEMY_DATABASE_URI = "sqlite://"
            SUPPORTED_LOCALES = ["en"]
            BABEL_DEFAULT_LOCALE = "en"
            BABEL_DEFAULT_TIMEZONE = "UTC"
            MAIL_TRANSPORT = "log"

        app = create_app(Cfg)
        with app.app_context():
            result = get_secondary_services()
            assert result == {}

    def test_secondary_check_returns_error_when_not_configured(self):
        from app.services.imei_lookup_service import secondary_check
        from app import create_app

        class Cfg:
            TESTING = True
            SECRET_KEY = "x"
            SQLALCHEMY_DATABASE_URI = "sqlite://"
            SUPPORTED_LOCALES = ["en"]
            BABEL_DEFAULT_LOCALE = "en"
            BABEL_DEFAULT_TIMEZONE = "UTC"
            MAIL_TRANSPORT = "log"

        app = create_app(Cfg)
        with app.app_context():
            result = secondary_check("353456789012345", "fmi")
            assert result.success is False
            assert "not configured" in result.error.lower()
