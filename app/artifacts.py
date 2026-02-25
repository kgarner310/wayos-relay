"""
Generate draft artifacts for a parsed request:
- client_reply_draft  — acknowledge, confirm needs, ETA, ask for missing info
- carrier_email_draft — subject line, extracted entities, missing-item checklist
- ams_note_draft      — timestamped: channel, summary, action taken, pending
- internal_checklist  — JSON list of action items

Includes a **missing info detector** that checks required entities per category.
"""
import json
from datetime import datetime, timezone

from app.models import IntentCategory


# ======================================================================
# Missing-info detector
# ======================================================================

# Each category maps to a dict of:
#   entity_key -> (label, required?)
# "required?" False means optional but still nice to request.

_REQUIRED_ENTITIES: dict[IntentCategory, list[tuple[str, str, bool]]] = {
    IntentCategory.vehicle_add: [
        ("vin", "VIN (17-character)", True),
        ("vehicle_ymm", "Year / Make / Model", True),  # alternate to VIN
        ("effective_date", "Effective date", True),
        ("address", "Garaging address", True),
        ("lienholder", "Lienholder name & address", False),
    ],
    IntentCategory.coi: [
        ("certificate_holder", "Certificate holder name", True),
        ("holder_address", "Certificate holder address", True),
        ("description_of_ops", "Description of operations", True),
        ("ai_flag", "Additional Insured required (AI)?", False),
        ("waiver_flag", "Waiver of Subrogation required?", False),
        ("pnc_flag", "Primary & Non-Contributory required?", False),
    ],
    IntentCategory.payroll_change: [
        ("dollar_amounts", "Updated payroll amount(s)", True),
        ("class_codes", "Class code(s)", False),
        ("effective_date", "Effective date of change", True),
    ],
    IntentCategory.driver_add: [
        ("driver_name", "Driver full legal name", True),
        ("dob", "Date of birth", True),
        ("drivers_license", "Driver's license number & state", True),
    ],
    IntentCategory.address_change: [
        ("address", "New full address", True),
        ("effective_date", "Effective date of change", True),
    ],
    IntentCategory.coverage_change: [
        ("effective_date", "Effective / requested date", False),
        ("dollar_amounts", "Current or desired limit amounts", False),
    ],
}


def detect_missing_info(
    intent: IntentCategory, entities: dict
) -> tuple[list[str], list[str]]:
    """Return (missing_required, missing_optional) label lists.

    For vehicle_add: VIN **or** year/make/model satisfies the identification
    requirement, so both are only flagged missing if neither is present.
    """
    reqs = _REQUIRED_ENTITIES.get(intent, [])
    missing_required: list[str] = []
    missing_optional: list[str] = []

    for key, label, required in reqs:
        # Special case: vehicle identification — VIN *or* YMM is enough
        if intent == IntentCategory.vehicle_add and key in ("vin", "vehicle_ymm"):
            continue  # handled below
        if key not in entities:
            if required:
                missing_required.append(label)
            else:
                missing_optional.append(label)

    # Vehicle identification: need VIN or YMM
    if intent == IntentCategory.vehicle_add:
        has_vin = "vin" in entities
        has_ymm = "vehicle_ymm" in entities
        if not has_vin and not has_ymm:
            missing_required.append("VIN or Year / Make / Model")

    return missing_required, missing_optional


# ======================================================================
# Helper
# ======================================================================

def _policy_ref(policy_number: str) -> str:
    if policy_number:
        return f" (Policy: {policy_number})"
    return ""


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# ======================================================================
# Client reply drafts
# ======================================================================

_ETA_MAP: dict[IntentCategory, str] = {
    IntentCategory.coi: "within 1 business day",
    IntentCategory.vehicle_add: "within 1–2 business days once we have the details below",
    IntentCategory.driver_add: "within 1–2 business days once we have the details below",
    IntentCategory.address_change: "within 1 business day",
    IntentCategory.payroll_change: "within 2–3 business days",
    IntentCategory.coverage_change: "within 2–3 business days after we review options",
    IntentCategory.other: "as soon as possible",
}

