"""JSON API: simulate, list, approve/reject, compliance timeline, E&O export."""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app.database import get_session
from app.ingest import ingest_message
from app.models import (
    ApprovalAction,
    ApprovalEvent,
    ChannelType,
    DraftArtifacts,
    MessageStatus,
    OutboundKind,
    OutboundMessage,
    RawMessage,
    StructuredRequest,
)
from app.services.email_send import send_email
from app.services.sms import send_sms

router = APIRouter(prefix="/api", tags=["api"])


# ---------- Schemas ----------

class SimulateRequest(BaseModel):
    channel: str = "email"
    sender: str = "demo@example.com"
    subject: str = ""
    body: str


class ApproveRequest(BaseModel):
    actor_name: str = "agent"
    actor_email: str = ""
    client_reply_draft: str | None = None
    carrier_email_draft: str | None = None


# ---------- Endpoints ----------

@router.post("/seed")
def seed_database():
    """Load sample messages from seeds/sample_messages.json."""
    from app.seeds import load_seeds

    count = load_seeds()
    return {"loaded": count}


@router.get("/requests")
def list_requests(session: Session = Depends(get_session)):
    stmt = (
        select(StructuredRequest)
        .order_by(StructuredRequest.created_at.desc())  # type: ignore[union-attr]
    )
    results = session.exec(stmt).all()
    return [_sr_to_dict(sr, session) for sr in results]


@router.get("/requests/{request_id}")
def get_request(request_id: str, session: Session = Depends(get_session)):
    sr = session.get(StructuredRequest, request_id)
    if not sr:
        raise HTTPException(404, "Request not found")
    return _sr_to_dict(sr, session)


@router.post("/simulate")
def simulate_inbound(payload: SimulateRequest, session: Session = Depends(get_session)):
    """Simulate an inbound message (for demo purposes)."""
    channel_map = {v.value: v for v in ChannelType}
    channel = channel_map.get(payload.channel, ChannelType.manual)
    sr = ingest_message(
        session,
        channel=channel,
        from_address=payload.sender,
        subject=payload.subject or None,
        body=payload.body,
        raw_payload=json.dumps(payload.model_dump()),
    )
    return _sr_to_dict(sr, session)


@router.post("/requests/{request_id}/approve")
def approve_request(
    request_id: str,
    payload: ApproveRequest,
    session: Session = Depends(get_session),
):
    sr = session.get(StructuredRequest, request_id)
    if not sr:
        raise HTTPException(404, "Request not found")

    raw = sr.raw_message
    if not raw:
        raise HTTPException(400, "No raw message linked")
    if raw.status in (MessageStatus.sent, MessageStatus.rejected):
        raise HTTPException(400, f"Cannot approve a {raw.status.value} request")

    # Allow editing drafts on approve
    drafts = sr.draft_artifacts
    edits: dict = {}
    if drafts:
        if payload.client_reply_draft is not None:
            edits["client_reply_draft"] = payload.client_reply_draft
            drafts.client_reply_draft = payload.client_reply_draft
        if payload.carrier_email_draft is not None:
            edits["carrier_email_draft"] = payload.carrier_email_draft
            drafts.carrier_email_draft = payload.carrier_email_draft
        session.add(drafts)

    # Record approval event
    event = ApprovalEvent(
        structured_request_id=sr.id,
        action=ApprovalAction.approve,
        actor_name=payload.actor_name,
        actor_email=payload.actor_email,
        edits_json=json.dumps(edits) if edits else None,
    )
    session.add(event)

    raw.status = MessageStatus.approved
    session.add(raw)

    # Send outbound messages
    if drafts and drafts.client_reply_draft:
        result_json: dict = {}
        if raw.channel == ChannelType.sms:
            ok = send_sms(raw.from_address, drafts.client_reply_draft)
            result_json["sms"] = "sent" if ok else "skipped"
        elif "@" in raw.from_address:
            ok = send_email(
                raw.from_address,
                f"Re: {raw.subject or 'Your request'}",
                drafts.client_reply_draft,
            )
            result_json["email"] = "sent" if ok else "skipped"

        outbound_client = OutboundMessage(
            structured_request_id=sr.id,
            kind=OutboundKind.client,
            to_address=raw.from_address,
            subject=f"Re: {raw.subject or 'Your request'}",
            body=drafts.client_reply_draft,
            sent_at=datetime.now(timezone.utc),
            transport="smtp" if "@" in raw.from_address else "twilio",
            result_json=json.dumps(result_json),
        )
        session.add(outbound_client)

    if drafts and drafts.carrier_email_draft:
        outbound_carrier = OutboundMessage(
            structured_request_id=sr.id,
            kind=OutboundKind.carrier,
            to_address="carrier@placeholder.com",
            subject=f"Endorsement: {sr.intent_category.value}",
            body=drafts.carrier_email_draft,
            sent_at=datetime.now(timezone.utc),
            transport="smtp",
            result_json=json.dumps({"status": "logged_only"}),
        )
        session.add(outbound_carrier)

    raw.status = MessageStatus.sent
    session.add(raw)
    session.commit()
    session.refresh(sr)
    return _sr_to_dict(sr, session)


