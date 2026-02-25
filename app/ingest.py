"""
Core ingestion pipeline: RawMessage -> parse -> generate artifacts -> persist.
Shared by webhook, IMAP poller, and simulate endpoint.
"""
import json

from sqlmodel import Session

from app.artifacts import (
    generate_ams_note,
    generate_carrier_email,
    generate_checklist,
    generate_client_reply,
)
from app.models import (
    ChannelType,
    DraftArtifacts,
    MessageStatus,
    RawMessage,
    StructuredRequest,
)
from app.parser import parse_message


def ingest_message(
    session: Session,
    *,
    channel: ChannelType,
    from_address: str,
    to_address: str = "",
    subject: str | None = None,
    body: str,
    raw_payload: str = "",
) -> StructuredRequest:
    """Full pipeline: store raw -> parse -> generate drafts -> return StructuredRequest."""

    # 1. Store raw message
    raw = RawMessage(
        channel=channel,
        from_address=from_address,
        to_address=to_address,
        subject=subject,
        body_text=body,
        status=MessageStatus.new,
    )
    session.add(raw)
    session.flush()

    # 2. Parse
    result = parse_message(body, subject=subject or "", sender=from_address)

    # 3. Update raw status
    raw.status = MessageStatus.parsed
    session.add(raw)

    # 4. Create structured request
    sr = StructuredRequest(
        raw_message_id=raw.id,
        intent_category=result.intent,
        extracted_entities_json=json.dumps(result.entities),
        urgency_score=result.urgency_score,
        confidence_score=result.confidence_score,
    )
    session.add(sr)
    session.flush()

    # 5. Generate drafts
    name = result.entities.get("customer_name", "")
    policy = result.entities.get("policy_number", "")

    client_reply = generate_client_reply(result.intent, name, policy)
    carrier_email = generate_carrier_email(result.intent, name, policy, body)
    ams_note = generate_ams_note(
        result.intent, name, policy, channel.value, body, result.entities
    )
    checklist = generate_checklist(result.intent)

    drafts = DraftArtifacts(
        structured_request_id=sr.id,
        client_reply_draft=client_reply,
        carrier_email_draft=carrier_email,
        ams_note_draft=ams_note,
        internal_checklist=checklist,
    )
    session.add(drafts)

    # 6. Move to review
    raw.status = MessageStatus.review
    session.add(raw)

    session.commit()
    session.refresh(sr)

    return sr