_CLIENT_REPLY_TEMPLATES: dict[IntentCategory, str] = {
    IntentCategory.coi: (
        "Hi {name},\n\n"
        "Thank you for your Certificate of Insurance request{policy_ref}. "
        "We're on it and expect to have your COI ready {eta}.\n\n"
        "{missing_block}"
        "If you have any questions in the meantime, just reply to this message.\n\n"
        "Best regards,\nYour Insurance Team"
    ),
    IntentCategory.vehicle_add: (
        "Hi {name},\n\n"
        "We received your request to add a vehicle to your policy{policy_ref}. "
        "We can get the endorsement submitted {eta}.\n\n"
        "{missing_block}"
        "Once we have everything, we'll submit the change and send you a confirmation.\n\n"
        "Best regards,\nYour Insurance Team"
    ),
    IntentCategory.driver_add: (
        "Hi {name},\n\n"
        "Thanks for letting us know about the new driver. "
        "We can get them added to your policy{policy_ref} {eta}.\n\n"
        "{missing_block}"
        "We appreciate your prompt attention to this.\n\n"
        "Best regards,\nYour Insurance Team"
    ),
    IntentCategory.address_change: (
        "Hi {name},\n\n"
        "We received your address change request{policy_ref}. "
        "We'll have the update processed {eta}.\n\n"
        "{missing_block}"
        "We'll confirm once your records have been updated.\n\n"
        "Best regards,\nYour Insurance Team"
    ),
    IntentCategory.payroll_change: (
        "Hi {name},\n\n"
        "Thank you for the payroll update{policy_ref}. "
        "We'll forward this to your carrier and expect processing {eta}.\n\n"
        "{missing_block}"
        "If you have a current payroll report or breakdown by class code, "
        "please send it along.\n\n"
        "Best regards,\nYour Insurance Team"
    ),
    IntentCategory.coverage_change: (
        "Hi {name},\n\n"
        "We received your coverage change request{policy_ref}. "
        "We'll review the options and get back to you with a quote {eta}.\n\n"
        "{missing_block}"
        "Best regards,\nYour Insurance Team"
    ),
    IntentCategory.other: (
        "Hi {name},\n\n"
        "Thank you for reaching out. We've received your message and "
        "a team member will review it and respond {eta}.\n\n"
        "{missing_block}"
        "Best regards,\nYour Insurance Team"
    ),
}


def _build_missing_block(
    missing_required: list[str], missing_optional: list[str]
) -> str:
    """Format a polite bullet list asking for missing information."""
    if not missing_required and not missing_optional:
        return ""

    lines: list[str] = []
    if missing_required:
        lines.append("To move forward, we'll need the following from you:")
        for item in missing_required:
            lines.append(f"  • {item}")
    if missing_optional:
        if missing_required:
            lines.append("")
            lines.append("If available, the following would also be helpful:")
        else:
            lines.append("If you have the following details handy, they'd help speed things up:")
        for item in missing_optional:
            lines.append(f"  • {item}")
    lines.append("")  # trailing newline
    return "\n".join(lines) + "\n"


def generate_client_reply(
    intent: IntentCategory,
    name: str,
    policy_number: str,
    entities: dict | None = None,
) -> str:
    """Build a professional client-facing reply draft."""
    entities = entities or {}
    template = _CLIENT_REPLY_TEMPLATES.get(
        intent, _CLIENT_REPLY_TEMPLATES[IntentCategory.other]
    )
    eta = _ETA_MAP.get(intent, _ETA_MAP[IntentCategory.other])
    missing_req, missing_opt = detect_missing_info(intent, entities)
    missing_block = _build_missing_block(missing_req, missing_opt)

    return template.format(
        name=name or "Valued Customer",
        policy_ref=_policy_ref(policy_number),
        eta=eta,
        missing_block=missing_block,
    )


# ======================================================================
# Carrier email drafts
# ======================================================================

_CARRIER_SUBJECT_MAP: dict[IntentCategory, str] = {
    IntentCategory.coi: "COI Request – {name} – {policy}",
    IntentCategory.vehicle_add: "Endorsement Request: Add Vehicle – {name} – Effective {eff_date}",
    IntentCategory.driver_add: "Endorsement Request: Add Driver – {name} – Effective {eff_date}",
    IntentCategory.address_change: "Endorsement Request: Address Change – {name} – Effective {eff_date}",
    IntentCategory.payroll_change: "Payroll / Audit Update – {name} – {policy}",
    IntentCategory.coverage_change: "Endorsement Request: Coverage Change – {name} – Effective {eff_date}",
}

