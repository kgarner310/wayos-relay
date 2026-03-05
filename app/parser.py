"""
Deterministic message parser: extracts customer name, policy hints, intent, urgency.
No LLM required — uses regex + keyword matching.
"""
import re
from dataclasses import dataclass

from app.models import IntentCategory


@dataclass
class ParseResult:
    customer_name: str
    policy_hint: str
    intent: IntentCategory
    urgency: int  # 1-5


# --- Intent keyword map (order matters: first match wins) ---
_INTENT_KEYWORDS: list[tuple[IntentCategory, list[str]]] = [
    (IntentCategory.coi, [
        "certificate of insurance", "coi", "cert of insurance", "proof of insurance",
        "insurance certificate", "additional insured",
    ]),
    (IntentCategory.vehicle_add, [
        "add vehicle", "new vehicle", "add a car", "new car", "add truck",
        "bought a vehicle", "purchased vehicle", "vehicle addition",
    ]),
    (IntentCategory.driver_add, [
        "add driver", "new driver", "additional driver", "hired driver",
        "new employee driver",
    ]),
    (IntentCategory.address_change, [
        "address change", "change address", "new address", "moved to",
        "change my address", "update address", "relocat",
    ]),
    (IntentCategory.payroll_change, [
        "payroll", "pay change", "salary update", "wage", "compensation change",
        "payroll audit", "payroll update",
    ]),
    (IntentCategory.coverage_change, [
        "coverage change", "increase coverage", "decrease coverage",
        "change my coverage", "add coverage", "remove coverage",
        "increase limit", "lower deductible", "raise deductible",
        "change deductible", "update coverage", "modify policy",
    ]),
]

# Urgency boosters
_URGENT_KEYWORDS = [
    "asap", "urgent", "immediately", "right away", "emergency",
    "rush", "time sensitive", "today", "deadline", "need it now",
]

# Policy number patterns: common formats like POL-12345, WC-2024-001, BOP123456
_POLICY_PATTERN = re.compile(
    r"\b([A-Z]{2,4}[-\s]?\d{4,10}(?:[-\s]\d{2,6})?)\b", re.IGNORECASE
)

# Name extraction: "my name is ...", "this is ...", "— John Smith", email From header style
_NAME_PATTERNS = [
    re.compile(r"(?:my name is|this is|i(?:'?m| am))\s+([A-Z][a-z]+ [A-Z][a-z]+)", re.IGNORECASE),
    re.compile(r"(?:thanks|regards|sincerely|best)[,\s]*\n?\s*([A-Z][a-z]+ [A-Z][a-z]+)"),
    re.compile(r"^([A-Z][a-z]+ [A-Z][a-z]+)$", re.MULTILINE),
]


def classify_intent(text: str) -> IntentCategory:
    lower = text.lower()
    for intent, keywords in _INTENT_KEYWORDS:
        for kw in keywords:
            if kw in lower:
                return intent
    return IntentCategory.other


def extract_policy_hint(text: str) -> str:
    match = _POLICY_PATTERN.search(text)
    return match.group(1).strip() if match else ""


def extract_customer_name(text: str, sender: str = "") -> str:
    for pattern in _NAME_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
    # Fallback: use email local part or phone
    if "@" in sender:
        local = sender.split("@")[0]
        # Turn "john.smith" or "john_smith" into "John Smith"
        parts = re.split(r"[._]", local)
        if len(parts) >= 2:
            return " ".join(p.capitalize() for p in parts[:2])
        return local.capitalize()
    return sender


def score_urgency(text: str) -> int:
    lower = text.lower()
    score = 3  # default medium
    for kw in _URGENT_KEYWORDS:
        if kw in lower:
            score = min(score + 1, 5)
    # Exclamation marks boost urgency
    if text.count("!") >= 2:
        score = min(score + 1, 5)
    return score


def parse_message(body: str, subject: str = "", sender: str = "") -> ParseResult:
    full_text = f"{subject}\n{body}" if subject else body
    return ParseResult(
        customer_name=extract_customer_name(full_text, sender),
        policy_hint=extract_policy_hint(full_text),
        intent=classify_intent(full_text),
        urgency=score_urgency(full_text),
    )