class RejectRequest(BaseModel):
    actor_name: str = "agent"
    actor_email: str = ""
    reason: str = ""


@router.post("/requests/{request_id}/reject")
def reject_request(
    request_id: str,
    payload: RejectRequest | None = None,
    session: Session = Depends(get_session),
):
    sr = session.get(StructuredRequest, request_id)
    if not sr:
        raise HTTPException(404, "Request not found")

    raw = sr.raw_message
    if raw:
        if raw.status in (MessageStatus.sent, MessageStatus.rejected):
            raise HTTPException(400, f"Cannot reject a {raw.status.value} request")
        raw.status = MessageStatus.rejected
        session.add(raw)

    actor_name = payload.actor_name if payload else "agent"
    actor_email = payload.actor_email if payload else ""
    reason = payload.reason if payload else ""

    edits = {"reason": reason} if reason else None

    event = ApprovalEvent(
        structured_request_id=sr.id,
        action=ApprovalAction.reject,
        actor_name=actor_name,
        actor_email=actor_email,
        edits_json=json.dumps(edits) if edits else None,
    )
    session.add(event)
    session.commit()
    session.refresh(sr)
    return _sr_to_dict(sr, session)


# ---------- Compliance Timeline ----------

@router.get("/requests/{request_id}/compliance")
def compliance_timeline(request_id: str, session: Session = Depends(get_session)):
    """Single timeline combining all events for a request."""
    sr = session.get(StructuredRequest, request_id)
    if not sr:
        raise HTTPException(404, "Request not found")

    return _build_timeline(sr, session)


@router.get("/requests/{request_id}/compliance/export")
def compliance_export_json(request_id: str, session: Session = Depends(get_session)):
    """Export compliance timeline as JSON."""
    sr = session.get(StructuredRequest, request_id)
    if not sr:
        raise HTTPException(404, "Request not found")

    return _build_timeline(sr, session)


