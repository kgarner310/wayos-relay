"""
Generate draft artifacts for a parsed request:
- client_reply_draft
- carrier_email_draft
- ams_note_draft
- internal_checklist (JSON list of action items)
"""
import json

from app.models import IntentCategory


_CLIENT_REPLY_TEMPLATES: dict[IntentCategory, str] = {
    IntentCategory.coi: (
        "Hi {name},\n\n"
        "Thank you for your request. We are preparing your Certificate of Insurance "
        "and will have it sent over shortly.\n\n"
        "If you need the COI sent to a specific party, please reply with their name, "
        "address, and email.\n\n"
        "Best regards,\nYour Insurance Team"
    ),
    IntentCategory.vehicle_add: (
        "Hi {name},\n\n"
        "We received your request to add a vehicle to your policy{policy_ref}. "
        "To proceed, we'll need:\n"
        "- Year, Make, Model\n"
        "- VIN number\n"
        "- Garaging address\n\n"
        "Please reply with these details and we'll get it taken care of.\n\n"
        "Best regards,\nYour Insurance Team"
    ),
    IntentCategory.driver_add: (
        "Hi {name},\n\n"
        "Thanks for letting us know about the new driver. "
        "To add them to your policy{policy_ref}, we'll need:\n"
        "- Full legal name\n"
        "- Date of birth\n"
        "- Driver's license number and state\n\n"
        "Best regards,\nYour Insurance Team"
    ),
    IntentCategory.address_change: (
        "Hi {name},\n\n"
        "We received your address change request{policy_ref}. "
        "We'll update your policy records. "
        "Please confirm the new address and effective date.\n\n"
        "Best regards,\nYour Insurance Team"
    ),
    IntentCategory.payroll_change: (
        "Hi {name},\n\n"
        "Thank you for the payroll update{policy_ref}. "
        "We will forward this to your carrier for processing. "
        "If you have a payroll report to attach, please send it over.\n\n"
        "Best regards,\nYour Insurance Team"
    ),
    IntentCategory.coverage_change: (
        "Hi {name},\n\n"
        "We received your coverage change request{policy_ref}. "
        "We'll review the options and get back to you with a quote "
        "for the adjustment.\n\n"
        "Best regards,\nYour Insurance Team"
    ),
    IntentCategory.other: (
        "Hi {name},\n\n"
        "Thank you for reaching out. We've received your message and "
        "a team member will review it and respond shortly.\n\n"
        "Best regards,\nYour Insurance Team"
    ),
}

_CARRIER_TEMPLATES: dict[IntentCategory, str] = {
    IntentCategory.coi: (
        "Subject: COI Request — {name}{policy_ref}\n\n"
        "Hi,\n\n"
        "Please issue a Certificate of Insurance for the following insured:\n"
        "Name: {name}\n"
        "Policy: {policy_number}\n\n"
        "Additional details from the insured's request:\n{summary}\n\n"
        "Thank you."
    ),
    IntentCategory.vehicle_add: (
        "Subject: Vehicle Addition — {name}{policy_ref}\n\n"
        "Hi,\n\n"
        "Please add a vehicle to the policy for:\n"
        "Insured: {name}\n"
        "Policy: {policy_number}\n\n"
        "Details from the insured:\n{summary}\n\n"
        "We will forward VIN and vehicle details once received.\n\n"
        "Thank you."
    ),
    IntentCategory.driver_add: (
        "Subject: Driver Addition — {name}{policy_ref}\n\n"
        "Hi,\n\n"
        "Please add a driver to the policy for:\n"
        "Insured: {name}\n"
        "Policy: {policy_number}\n\n"
        "Driver details to follow.\n\n"
        "Thank you."
    ),
}

_CHECKLIST_MAP: dict[IntentCategory, list[str]] = {
    IntentCategory.coi: [
        "Verify certificate holder info",
        "Check additional insured requirements",
        "Issue COI from carrier portal",
        "Send COI to requesting party",
    ],
    IntentCategory.vehicle_add: [
        "Collect VIN, Year/Make/Model",
        "Confirm garaging address",
        "Submit endorsement to carrier",
        "Update AMS vehicle schedule",
    ],
    IntentCategory.driver_add: [
        "Collect driver license + DOB",
        "Run MVR check",
        "Submit driver addition to carrier",
        "Update AMS driver list",
    ],
    IntentCategory.address_change: [
        "Confirm new address",
        "Check territory rating impact",
        "Submit change to carrier",
        "Update AMS records",
    ],
    IntentCategory.payroll_change: [
        "Collect updated payroll breakdown by class code",
        "Submit audit/endorsement to carrier",
        "Update AMS payroll records",
    ],
    IntentCategory.coverage_change: [
        "Review current limits and requested change",
        "Obtain quote from carrier",
        "Present options to insured",
        "Bind coverage change on approval",
    ],
    IntentCategory.other: [
        "Review message and determine next steps",
        "Respond to client",
    ],
}


def _policy_ref(policy_number: str) -> str:
    if policy_number:
        return f" (Policy: {policy_number})"
    return ""


def generate_client_reply(
    intent: IntentCategory, name: str, policy_number: str
) -> str:
    template = _CLIENT_REPLY_TEMPLATES.get(intent, _CLIENT_REPLY_TEMPLATES[IntentCategory.other])
    return template.format(
        name=name or "Valued Customer",
        policy_ref=_policy_ref(policy_number),
    )


def generate_carrier_email(
    intent: IntentCategory, name: str, policy_number: str, summary: str
) -> str:
    template = _CARRIER_TEMPLATES.get(intent)
    if not template:
        return ""
    return template.format(
        name=name or "Insured",
        policy_number=policy_number or "N/A",
        policy_ref=_policy_ref(policy_number),
        summary=summary[:500],
    )


def generate_ams_note(
    intent: IntentCategory,
    name: str,
    policy_number: str,
    channel: str,
    summary: str,
    entities: dict | None = None,
) -> str:
    lines = [
        f"Service Request via {channel.upper()}",
        f"Customer: {name or 'Unknown'}",
        f"Policy: {policy_number or 'N/A'}",
        f"Intent: {intent.value}",
    ]
    if entities:
        for key, val in entities.items():
            if key not in ("customer_name", "policy_number"):
                lines.append(f"  {key}: {val}")
    lines.append("---")
    lines.append(summary[:1000])
    return "\n".join(lines)


def generate_checklist(intent: IntentCategory) -> str:
    """Return JSON string of checklist items for this intent."""
    items = _CHECKLIST_MAP.get(intent, _CHECKLIST_MAP[IntentCategory.other])
    return json.dumps(items)
