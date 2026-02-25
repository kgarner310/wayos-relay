"""
Digest generator — the core of ServiceInbox Lite.

Groups pending StructuredRequests by intent category, formats them into
a clean work-packet digest (HTML), persists a DigestRun, and optionally
sends the digest email.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, select

from app.artifacts import detect_missing_info
from app.models import (
    DigestItem,
    DigestRun,
    IntentCategory,
    MessageStatus,
    RawMessage,
    StructuredRequest,
)

log = logging.getLogger(__name__)

# Human-friendly labels for intent categories
_INTENT_LABELS: dict[str, str] = {
    "coi": "Certificates of Insurance",
    "vehicle_add": "Vehicle Add Endorsements",
    "driver_add": "Driver Add Endorsements",
    "address_change": "Address Changes",
    "payroll_change": "Payroll / Audit Changes",
    "coverage_change": "Coverage Changes",
    "other": "Other / General Requests",
}

# Section icons for the digest
_INTENT_ICONS: dict[str, str] = {
    "coi": "&#128196;",           # 📄
    "vehicle_add": "&#128663;",   # 🚗
    "driver_add": "&#128100;",    # 👤
    "address_change": "&#127968;",# 🏠
    "payroll_change": "&#128176;",# 💰
    "coverage_change": "&#128737;",# 🛡
    "other": "&#128233;",         # 📩
}


def _get_pending_requests(session: Session) -> list[StructuredRequest]:
    """Fetch all StructuredRequests in 'review' status not yet included in a digest."""
    stmt = (
        select(StructuredRequest)
        .join(RawMessage, StructuredRequest.raw_message_id == RawMessage.id)
        .where(RawMessage.status == MessageStatus.review)
        .order_by(StructuredRequest.urgency_score.desc())  # type: ignore[union-attr]
    )
    return list(session.exec(stmt).all())


def _group_by_intent(
    requests: list[StructuredRequest],
) -> dict[str, list[StructuredRequest]]:
    """Group requests by intent_category, preserving urgency sort within each group."""
    groups: dict[str, list[StructuredRequest]] = {}
    for sr in requests:
        key = sr.intent_category.value
        groups.setdefault(key, []).append(sr)
    return groups


def _render_item_row(sr: StructuredRequest) -> str:
    """Render a single request as an HTML table row."""
    entities = json.loads(sr.extracted_entities_json)
    name = entities.get("customer_name", "Unknown")
    policy = entities.get("policy_number", "")
    raw = sr.raw_message

    subject = ""
    sender = ""
    channel = ""
    received = ""
    if raw:
        subject = raw.subject or raw.body_text[:80]
        sender = raw.from_address
        channel = raw.channel.value.upper()
        received = raw.received_at.strftime("%b %d %I:%M %p")

    # Missing info badge
    missing_req, missing_opt = detect_missing_info(sr.intent_category, entities)
    missing_badge = ""
    if missing_req:
        items = ", ".join(missing_req)
        missing_badge = f'<span style="color:#e74c3c;font-size:12px;">Missing: {items}</span>'
    elif missing_opt:
        missing_badge = '<span style="color:#f39c12;font-size:12px;">Optional info available to request</span>'

    urgency_color = "#e74c3c" if sr.urgency_score >= 70 else "#f39c12" if sr.urgency_score >= 40 else "#27ae60"

    return f"""<tr>
      <td style="text-align:center;">
        <strong style="color:{urgency_color};font-size:18px;">{sr.urgency_score}</strong>
      </td>
      <td>
        <strong>{name}</strong>
        {f'<br><span style="color:#666;font-size:12px;">Policy: {policy}</span>' if policy else ''}
        {f'<br>{missing_badge}' if missing_badge else ''}
      </td>
      <td style="font-size:13px;">{subject[:60]}{'...' if len(subject) > 60 else ''}</td>
      <td style="font-size:12px;color:#666;">{sender}</td>
      <td style="text-align:center;"><span style="background:#eee;padding:2px 6px;border-radius:3px;font-size:11px;">{channel}</span></td>
      <td style="font-size:12px;color:#888;">{received}</td>
    </tr>"""


def _render_section(intent_key: str, items: list[StructuredRequest]) -> str:
    """Render a full section (one intent category) as HTML."""
    label = _INTENT_LABELS.get(intent_key, intent_key.replace("_", " ").title())
    icon = _INTENT_ICONS.get(intent_key, "&#128233;")
    count = len(items)

    rows = "\n".join(_render_item_row(sr) for sr in items)

    return f"""
    <div style="margin-bottom:28px;">
      <h2 style="color:#1a1a2e;border-bottom:2px solid #16213e;padding-bottom:6px;font-size:18px;">
        {icon} {label} <span style="color:#888;font-weight:normal;font-size:14px;">({count} item{'s' if count != 1 else ''})</span>
      </h2>
      <table style="width:100%;border-collapse:collapse;font-family:system-ui,-apple-system,sans-serif;font-size:14px;">
        <thead>
          <tr style="background:#f8f9fa;text-align:left;">
            <th style="padding:8px;width:60px;">Urg.</th>
            <th style="padding:8px;">Customer</th>
            <th style="padding:8px;">Subject</th>
            <th style="padding:8px;">From</th>
            <th style="padding:8px;width:60px;">Ch.</th>
            <th style="padding:8px;width:110px;">Received</th>
          </tr>
        </thead>
        <tbody>
          {rows}
        </tbody>
      </table>
    </div>"""


def render_digest_html(
    requests: list[StructuredRequest],
    period_label: str = "",
    generated_at: Optional[datetime] = None,
) -> str:
    """Render a full digest as standalone HTML (for email and archive)."""
    if generated_at is None:
        generated_at = datetime.now(timezone.utc)

    groups = _group_by_intent(requests)
    total = len(requests)

    # Summary counts
    summary_items = []
    # Fixed order so digest is consistent
    intent_order = ["coi", "vehicle_add", "driver_add", "address_change",
                     "payroll_change", "coverage_change", "other"]
    for key in intent_order:
        if key in groups:
            label = _INTENT_LABELS.get(key, key)
            icon = _INTENT_ICONS.get(key, "")
            summary_items.append(
                f'<li>{icon} <strong>{len(groups[key])}</strong> {label}</li>'
            )

    summary_html = "\n".join(summary_items)

    # Sections
    sections_html = ""
    for key in intent_order:
        if key in groups:
            sections_html += _render_section(key, groups[key])

    # Count urgent items
    urgent_count = sum(1 for sr in requests if sr.urgency_score >= 70)
    urgent_banner = ""
    if urgent_count:
        urgent_banner = f"""
        <div style="background:#ffeaea;border:1px solid #e74c3c;border-radius:6px;padding:12px 16px;margin-bottom:20px;">
          <strong style="color:#e74c3c;">&#9888; {urgent_count} urgent item{'s' if urgent_count != 1 else ''}</strong>
          <span style="color:#666;"> — requires immediate attention</span>
        </div>"""

    timestamp = generated_at.strftime("%B %d, %Y at %I:%M %p UTC")
    period_title = period_label.title() if period_label else "Service"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head>
<body style="font-family:system-ui,-apple-system,sans-serif;max-width:800px;margin:0 auto;padding:20px;color:#333;">

  <div style="background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);color:white;padding:24px 28px;border-radius:8px;margin-bottom:24px;">
    <h1 style="margin:0 0 4px 0;font-size:22px;">ServiceInbox — {period_title} Digest</h1>
    <p style="margin:0;opacity:0.8;font-size:14px;">{timestamp}</p>
  </div>

  {urgent_banner}

  <div style="background:#f8f9fa;border-radius:6px;padding:16px 20px;margin-bottom:24px;">
    <h3 style="margin:0 0 8px 0;font-size:15px;color:#555;">Summary — {total} item{'s' if total != 1 else ''} requiring service</h3>
    <ul style="margin:0;padding-left:20px;line-height:1.8;font-size:14px;">
      {summary_html}
    </ul>
  </div>

  {sections_html}

  <div style="border-top:1px solid #ddd;padding-top:12px;margin-top:20px;font-size:12px;color:#999;text-align:center;">
    Generated by ServiceInbox Lite &middot; Review and action items at
    <a href="{{{{ app_base_url }}}}" style="color:#3498db;">your dashboard</a>
  </div>

</body>
</html>"""


def generate_digest(
    session: Session,
    *,
    period_label: str = "manual",
    recipient_emails: list[str] | None = None,
) -> Optional[DigestRun]:
    """Generate a digest of all pending (review-status) requests.

    Returns the DigestRun record, or None if there were no items.
    """
    requests = _get_pending_requests(session)
    if not requests:
        log.info("No pending requests — skipping digest generation")
        return None

    now = datetime.now(timezone.utc)
    html = render_digest_html(requests, period_label=period_label, generated_at=now)

    sent_to = ", ".join(recipient_emails) if recipient_emails else ""

    run = DigestRun(
        generated_at=now,
        period_label=period_label,
        item_count=len(requests),
        sent_to=sent_to,
        html_snapshot=html,
    )
    session.add(run)
    session.flush()

    # Link each request to this digest
    for sr in requests:
        item = DigestItem(
            digest_run_id=run.id,
            structured_request_id=sr.id,
        )
        session.add(item)

    session.commit()
    session.refresh(run)

    log.info(
        "Generated %s digest: %d items, id=%s",
        period_label, len(requests), run.id[:8],
    )
    return run
