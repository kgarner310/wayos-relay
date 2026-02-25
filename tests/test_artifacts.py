"""Tests for draft generation and missing info detection."""
import json

import pytest

from app.artifacts import (
    detect_missing_info,
    generate_ams_note,
    generate_carrier_email,
    generate_checklist,
    generate_client_reply,
)
from app.models import IntentCategory


# ======================================================================
# Missing-info detector
# ======================================================================


class TestMissingInfoVehicleAdd:
    """vehicle_add requires VIN OR year/make/model, effective date, garaging."""

    def test_all_missing(self) -> None:
        req, opt = detect_missing_info(IntentCategory.vehicle_add, {})
        labels = req + opt
        assert any("VIN" in l for l in labels)
        assert any("Effective" in l for l in labels)
        assert any("Garaging" in l for l in labels)

    def test_vin_satisfies_identification(self) -> None:
        req, _ = detect_missing_info(
            IntentCategory.vehicle_add,
            {"vin": "1HGCM82633A004352", "effective_date": "03/01/2026", "address": "123 Main St"},
        )
        # VIN present — no identification missing
        assert not any("VIN" in l for l in req)

    def test_ymm_satisfies_identification(self) -> None:
        req, _ = detect_missing_info(
            IntentCategory.vehicle_add,
            {"vehicle_ymm": "2024 Ford F-150", "effective_date": "03/01/2026", "address": "123 Main St"},
        )
        assert not any("VIN" in l for l in req)

    def test_lienholder_is_optional(self) -> None:
        req, opt = detect_missing_info(
            IntentCategory.vehicle_add,
            {"vin": "1HGCM82633A004352", "effective_date": "03/01/2026", "address": "123 Main St"},
        )
        assert len(req) == 0
        assert any("Lienholder" in l for l in opt)


class TestMissingInfoCOI:
    """COI requires cert holder name + address, description of ops."""

    def test_all_missing(self) -> None:
        req, opt = detect_missing_info(IntentCategory.coi, {})
        assert any("Certificate holder name" in l for l in req)
        assert any("Certificate holder address" in l for l in req)
        assert any("Description of operations" in l for l in req)

    def test_ai_waiver_pnc_optional(self) -> None:
        entities = {
            "certificate_holder": "ABC Corp",
            "holder_address": "123 Main St",
            "description_of_ops": "General contracting",
        }
        req, opt = detect_missing_info(IntentCategory.coi, entities)
        assert len(req) == 0
        labels = [l for l in opt]
        assert any("Additional Insured" in l for l in labels)
        assert any("Waiver" in l for l in labels)
        assert any("Primary" in l for l in labels)


class TestMissingInfoPayroll:
    """Payroll requires amount and effective date, class codes optional."""

    def test_all_missing(self) -> None:
        req, opt = detect_missing_info(IntentCategory.payroll_change, {})
        assert any("payroll" in l.lower() for l in req)
        assert any("Effective" in l for l in req)

    def test_class_codes_optional(self) -> None:
        entities = {"dollar_amounts": ["$50000"], "effective_date": "01/01/2026"}
        req, opt = detect_missing_info(IntentCategory.payroll_change, entities)
        assert len(req) == 0
        assert any("Class code" in l for l in opt)


class TestMissingInfoDriverAdd:
    def test_all_missing(self) -> None:
        req, _ = detect_missing_info(IntentCategory.driver_add, {})
        assert any("legal name" in l.lower() for l in req)
        assert any("Date of birth" in l for l in req)
        assert any("license" in l.lower() for l in req)

    def test_complete(self) -> None:
        entities = {
            "driver_name": "Jane Doe",
            "dob": "05/15/1990",
            "drivers_license": "TX 12345678",
        }
        req, opt = detect_missing_info(IntentCategory.driver_add, entities)
        assert len(req) == 0


class TestMissingInfoOther:
    def test_other_has_no_requirements(self) -> None:
        req, opt = detect_missing_info(IntentCategory.other, {})
        assert len(req) == 0
        assert len(opt) == 0


# ======================================================================
# Client reply generation
# ======================================================================


class TestClientReply:
    def test_includes_name(self) -> None:
        reply = generate_client_reply(
            IntentCategory.coi, "John Smith", "TX-12345", {}
        )
        assert "John Smith" in reply

    def test_fallback_name(self) -> None:
        reply = generate_client_reply(IntentCategory.coi, "", "", {})
        assert "Valued Customer" in reply

    def test_includes_eta(self) -> None:
        reply = generate_client_reply(IntentCategory.coi, "Jane", "", {})
        assert "1 business day" in reply

    def test_includes_missing_info_prompt(self) -> None:
        reply = generate_client_reply(IntentCategory.vehicle_add, "Bob", "", {})
        assert "VIN" in reply
        assert "Garaging" in reply

    def test_no_missing_block_when_complete(self) -> None:
        entities = {
            "vin": "1HGCM82633A004352",
            "effective_date": "03/01/2026",
            "address": "123 Main St",
        }
        reply = generate_client_reply(
            IntentCategory.vehicle_add, "Bob", "TX-123", entities
        )
        assert "To move forward" not in reply

    def test_policy_ref_in_reply(self) -> None:
        reply = generate_client_reply(
            IntentCategory.coi, "Alice", "WC-98765", {}
        )
        assert "WC-98765" in reply

    def test_other_intent_reply(self) -> None:
        reply = generate_client_reply(IntentCategory.other, "Pat", "", {})
        assert "team member will review" in reply
        assert "as soon as possible" in reply


