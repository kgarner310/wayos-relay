"""Unit tests for the deterministic classification engine."""
import pytest

from app.models import IntentCategory
from app.parser import parse_message


# ---------- COI ----------

class TestCOI:
    def test_coi_basic(self):
        result = parse_message(
            "I need a certificate of insurance for a new contract. Policy BOP-2024-4471.",
            sender="john@acme.com",
        )
        assert result.intent == IntentCategory.coi
        assert result.entities.get("policy_number") == "BOP-2024-4471"
        assert result.confidence_score > 40

    def test_coi_additional_insured(self):
        result = parse_message(
            "Please add Apex Construction as additional insured on our COI. "
            "We also need a waiver of subrogation.",
            sender="sarah@bigbiz.com",
        )
        assert result.intent == IntentCategory.coi
        assert "certificate_holder" in result.entities

    def test_coi_with_urgency(self):
        result = parse_message(
            "Need COI ASAP — contract deadline is tomorrow!",
            subject="URGENT COI Request",
            sender="boss@company.com",
        )
        assert result.intent == IntentCategory.coi
        assert result.urgency_score >= 60  # "asap" + "tomorrow" + "deadline"


# ---------- Vehicle Add ----------

class TestVehicleAdd:
    def test_vehicle_with_vin(self):
        result = parse_message(
            "I just bought a new truck. 2024 Ford F-150, "
            "VIN 1FTFW1E50NFA12345. Policy WC-88231.",
            sender="+15559876543",
        )
        assert result.intent == IntentCategory.vehicle_add
        assert result.entities.get("vin") == "1FTFW1E50NFA12345"
        assert result.entities.get("policy_number") == "WC-88231"
        assert result.confidence_score >= 60  # keyword + VIN entity (may have ambiguity penalty)

    def test_vehicle_no_vin(self):
        result = parse_message(
            "I need to add vehicle to my policy. Just purchased a 2024 Honda Civic.",
            sender="buyer@email.com",
        )
        assert result.intent == IntentCategory.vehicle_add
        assert result.confidence_score >= 40  # keyword only, no VIN


# ---------- Driver Add ----------

class TestDriverAdd:
    def test_driver_with_details(self):
        result = parse_message(
            "Need to add driver Carlos Rodriguez, DOB 03/15/1990, "
            "license TX-12345678 to our fleet policy. He starts tomorrow!!",
            sender="+15551112222",
        )
        assert result.intent == IntentCategory.driver_add
        assert result.entities.get("dob") == "03/15/1990"
        assert result.entities.get("drivers_license") == "TX-12345678"
        assert result.urgency_score >= 60  # "tomorrow" + "!!"

    def test_driver_minimal(self):
        result = parse_message(
            "Hi, I hired a new driver and need to add them to my insurance.",
            sender="fleet@company.com",
        )
        assert result.intent == IntentCategory.driver_add


# ---------- Address Change ----------

class TestAddressChange:
    def test_address_with_details(self):
        result = parse_message(
            "We moved to a new address: 456 Oak Ave, Floor 3, Dallas TX 75202. "
            "Policy GL-2023-8899.",
            subject="Address change for policy",
            sender="sarah.jones@bigbiz.com",
        )
        assert result.intent == IntentCategory.address_change
        assert result.entities.get("policy_number") == "GL-2023-8899"
        assert "address" in result.entities

    def test_garaging_address(self):
        result = parse_message(
            "Please update the garaging address on my auto policy to "
            "789 Main St, Austin TX 78701.",
            sender="driver@fleet.com",
        )
        assert result.intent == IntentCategory.address_change


# ---------- Payroll / WC ----------

