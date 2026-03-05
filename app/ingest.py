"""
Core ingestion pipeline: RawMessage → parse → generate artifacts → StructuredRequest.
Shared by webhook, IMAP poller, and simulate endpoint.
"""
from sqlmodel import Session

from app.artifacts import generate_ams_note, generate_carrier_email, generate_client_reply
from app.models import (
    AuditLog,
    ChannelType,
    RawMessage,
    StructuredRequest,
)
from app.parser import parse_message


def ingest_message(
    session: Session,
    *,
    channel: ChannelType,
    sender: str,
    subject: str = "",
    body: str,
    raw_payload: str = "",
) -> StructuredRequest:
    """Full pipeline: store raw → parse → generate drafts → return StructuredRequest."""

    # 1. Store raw message
    raw = RawMessage(
        channel=channel,
        sender=sender,
        subject=subject,
        body=body,
        raw_payload=raw_payload,
    )
    session.add(raw)
    session.flush()  # get raw.id

    # 2. Parse
    result = parse_message(body, subject=subject, sender=sender)

    # 3. Generate drafts
    client_reply = generate_client_reply(result.intent, result.customer_name, result.policy_hint)
    carrier_email = generate_carrier_email(
        result.intent, result.customer_name, result.policy_hint, body
    )
    ams_note = generate_ams_note(
        result.intent, result.customer_name, result.policy_hint, channel.value, body
    )

    # 4. Create structured request
    sr = StructuredRequest(
        raw_message_id=raw.id,
        customer_name=result.customer_name,
        policy_hint=result.policy_hint,
        intent=result.intent,
        urgency=result.urgency,
        client_reply_draft=client_reply,
        carrier_email_draft=carrier_email,
        ams_note_draft=ams_note,
    )
    session.add(sr)
    session.flush()

    # 5. Audit log
    audit = AuditLog(
        structured_request_id=sr.id,
        action="created",
        actor="system",
        details=f"Ingested from {channel.value}: {sender}",
    )
    session.add(audit)
    session.commit()
    session.refresh(sr)

    return sr