# ======================================================================
# Carrier email generation
# ======================================================================


class TestCarrierEmail:
    def test_subject_line_format_vehicle(self) -> None:
        email = generate_carrier_email(
            IntentCategory.vehicle_add,
            "John Smith",
            "TX-12345",
            "Adding a truck",
            entities={"effective_date": "03/01/2026"},
        )
        assert "Endorsement Request: Add Vehicle" in email
        assert "John Smith" in email
        assert "03/01/2026" in email

    def test_subject_line_coi(self) -> None:
        email = generate_carrier_email(
            IntentCategory.coi, "Alice", "WC-99999", "Need COI", entities={},
        )
        assert "COI Request" in email
        assert "Alice" in email

    def test_includes_extracted_entities(self) -> None:
        entities = {
            "vin": "1HGCM82633A004352",
            "effective_date": "03/01/2026",
        }
        email = generate_carrier_email(
            IntentCategory.vehicle_add, "Bob", "TX-123", "Add vehicle", entities=entities,
        )
        assert "1HGCM82633A004352" in email
        assert "Extracted Details" in email

    def test_includes_missing_checklist(self) -> None:
        email = generate_carrier_email(
            IntentCategory.vehicle_add, "Bob", "TX-123", "Add a truck", entities={},
        )
        assert "Still Pending" in email
        assert "☐" in email

    def test_other_intent_fallback(self) -> None:
        email = generate_carrier_email(
            IntentCategory.other, "Pat", "N/A", "Random question", entities={},
        )
        assert "Subject:" in email
        assert "Service Request" in email

    def test_no_missing_block_when_complete(self) -> None:
        entities = {
            "certificate_holder": "ABC Corp",
            "holder_address": "100 Industrial Way",
            "description_of_ops": "General contracting",
        }
        email = generate_carrier_email(
            IntentCategory.coi, "Alice", "TX-999", "COI request", entities=entities,
        )
        assert "Still Pending" not in email or "Waiver" in email  # optional items only

    def test_all_six_intents_have_templates(self) -> None:
        for intent in IntentCategory:
            email = generate_carrier_email(intent, "Test", "POL-1", "test body", entities={})
            assert "Subject:" in email
            assert len(email) > 50


# ======================================================================
# AMS note generation
# ======================================================================


class TestAMSNote:
    def test_has_timestamp(self) -> None:
        note = generate_ams_note(
            IntentCategory.coi, "Alice", "TX-123", "email", "Need a COI", {},
        )
        assert "UTC" in note
        assert "SERVICE REQUEST" in note

    def test_has_channel(self) -> None:
        note = generate_ams_note(
            IntentCategory.coi, "Alice", "TX-123", "sms", "Need a COI", {},
        )
        assert "Channel: SMS" in note

    def test_has_summary_section(self) -> None:
        note = generate_ams_note(
            IntentCategory.vehicle_add, "Bob", "TX-456", "email",
            "I just bought a new truck", {},
        )
        assert "--- Summary ---" in note
        assert "new truck" in note

    def test_has_action_taken(self) -> None:
        note = generate_ams_note(
            IntentCategory.driver_add, "Carol", "WC-789", "sms",
            "Adding driver Jane Doe", {},
        )
        assert "--- Action Taken ---" in note
        assert "REVIEW" in note

    def test_has_pending_items(self) -> None:
        note = generate_ams_note(
            IntentCategory.vehicle_add, "Dave", "TX-111", "email",
            "Add a vehicle", {},
        )
        assert "--- Pending Items ---" in note
        assert "[REQUIRED]" in note

    def test_pending_all_received(self) -> None:
        entities = {
            "vin": "1HGCM82633A004352",
            "effective_date": "03/01/2026",
            "address": "456 Oak Ave",
        }
        note = generate_ams_note(
            IntentCategory.vehicle_add, "Eve", "TX-222", "email",
            "Add vehicle", entities,
        )
        assert "All required information received" in note

    def test_entities_listed(self) -> None:
        entities = {
            "vin": "1HGCM82633A004352",
            "effective_date": "03/01/2026",
        }
        note = generate_ams_note(
            IntentCategory.vehicle_add, "Frank", "TX-333", "email",
            "Add vehicle", entities,
        )
        assert "--- Extracted Entities ---" in note
        assert "1HGCM82633A004352" in note


# ======================================================================
# Checklist generation
# ======================================================================


class TestChecklist:
    def test_returns_valid_json(self) -> None:
        result = generate_checklist(IntentCategory.coi)
        items = json.loads(result)
        assert isinstance(items, list)
        assert len(items) > 0

    def test_vehicle_checklist_items(self) -> None:
        items = json.loads(generate_checklist(IntentCategory.vehicle_add, {}))
        combined = " ".join(items).lower()
        assert "vin" in combined
        assert "garaging" in combined
        assert "carrier" in combined

    def test_missing_info_prepended(self) -> None:
        # No entities → missing items added to front
        items = json.loads(generate_checklist(IntentCategory.vehicle_add, {}))
        assert any("Request from insured" in i for i in items)

    def test_no_extra_items_when_complete(self) -> None:
        entities = {
            "vin": "1HGCM82633A004352",
            "effective_date": "03/01/2026",
            "address": "123 Main St",
        }
        items = json.loads(generate_checklist(IntentCategory.vehicle_add, entities))
        assert not any("Request from insured" in i for i in items)

    def test_all_intents_have_checklists(self) -> None:
        for intent in IntentCategory:
            items = json.loads(generate_checklist(intent))
            assert len(items) >= 2
