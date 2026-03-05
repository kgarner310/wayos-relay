"""
Generate draft artifacts for a parsed request:
- client_reply_draft: the reply to send back to the customer
- carrier_email_draft: email to send to the carrier (if applicable)
- ams_note_draft: internal note for the agency management system
"""
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
        "Policy: {policy_hint}\n\n"
        "Additional details from the insured's request:\n{summary}\n\n"
        "Thank you."
    ),
    IntentCategory.vehicle_add: (
        "Subject: Vehicle Addition — {name}{policy_ref}\n\n"
        "Hi,\n\n"
        "Please add a vehicle to the policy for:\n"
        "Insured: {name}\n"
        "Policy: {policy_hint}\n\n"
        "Details from the insured:\n{summary}\n\n"
        "We will forward VIN and vehicle details once received.\n\n"
        "Thank you."
    ),
    IntentCategory.driver_add: (
        "Subject: Driver Addition — {name}{policy_ref}\n\n"
        "Hi,\n\n"
        "Please add a driver to the policy for:\n"
        "Insured: {name}\n"
        "Policy: {policy_hint}\n\n"
        "Driver details to follow.\n\n"
        "Thank you."
    ),
}


def _policy_ref(policy_hint: str) -> str:
    if policy_hint:
        return f" (Policy: {policy_hint})"
    return ""


def generate_client_reply(
    intent: IntentCategory, name: str, policy_hint: str
) -> str:
    template = _CLIENT_REPLY_TEMPLATES.get(intent, _CLIENT_REPLY_TEMPLATES[IntentCategory.other])
    return template.format(name=name or "Valued Customer", policy_ref=_policy_ref(policy_hint))


def generate_carrier_email(
    intent: IntentCategory, name: str, policy_hint: str, summary: str
) -> str:
    template = _CARRIER_TEMPLATES.get(intent)
    if not template:
        return ""  # Not every intent needs a carrier email
    return template.format(
        name=name or "Insured",
        policy_hint=policy_hint or "N/A",
        policy_ref=_policy_ref(policy_hint),
        summary=summary[:500],
    )


def generate_ams_note(
    intent: IntentCategory, name: str, policy_hint: str, channel: str, summary: str
) -> str:
    return (
        f"Service Request via {channel.upper()}\n"
        f"Customer: {name or 'Unknown'}\n"
        f"Policy: {policy_hint or 'N/A'}\n"
        f"Intent: {intent.value}\n"
        f"---\n"
        f"{summary[:1000]}"
    )
