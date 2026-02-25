"""
Deterministic classification engine.

Takes a RawMessage (subject + body) and returns:
- intent_category
- entities dict
- urgency_score (0-100)
- confidence_score (0-100)

No LLM required — regex + keyword matching only.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.models import IntentCategory


@dataclass
class ParseResult:
    intent: IntentCategory
    entities: dict = field(default_factory=dict)
    urgency_score: int = 30
    confidence_score: int = 50


# ===== Intent rules =====

_VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")

_INTENT_RULES: list[tuple[IntentCategory, list[str]]] = [
    (IntentCategory.coi, [
        "certificate of insurance", "coi", "cert of insurance",
        "additional insured", "holder", "waiver of subrogation",
        "primary and noncontributory", "proof of insurance",
        "insurance certificate",
    ]),
    (IntentCategory.vehicle_add, [
        "add vehicle", "new vehicle", "new truck", "new car",
        "vin", "purchase", "bill of sale", "add a car",
        "bought a vehicle", "vehicle addition",
    ]),
    (IntentCategory.driver_add, [
        "add driver", "new driver", "additional driver",
        "license", "dob", "date of birth", "hired driver",
    ]),
    (IntentCategory.address_change, [
        "new address", "moved to", "garaging", "mailing address",
        "address change", "change address", "update address",
        "change my address", "relocat",
    ]),
    (IntentCategory.payroll_change, [
        "payroll", "workers comp", "wc", "audit",
        "class code", "1099", "subcontractor",
    ]),
    (IntentCategory.coverage_change, [
        "increase limits", "lower limits", "higher limits",
        "coverage limits", "umbrella",
        "add coverage", "increase coverage", "decrease coverage",
        "change my coverage", "remove coverage", "increase limit",
        "lower deductible", "raise deductible", "modify policy",
    ]),
]

# ===== Entity extraction patterns =====

_POLICY_RE = re.compile(
    r"\b([A-Z]{2,4}-\d{4,10}(?:-\d{2,6})?)\b"
    r"|"
    r"\b([A-Z]{3,4}\d{4,10})\b",
    re.IGNORECASE,
)

_NAME_PATTERNS = [
    re.compile(r"(?:my name is|this is|i(?:'?m| am))\s+([A-Z][a-z]+ [A-Z][a-z]+)", re.IGNORECASE),
    re.compile(r"(?:thanks|regards|sincerely|best)[,\s]*\n?\s*([A-Z][a-z]+ [A-Z][a-z]+)"),
    re.compile(r"^([A-Z][a-z]+ [A-Z][a-z]+)$", re.MULTILINE),
]

_ADDRESS_RE = re.compile(
    r"\d{1,5}\s+[A-Z][a-zA-Z\s.]+(?:St|Ave|Blvd|Dr|Rd|Ln|Way|Ct|Pl|Pkwy|Circle|Suite|Floor|Ste)"
    r"[^,\n]{0,40}",
    re.IGNORECASE,
)

_DATE_RE = re.compile(
    r"\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\b"
)

_DOLLAR_RE = re.compile(r"\$[\d,]+(?:\.\d{2})?")

_DL_RE = re.compile(r"\b([A-Z]{2}[-\s]?\d{6,10})\b")

_DOB_RE = re.compile(
    r"(?:dob|date of birth|born)[:\s]*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
    re.IGNORECASE,
)

_DRIVER_NAME_RE = re.compile(
    r"(?:driver|new driver|add driver)[:\s]+([A-Z][a-z]+ [A-Z][a-z]+)",
    re.IGNORECASE,
)

_CERT_HOLDER_RE = re.compile(
    r"(?:certificate holder|additional insured|sent? to|holder)[:\s]+([^\n,]{3,60})",
    re.IGNORECASE,
)

_EFFECTIVE_DATE_RE = re.compile(
    r"(?:effective|start(?:ing)?|as of|by)[:\s]*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
    re.IGNORECASE,
)

# ===== Urgency keywords =====

_URGENT_IMMEDIATE = ["today", "tomorrow", "asap", "urgent", "before", "deadline"]
_URGENT_CONTEXT = ["jobsite", "contract", "permit", "closing"]

# ===== Near-date detection =====

_DATE_FORMATS = ["%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%m-%d-%y"]


def _is_near_date(text: str, days: int = 7) -> bool:
    """Check if any date in text is within `days` days from today."""
    now = datetime.now()
    cutoff = now + timedelta(days=days)
    for match in _DATE_RE.finditer(text):
        for fmt in _DATE_FORMATS:
            try:
                dt = datetime.strptime(match.group(1), fmt)
                # Handle 2-digit year
                if dt.year < 100:
                    dt = dt.replace(year=dt.year + 2000)
                if now <= dt <= cutoff:
                    return True
            except ValueError:
                continue
    return False


# ===== Core functions =====

def _classify_intent(text: str) -> tuple[IntentCategory, list[str]]:
    """Return (intent, matched_keywords). First matching category wins."""
    lower = text.lower()
    for intent, keywords in _INTENT_RULES:
        matched = [kw for kw in keywords if kw in lower]
        if matched:
            return intent, matched
    return IntentCategory.other, []


def _extract_entities(text: str, intent: IntentCategory) -> dict:
    """Pull structured entities from the message text."""
    entities: dict = {}

    # Policy number — always attempt
    policy_match = _POLICY_RE.search(text)
    if policy_match:
        val = (policy_match.group(1) or policy_match.group(2) or "").strip()
        if val:
            entities["policy_number"] = val

    # Customer name
    for pat in _NAME_PATTERNS:
        m = pat.search(text)
        if m:
            entities["customer_name"] = m.group(1).strip()
            break

    # VIN
    vin_match = _VIN_RE.search(text)
    if vin_match:
        entities["vin"] = vin_match.group(0)

    # Address
    addr_match = _ADDRESS_RE.search(text)
    if addr_match:
        entities["address"] = addr_match.group(0).strip()

    # Driver name
    driver_match = _DRIVER_NAME_RE.search(text)
    if driver_match:
        entities["driver_name"] = driver_match.group(1).strip()

    # DOB
    dob_match = _DOB_RE.search(text)
    if dob_match:
        entities["dob"] = dob_match.group(1)

    # Driver's license
    dl_match = _DL_RE.search(text)
    if dl_match:
        entities["drivers_license"] = dl_match.group(1).strip()

    # Certificate holder
    holder_match = _CERT_HOLDER_RE.search(text)
    if holder_match:
        entities["certificate_holder"] = holder_match.group(1).strip()

    # Effective date
    eff_match = _EFFECTIVE_DATE_RE.search(text)
    if eff_match:
        entities["effective_date"] = eff_match.group(1)

    # Dollar amounts (payroll, coverage)
    dollar_matches = _DOLLAR_RE.findall(text)
    if dollar_matches:
        entities["dollar_amounts"] = dollar_matches

    return entities


def _score_urgency(text: str) -> int:
    """Score urgency 0-100 based on keywords and date proximity."""
    lower = text.lower()
    score = 30  # baseline

    # +30 for immediate-urgency keywords
    for kw in _URGENT_IMMEDIATE:
        if kw in lower:
            score += 30
            break  # only apply once

    # +20 if a date within 7 days is mentioned
    if _is_near_date(text, days=7):
        score += 20

    # +10 for context keywords
    for kw in _URGENT_CONTEXT:
        if kw in lower:
            score += 10
            break

    # Exclamation marks as signal
    if text.count("!") >= 2:
        score += 10

    return min(score, 100)


def _score_confidence(
    intent: IntentCategory, matched_keywords: list[str], entities: dict
) -> int:
    """Score confidence 0-100 based on match quality."""
    if intent == IntentCategory.other:
        return 20  # low confidence for unclassified

    score = 50  # baseline for any match

    # +20 if strong keyword + relevant entity extracted
    has_relevant_entity = False
    if intent == IntentCategory.coi and "certificate_holder" in entities:
        has_relevant_entity = True
    elif intent == IntentCategory.vehicle_add and "vin" in entities:
        has_relevant_entity = True
    elif intent == IntentCategory.driver_add and (
        "driver_name" in entities or "dob" in entities
    ):
        has_relevant_entity = True
    elif intent == IntentCategory.address_change and "address" in entities:
        has_relevant_entity = True
    elif intent == IntentCategory.payroll_change and "dollar_amounts" in entities:
        has_relevant_entity = True
    elif intent == IntentCategory.coverage_change and "dollar_amounts" in entities:
        has_relevant_entity = True

    if has_relevant_entity and matched_keywords:
        score += 20

    # +10 if multiple keywords matched
    if len(matched_keywords) >= 2:
        score += 10

    # Policy number is always a positive signal
    if "policy_number" in entities:
        score += 5

    # -20 if category could be ambiguous (check if text also matches another)
    lower_text_for_ambiguity = " ".join(matched_keywords)  # we already classified
    # Actually re-check: count how many categories have *any* keyword hit
    lower = entities.get("_full_text_lower", "")
    # We'll pass full text lower through a side channel — see parse_message
    # For now, skip ambiguity penalty if we don't have the text.
    # (Ambiguity is handled in parse_message below.)

    return min(max(score, 0), 100)


def parse_message(body: str, subject: str = "", sender: str = "") -> ParseResult:
    """Full classification pipeline."""
    full_text = f"{subject}\n{body}" if subject else body
    lower_full = full_text.lower()

    # 1. Classify intent
    intent, matched_keywords = _classify_intent(full_text)

    # 2. Extract entities
    entities = _extract_entities(full_text, intent)

    # Fallback customer name from sender
    if "customer_name" not in entities and sender:
        if "@" in sender:
            local = sender.split("@")[0]
            parts = re.split(r"[._]", local)
            if len(parts) >= 2:
                entities["customer_name"] = " ".join(p.capitalize() for p in parts[:2])
            else:
                entities["customer_name"] = local.capitalize()
        else:
            entities["customer_name"] = sender

    # 3. Urgency
    urgency = _score_urgency(full_text)

    # 4. Confidence
    confidence = _score_confidence(intent, matched_keywords, entities)

    # Ambiguity check: how many categories match?
    hit_count = 0
    for _, keywords in _INTENT_RULES:
        if any(kw in lower_full for kw in keywords):
            hit_count += 1
    if hit_count >= 2:
        confidence = max(confidence - 20, 0)

    return ParseResult(
        intent=intent,
        entities=entities,
        urgency_score=urgency,
        confidence_score=confidence,
    )