@router.get("/requests/{request_id}/eo-report")
def eo_timeline_report(request_id: str, session: Session = Depends(get_session)):
    """Plain-text E&O timeline report for errors & omissions documentation."""
    sr = session.get(StructuredRequest, request_id)
    if not sr:
        raise HTTPException(404, "Request not found")

    timeline = _build_timeline(sr, session)
    entities = json.loads(sr.extracted_entities_json)
    raw = sr.raw_message

    lines = [
        "=" * 60,
        "ERRORS & OMISSIONS TIMELINE REPORT",
        "=" * 60,
        f"Request ID:     {sr.id}",
        f"Customer:       {entities.get('customer_name', 'Unknown')}",
        f"Policy:         {entities.get('policy_number', 'N/A')}",
        f"Intent:         {sr.intent_category.value}",
        f"Urgency Score:  {sr.urgency_score}/100",
        f"Confidence:     {sr.confidence_score}/100",
        "",
        "-" * 60,
        "ORIGINAL MESSAGE",
        "-" * 60,
    ]
    if raw:
        lines.append(f"Channel:  {raw.channel.value.upper()}")
        lines.append(f"From:     {raw.from_address}")
        lines.append(f"Received: {raw.received_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        if raw.subject:
            lines.append(f"Subject:  {raw.subject}")
        lines.append("")
        lines.append(raw.body_text[:2000])

    lines.append("")
    lines.append("-" * 60)
    lines.append("EVENT TIMELINE")
    lines.append("-" * 60)

    for event in timeline["events"]:
        lines.append(f"  [{event['timestamp']}] {event['event_type']}")
        if event.get("details"):
            lines.append(f"    {event['details']}")

    lines.append("")
    lines.append("-" * 60)
    lines.append("EXTRACTED ENTITIES")
    lines.append("-" * 60)
    for k, v in entities.items():
        lines.append(f"  {k}: {v}")

    lines.append("")
    lines.append("=" * 60)
    lines.append("END OF REPORT")
    lines.append("=" * 60)

    return PlainTextResponse("\n".join(lines))


# ---------- Helpers ----------

def _build_timeline(sr: StructuredRequest, session: Session) -> dict:
    """Build a unified timeline of all events for a structured request."""
    raw = sr.raw_message
    entities = json.loads(sr.extracted_entities_json)
    events: list[dict] = []

    # 1. Message received
    if raw:
        events.append({
            "timestamp": raw.received_at.isoformat(),
            "event_type": "message_received",
            "details": f"Inbound {raw.channel.value} from {raw.from_address}",
        })

    # 2. Parsed / classified
    events.append({
        "timestamp": sr.created_at.isoformat(),
        "event_type": "classified",
        "details": (
            f"Intent: {sr.intent_category.value}, "
            f"urgency: {sr.urgency_score}, "
            f"confidence: {sr.confidence_score}"
        ),
    })

    # 3. Drafts generated
    drafts = sr.draft_artifacts
    if drafts:
        events.append({
            "timestamp": drafts.created_at.isoformat(),
            "event_type": "drafts_generated",
            "details": "Client reply, carrier email, AMS note generated",
        })

    # 4. Approval / rejection events
    for ae in sr.approval_events:
        events.append({
            "timestamp": ae.approved_at.isoformat(),
            "event_type": f"action_{ae.action.value}",
            "details": f"By {ae.actor_name}" + (
                f" (edits: {ae.edits_json})" if ae.edits_json else ""
            ),
        })

    # 5. Outbound messages
    for om in sr.outbound_messages:
        events.append({
            "timestamp": om.sent_at.isoformat() if om.sent_at else sr.created_at.isoformat(),
            "event_type": f"outbound_{om.kind.value}",
            "details": f"To: {om.to_address} via {om.transport}",
        })

    events.sort(key=lambda e: e["timestamp"])

    return {
        "request_id": sr.id,
        "customer_name": entities.get("customer_name", ""),
        "policy_number": entities.get("policy_number", ""),
        "intent": sr.intent_category.value,
        "urgency_score": sr.urgency_score,
        "confidence_score": sr.confidence_score,
        "current_status": raw.status.value if raw else "unknown",
        "events": events,
    }


def _sr_to_dict(sr: StructuredRequest, session: Session) -> dict:
    raw = sr.raw_message
    drafts = sr.draft_artifacts
    entities = json.loads(sr.extracted_entities_json)

    return {
        "id": sr.id,
        "intent": sr.intent_category.value,
        "extracted_entities": entities,
        "urgency_score": sr.urgency_score,
        "confidence_score": sr.confidence_score,
        "status": raw.status.value if raw else "unknown",
        "created_at": sr.created_at.isoformat(),
        "drafts": {
            "client_reply_draft": drafts.client_reply_draft,
            "carrier_email_draft": drafts.carrier_email_draft,
            "ams_note_draft": drafts.ams_note_draft,
            "internal_checklist": json.loads(drafts.internal_checklist),
        } if drafts else None,
        "approval_events": [
            {
                "action": ae.action.value,
                "actor_name": ae.actor_name,
                "approved_at": ae.approved_at.isoformat(),
            }
            for ae in sr.approval_events
        ],
        "outbound_messages": [
            {
                "kind": om.kind.value,
                "to_address": om.to_address,
                "sent_at": om.sent_at.isoformat() if om.sent_at else None,
            }
            for om in sr.outbound_messages
        ],
        "raw_message": {
            "id": raw.id,
            "channel": raw.channel.value,
            "from_address": raw.from_address,
            "subject": raw.subject,
            "body_text": raw.body_text,
            "received_at": raw.received_at.isoformat(),
        } if raw else None,
    }
