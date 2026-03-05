"""Twilio SMS helpers."""
import logging

from app.config import settings

log = logging.getLogger(__name__)


def send_sms(to: str, body: str) -> bool:
    """Send an outbound SMS via Twilio. Returns True on success."""
    if not settings.twilio_configured:
        log.warning("Twilio not configured — skipping SMS to %s", to)
        return False

    try:
        from twilio.rest import Client

        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        message = client.messages.create(
            body=body,
            from_=settings.twilio_phone_number,
            to=to,
        )
        log.info("SMS sent to %s: sid=%s", to, message.sid)
        return True
    except Exception:
        log.exception("Failed to send SMS to %s", to)
        return False
