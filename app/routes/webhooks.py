"""Twilio inbound SMS webhook."""
import json

from fastapi import APIRouter, Depends, Form, Response
from sqlmodel import Session

from app.database import get_session
from app.ingest import ingest_message
from app.models import ChannelType

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/twilio/sms")
def twilio_inbound_sms(
    From: str = Form(...),
    Body: str = Form(...),
    MessageSid: str = Form(""),
    To: str = Form(""),
    session: Session = Depends(get_session),
) -> Response:
    """
    Twilio sends a POST here when an SMS arrives.
    We ingest, then return empty TwiML (no auto-reply from webhook).
    """
    raw_payload = json.dumps({"MessageSid": MessageSid, "From": From, "To": To})

    ingest_message(
        session,
        channel=ChannelType.sms,
        from_address=From,
        to_address=To,
        body=Body,
        raw_payload=raw_payload,
    )

    twiml = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
    return Response(content=twiml, media_type="application/xml")
