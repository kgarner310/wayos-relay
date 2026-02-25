"""JSON API: simulate inbound, list requests, approve/reject."""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.database import get_session
from app.ingest import ingest_message
from app.models import (
    AuditLog,
    ChannelType,
    RequestStatus,
    StructuredRequest,
)
from app.services.email_send import send_email
from app.services.sms import send_sms

router = APIRouter(prefix="/api", tags=["api"])


# --- Schemas ---

class SimulateRequest(BaseModel):
    channel: str = "email"
    sender: str = "demo@example.com"
    subject: str = ""
    body: str


class ApproveRequest(BaseModel):
    approved_by: str = "agent"
    client_reply_draft: str | None = None
    carrier_email_draft: str | None = None


# --- Endpoints ---

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
    return [_sr_to_dict(sr) for sr in results]


@router.get("/requests/{request_id}")
def get_request(request_id: int, session: Session = Depends(get_session)):
    sr = session.get(StructuredRequest, request_id)
    if not sr:
        raise HTTPException(404, "Request not found")
    return _sr_to_dict(sr)


@router.post("/simulate")
def simulate_inbound(payload: SimulateRequest, session: Session = Depends(get_session)):
    """Simulate an inbound message (for demo purposes)."""
    channel = ChannelType(payload.channel) if payload.channel in ChannelType.__members__ else ChannelType.manual
    sr = ingest_message(
        session,
        channel=channel,
        sender=payload.sender,
        subject=payload.subject,
        body=payload.body,
        raw_payload=json.dumps(payload.model_dump()),
    )
    return _sr_to_dict(sr)


@router.post("/requests/{request_id}/approve")
def approve_request(
    request_id: int,
    payload: ApproveRequest,
    session: Session = Depends(get_session),
):
    sr = session.get(StructuredRequest, request_id)
    if not sr:
        raise HTTPException(404, "Request not found")
    if sr.status in (RequestStatus.sent, RequestStatus.rejected):
        raise HTTPException(400, f"Cannot approve a {sr.status.value} request")

    # Allow editing drafts on approve
    if payload.client_reply_draft is not None:
        sr.client_reply_draft = payload.client_reply_draft
    if payload.carrier_email_draft is not None:
        sr.carrier_email_draft = payload.carrier_email_draft

    sr.status = RequestStatus.approved
    sr.approved_by = payload.approved_by
    sr.approved_at = datetime.now(timezone.utc)
    sr.updated_at = datetime.now(timezone.utc)

    session.add(AuditLog(
        structured_request_id=sr.id,
        action="approved",
        actor=payload.approved_by,
    ))

    # Send outbound
    sent_details = []
    raw = sr.raw_message
    if raw and sr.client_reply_draft:
        if raw.channel == ChannelType.sms:
            ok = send_sms(raw.sender, sr.client_reply_draft)
            sent_details.append(f"sms_to_client={'ok' if ok else 'skipped'}")
        elif "@" in raw.sender:
            ok = send_email(
                raw.sender,
                f"Re: {raw.subject or 'Your request'}",
                sr.client_reply_draft,
            )
            sent_details.append(f"email_to_client={'ok' if ok else 'skipped'}")

    if sr.carrier_email_draft:
        # In a real system, carrier email would go to a configured address.
        # For MVP we just log it.
        sent_details.append("carrier_email=logged_only")

    sr.status = RequestStatus.sent
    sr.updated_at = datetime.now(timezone.utc)

    session.add(AuditLog(
        structured_request_id=sr.id,
        action="sent",
        actor="system",
        details="; ".join(sent_details),
    ))

    session.commit()
    session.refresh(sr)
    return _sr_to_dict(sr)


@router.post("/requests/{request_id}/reject")
def reject_request(request_id: int, session: Session = Depends(get_session)):
    sr = session.get(StructuredRequest, request_id)
    if not sr:
        raise HTTPException(404, "Request not found")

    sr.status = RequestStatus.rejected
    sr.updated_at = datetime.now(timezone.utc)

    session.add(AuditLog(
        structured_request_id=sr.id,
        action="rejected",
        actor="agent",
    ))
    session.commit()
    session.refresh(sr)
    return _sr_to_dict(sr)


@router.get("/requests/{request_id}/audit")
def get_audit_log(request_id: int, session: Session = Depends(get_session)):
    stmt = (
        select(AuditLog)
        .where(AuditLog.structured_request_id == request_id)
        .order_by(AuditLog.created_at.asc())  # type: ignore[union-attr]
    )
    logs = session.exec(stmt).all()
    return [
        {
            "id": log.id,
            "action": log.action,
            "actor": log.actor,
            "details": log.details,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]


def _sr_to_dict(sr: StructuredRequest) -> dict:
    raw = sr.raw_message
    return {
        "id": sr.id,
        "customer_name": sr.customer_name,
        "policy_hint": sr.policy_hint,
        "intent": sr.intent.value,
        "urgency": sr.urgency,
        "status": sr.status.value,
        "client_reply_draft": sr.client_reply_draft,
        "carrier_email_draft": sr.carrier_email_draft,
        "ams_note_draft": sr.ams_note_draft,
        "approved_by": sr.approved_by,
        "approved_at": sr.approved_at.isoformat() if sr.approved_at else None,
        "created_at": sr.created_at.isoformat(),
        "updated_at": sr.updated_at.isoformat(),
        "raw_message": {
            "id": raw.id,
            "channel": raw.channel.value,
            "sender": raw.sender,
            "subject": raw.subject,
            "body": raw.body,
            "received_at": raw.received_at.isoformat(),
        } if raw else None,
    }
