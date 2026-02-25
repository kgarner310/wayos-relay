"""Twilio inbound SMS webhook with optional signature verification."""
import json
import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from sqlmodel import Session

from app.config import settings
from app.database import get_session
from app.ingest import ingest_message
from app.models import ChannelType

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = logging.getLogger(__name__)


def _verify_twilio_signature(request: Request, form_data: dict) -> None:
    """Validate that the request actually came from Twilio.

    Only runs when TWILIO_VERIFY_SIGNATURE=true in .env.
    Requires the `twilio` package.
    """
    if not settings.twilio_verify_signature:
        return  # verification disabled (demo mode)

    if not settings.twilio_auth_token:
        log.warning("Twilio signature verification enabled but no auth token configured")
        raise HTTPException(403, "Twilio auth token not configured")

    try:
        from twilio.request_validator import RequestValidator
    except ImportError:
        log.error("twilio package not installed — cannot verify signature")
        raise HTTPException(500, "twilio package required for signature verification")

    validator = RequestValidator(settings.twilio_auth_token)

    # Reconstruct the full URL Twilio used to call us
    url = str(request.url)
    # If behind a reverse proxy, use the configured base URL instead
    if settings.app_base_url and not url.startswith(settings.app_base_url):
        url = f"{settings.app_base_url.rstrip('/')}{request.url.path}"

    signature = request.headers.get("X-Twilio-Signature", "")

    if not validator.validate(url, form_data, signature):
        log.warning("Invalid Twilio signature for request to %s", request.url.path)
        raise HTTPException(403, "Invalid Twilio signature")


@router.post("/twilio/sms")
async def twilio_inbound_sms(
    request: Request,
    From: str = Form(...),
    Body: str = Form(...),
    MessageSid: str = Form(""),
    To: str = Form(""),
    NumMedia: str = Form("0"),
    session: Session = Depends(get_session),
) -> Response:
    """
    Twilio POSTs here when an SMS arrives.
    Steps:
      1. Optionally verify Twilio signature
      2. Save as RawMessage(channel="sms")
      3. Run parse + draft generation pipeline
      4. Return empty TwiML (no auto-reply from webhook)
    """
    # Build form dict for signature verification
    form_dict = {
        "From": From,
        "Body": Body,
        "MessageSid": MessageSid,
        "To": To,
        "NumMedia": NumMedia,
    }

    _verify_twilio_signature(request, form_dict)

    log.info("Inbound SMS from %s (sid=%s): %s", From, MessageSid, Body[:80])

    raw_payload = json.dumps({
        "MessageSid": MessageSid,
        "From": From,
        "To": To,
        "NumMedia": NumMedia,
    })

    ingest_message(
        session,
        channel=ChannelType.sms,
        from_address=From,
        to_address=To,
        body=Body,
        raw_payload=raw_payload,
    )

    # Return empty TwiML — the actual reply is sent later after CSR approval
    twiml = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
    return Response(content=twiml, media_type="application/xml")