class TestPayrollChange:
    def test_payroll_with_amounts(self):
        result = parse_message(
            "Our total payroll has increased from $2.1M to $2.8M due to new hires. "
            "Policy: WC-2024-1122. Please update for the workers comp audit.",
            sender="hr@techstartup.io",
        )
        assert result.intent == IntentCategory.payroll_change
        assert "dollar_amounts" in result.entities
        assert result.entities.get("policy_number") == "WC-2024-1122"

    def test_subcontractor_1099(self):
        result = parse_message(
            "We added three new 1099 subcontractor crews. Need to update our "
            "workers comp class code allocations for the audit.",
            sender="ops@construction.com",
        )
        assert result.intent == IntentCategory.payroll_change


# ---------- Coverage Change ----------

class TestCoverageChange:
    def test_increase_limits(self):
        result = parse_message(
            "I need to increase limits on our general liability from $1M to $2M "
            "per occurrence. Policy GL-2024-5567.",
            sender="bob@wilsonplumbing.com",
        )
        assert result.intent == IntentCategory.coverage_change
        assert result.entities.get("policy_number") == "GL-2024-5567"
        assert "dollar_amounts" in result.entities

    def test_add_umbrella(self):
        result = parse_message(
            "We need to add umbrella coverage for the upcoming contract. "
            "Can you provide a quote?",
            sender="cfo@bigco.com",
        )
        assert result.intent == IntentCategory.coverage_change


# ---------- Other / Fallback ----------

class TestOther:
    def test_general_inquiry(self):
        result = parse_message(
            "Hi, I was in a fender bender this morning. Not sure what to do. "
            "Can someone call me back?",
            sender="+15553334444",
        )
        assert result.intent == IntentCategory.other
        assert result.confidence_score <= 30  # low for "other"


# ---------- Urgency scoring ----------

class TestUrgency:
    def test_baseline_urgency(self):
        result = parse_message(
            "Please send me a copy of my policy when you get a chance.",
            sender="patient@example.com",
        )
        assert result.urgency_score == 30  # baseline

    def test_asap_urgency(self):
        result = parse_message(
            "I need this ASAP — deadline is Friday!",
            sender="rush@example.com",
        )
        assert result.urgency_score >= 60

    def test_jobsite_context(self):
        result = parse_message(
            "Need COI for the jobsite. General contractor requires it.",
            sender="gc@build.com",
        )
        assert result.urgency_score >= 40  # "jobsite" context boost

    def test_max_urgency(self):
        result = parse_message(
            "URGENT!! Need this today ASAP for the jobsite permit closing!!",
            sender="panic@example.com",
        )
        assert result.urgency_score >= 70


# ---------- Confidence scoring ----------

class TestConfidence:
    def test_high_confidence_with_entity(self):
        """Strong keyword + extracted entity = high confidence."""
        result = parse_message(
            "Need to add vehicle VIN 1FTFW1E50NFA12345 to policy BOP-2024-001.",
            sender="client@example.com",
        )
        assert result.intent == IntentCategory.vehicle_add
        assert result.confidence_score >= 70

    def test_lower_confidence_no_entity(self):
        """Keyword match but no supporting entity = moderate confidence."""
        result = parse_message(
            "I think I need to add coverage or something. Not sure.",
            sender="confused@example.com",
        )
        assert result.intent == IntentCategory.coverage_change
        assert result.confidence_score < 70

    def test_other_is_low_confidence(self):
        result = parse_message(
            "Hello, just checking in about my account.",
            sender="hello@example.com",
        )
        assert result.intent == IntentCategory.other
        assert result.confidence_score <= 25


# ---------- Entity extraction ----------

class TestEntityExtraction:
    def test_name_from_signature(self):
        result = parse_message(
            "Please send me a COI.\n\nThanks,\nJohn Smith",
            sender="john@example.com",
        )
        assert result.entities.get("customer_name") == "John Smith"

    def test_name_fallback_from_email(self):
        result = parse_message(
            "Need a COI please.",
            sender="jane.doe@company.com",
        )
        assert result.entities.get("customer_name") == "Jane Doe"

    def test_policy_number_extraction(self):
        result = parse_message(
            "My policy number is GL-2024-5567. Please update it.",
            sender="client@example.com",
        )
        assert result.entities.get("policy_number") == "GL-2024-5567"