_CARRIER_BODY_TEMPLATES: dict[IntentCategory, str] = {
    IntentCategory.coi: (
        "Hi,\n\n"
        "Please issue a Certificate of Insurance for the following insured:\n\n"
        "Insured: {name}\n"
        "Policy: {policy}\n\n"
        "{entities_block}"
        "{missing_block}"
        "Please let us know if you need any additional information.\n\n"
        "Thank you."
    ),
    IntentCategory.vehicle_add: (
        "Hi,\n\n"
        "Please process the following vehicle addition:\n\n"
        "Insured: {name}\n"
        "Policy: {policy}\n\n"
        "{entities_block}"
        "{missing_block}"
        "Please confirm the endorsement and any premium change.\n\n"
        "Thank you."
    ),
    IntentCategory.driver_add: (
        "Hi,\n\n"
        "Please add the following driver to the policy:\n\n"
        "Insured: {name}\n"
        "Policy: {policy}\n\n"
        "{entities_block}"
        "{missing_block}"
        "Please confirm and advise of any premium impact.\n\n"
        "Thank you."
    ),
    IntentCategory.address_change: (
        "Hi,\n\n"
        "Please process the following address change:\n\n"
        "Insured: {name}\n"
        "Policy: {policy}\n\n"
        "{entities_block}"
        "{missing_block}"
        "Please confirm the endorsement.\n\n"
        "Thank you."
    ),
    IntentCategory.payroll_change: (
        "Hi,\n\n"
        "Please update payroll records for the following insured:\n\n"
        "Insured: {name}\n"
        "Policy: {policy}\n\n"
        "{entities_block}"
        "{missing_block}"
        "Please confirm receipt and any premium adjustment.\n\n"
        "Thank you."
    ),
    IntentCategory.coverage_change: (
        "Hi,\n\n"
        "Please provide a quote for the following coverage change:\n\n"
        "Insured: {name}\n"
        "Policy: {policy}\n\n"
        "{entities_block}"
        "{missing_block}"
        "Please advise on options and premium impact.\n\n"
        "Thank you."
    ),
}

# Keys we skip when listing extracted entities (already in header)
_ENTITY_SKIP_KEYS = {"customer_name", "policy_number"}

_ENTITY_LABELS: dict[str, str] = {
    "vin": "VIN",
    "vehicle_ymm": "Year/Make/Model",
    "address": "Address",
    "effective_date": "Effective Date",
    "certificate_holder": "Certificate Holder",
    "holder_address": "Holder Address",
    "description_of_ops": "Description of Ops",
    "ai_flag": "Additional Insured",
    "waiver_flag": "Waiver of Subrogation",
    "pnc_flag": "Primary & Non-Contributory",
    "driver_name": "Driver Name",
    "dob": "Date of Birth",
    "drivers_license": "Driver's License",
    "dollar_amounts": "Dollar Amount(s)",
    "class_codes": "Class Code(s)",
    "lienholder": "Lienholder",
}


def _build_entities_block(entities: dict) -> str:
    """Format extracted entities as a neat block for the carrier."""
    lines: list[str] = []
    for key, val in entities.items():
        if key in _ENTITY_SKIP_KEYS:
            continue
        label = _ENTITY_LABELS.get(key, key.replace("_", " ").title())
        if isinstance(val, list):
            val = ", ".join(str(v) for v in val)
        lines.append(f"  {label}: {val}")
    if lines:
        return "Extracted Details:\n" + "\n".join(lines) + "\n\n"
    return ""


def _build_carrier_missing_block(
    missing_required: list[str], missing_optional: list[str]
) -> str:
    """Missing-item checklist for the carrier email."""
    items = missing_required + missing_optional
    if not items:
        return ""
    lines = ["Still Pending from Insured:"]
    for item in items:
        lines.append(f"  ☐ {item}")
    lines.append("")
    return "\n".join(lines) + "\n"


def generate_carrier_email(
    intent: IntentCategory,
    name: str,
    policy_number: str,
    summary: str,
    entities: dict | None = None,
) -> str:
    """Build a carrier-facing email draft with subject, entities, and missing items."""
    entities = entities or {}
    eff_date = entities.get("effective_date", "TBD")
    policy = policy_number or "N/A"

    # Subject line
    subject_tpl = _CARRIER_SUBJECT_MAP.get(intent)
    if subject_tpl:
        subject = subject_tpl.format(
            name=name or "Insured",
            policy=policy,
            eff_date=eff_date,
        )
    else:
        subject = f"Service Request – {name or 'Insured'} – {policy}"

    # Body
    body_tpl = _CARRIER_BODY_TEMPLATES.get(intent)
    if not body_tpl:
        # Fallback for "other"
        return (
            f"Subject: {subject}\n\n"
            f"Hi,\n\n"
            f"Our insured ({name or 'customer'}, Policy: {policy}) has submitted "
            f"a service request. Details below:\n\n"
            f"{summary[:500]}\n\n"
            f"Please advise on next steps.\n\nThank you."
        )

    missing_req, missing_opt = detect_missing_info(intent, entities)
    entities_block = _build_entities_block(entities)
    missing_block = _build_carrier_missing_block(missing_req, missing_opt)

    body = body_tpl.format(
        name=name or "Insured",
        policy=policy,
        entities_block=entities_block,
        missing_block=missing_block,
    )

    return f"Subject: {subject}\n\n{body}"


