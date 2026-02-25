"""IMAP email polling service."""
import email
import imaplib
import logging
from email.header import decode_header

from app.config import settings

log = logging.getLogger(__name__)


def _decode_header_value(value: str) -> str:
    parts = decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _get_text_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return ""


def fetch_new_emails() -> list[dict]:
    """
    Connect to IMAP, fetch UNSEEN emails, mark them SEEN, return list of dicts.
    Each dict: {"sender", "subject", "body", "raw_headers"}
    """
    if not settings.imap_configured:
        log.warning("IMAP not configured — skipping poll")
        return []

    results: list[dict] = []
    try:
        mail = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port)
        mail.login(settings.imap_user, settings.imap_password)
        mail.select(settings.imap_folder)

        status, data = mail.search(None, "UNSEEN")
        if status != "OK" or not data[0]:
            mail.logout()
            return []

        for msg_id in data[0].split():
            status, msg_data = mail.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            sender = _decode_header_value(msg.get("From", ""))
            subject = _decode_header_value(msg.get("Subject", ""))
            body = _get_text_body(msg)

            results.append({
                "sender": sender,
                "subject": subject,
                "body": body,
                "raw_headers": str(msg.items())[:2000],
            })

            # Mark as seen
            mail.store(msg_id, "+FLAGS", "\\Seen")

        mail.logout()
    except Exception:
        log.exception("IMAP fetch failed")

    return results