# ======================================================================
# AMS note drafts
# ======================================================================

def generate_ams_note(
    intent: IntentCategory,
    name: str,
    policy_number: str,
    channel: str,
    summary: str,
    entities: dict | None = None,
) -> str:
    """Timestamped AMS activity note: channel, summary, action, pending items."""
    entities = entities or {}
    stamp = _now_stamp()
    missing_req, missing_opt = detect_missing_info(intent, entities)

    lines: list[str] = [
        f"[{stamp}] SERVICE REQUEST — {intent.value.upper().replace('_', ' ')}",
        f"Channel: {channel.upper()}",
        f"Insured: {name or 'Unknown'}",
        f"Policy: {policy_number or 'N/A'}",
        "",
        "--- Summary ---",
        summary[:1000],
        "",
        "--- Extracted Entities ---",
    ]

    entity_found = False
    for key, val in entities.items():
        if key in _ENTITY_SKIP_KEYS:
            continue
        label = _ENTITY_LABELS.get(key, key.replace("_", " ").title())
        if isinstance(val, list):
            val = ", ".join(str(v) for v in val)
        lines.append(f"  {label}: {val}")
        entity_found = True
    if not entity_found:
        lines.append("  (none extracted)")

    lines.append("")
    lines.append("--- Action Taken ---")
    lines.append("Parsed inbound message. Generated client reply, carrier email, and checklist.")
    lines.append("Status set to REVIEW — awaiting CSR approval.")

    lines.append("")
    lines.append("--- Pending Items ---")
    if missing_req:
        for item in missing_req:
            lines.append(f"  [REQUIRED] {item}")
        for item in missing_opt:
            lines.append(f"  [OPTIONAL] {item}")
    elif missing_opt:
        lines.append("  All required information received.")
        for item in missing_opt:
            lines.append(f"  [OPTIONAL] {item}")
    else:
        lines.append("  All required information received.")

    return "\n".join(lines)


# ======================================================================
# Internal checklist
# ======================================================================

_CHECKLIST_MAP: dict[IntentCategory, list[str]] = {
    IntentCategory.coi: [
        "Verify certificate holder name and address",
        "Confirm AI / Waiver of Sub / PNC requirements",
        "Issue COI from carrier portal",
        "Send COI to requesting party and insured",
        "Log completed request in AMS",
    ],
    IntentCategory.vehicle_add: [
        "Collect VIN or Year/Make/Model",
        "Confirm garaging address",
        "Confirm effective date",
        "Check lienholder requirements",
        "Submit endorsement to carrier",
        "Update AMS vehicle schedule",
        "Send confirmation to insured",
    ],
    IntentCategory.driver_add: [
        "Collect full legal name, DOB, and license number",
        "Run MVR (Motor Vehicle Report) check",
        "Submit driver addition to carrier",
        "Update AMS driver list",
        "Send confirmation to insured",
    ],
    IntentCategory.address_change: [
        "Confirm new full address with insured",
        "Confirm effective date",
        "Check territory rating impact",
        "Submit address change to carrier",
        "Update AMS records",
        "Send confirmation to insured",
    ],
    IntentCategory.payroll_change: [
        "Collect updated payroll breakdown by class code",
        "Confirm effective date",
        "Submit audit/endorsement to carrier",
        "Update AMS payroll records",
        "Send confirmation to insured",
    ],
    IntentCategory.coverage_change: [
        "Review current limits and requested change",
        "Obtain quote from carrier",
        "Present options to insured",
        "Bind coverage change on approval",
        "Update AMS with new coverage details",
        "Send updated dec page to insured",
    ],
    IntentCategory.other: [
        "Review message and determine next steps",
        "Respond to client",
        "Log outcome in AMS",
    ],
}


def generate_checklist(
    intent: IntentCategory, entities: dict | None = None
) -> str:
    """Return JSON string of checklist items.

    Items already satisfied by extracted entities are marked done.
    """
    entities = entities or {}
    base_items = _CHECKLIST_MAP.get(intent, _CHECKLIST_MAP[IntentCategory.other])

    # Add dynamic items for missing required info
    missing_req, _ = detect_missing_info(intent, entities)
    extra = [f"Request from insured: {label}" for label in missing_req]

    return json.dumps(extra + base_items)
