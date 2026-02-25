"""IMAP email polling service.

Connects to an IMAP mailbox, fetches UNSEEN emails, extracts metadata
(including attachment info), and runs each through the ingest pipeline.
"""
import email
import imaplib
import json
import logging
from email.header import decode_header
from email.message import Message
from email.utils import parseaddr

from sqlmodel import Session

from app.config import settings
from app.ingest import ingest_message
from app.models import ChannelType

log = logging.getLogger(__name__)


def _decode_header_value(value: str) -> str:
    """Decode an RFC 2047 encoded header into a plain string."""
    parts = decode_header(value)
    decoded: list[str] = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _get_text_body(msg: Message) -> str:
    """Extract the plain-text body from a MIME message."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            # Skip attachments — we only want inline text
            if "attachment" in disposition:
                continue
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


def _extract_attachments(msg: Message) -> list[dict]:
    """Extract attachment metadata (filename, size, content-type) without storing binary."""
    attachments: list[dict] = []
    if not msg.is_multipart():
        return attachments

    for part in msg.walk():
        disposition = str(part.get("Content-Disposition", ""))
        if "attachment" not in disposition and "inline" not in disposition:
            continue
        # Skip text/plain and text/html body parts
        if part.get_content_type() in ("text/plain", "text/html") and "attachment" not in disposition:
            continue

        filename = part.get_filename()
        if filename:
            filename = _decode_header_value(filename)
        else:
            filename = f"unnamed.{part.get_content_subtype()}"

        payload = part.get_payload(decode=True)
        size = len(payload) if payload else 0

        attachments.append({
            "filename": filename,
            "size": size,
            "content_type": part.get_content_type(),
        })

    return attachments


def _parse_address(header_value: str) -> str:
    """Extract email address from a header like 'Name <email@example.com>'."""
    if not header_value:
        return ""
    _, addr = parseaddr(header_value)
    return addr or header_value


def poll_mailbox(session: Session) -> int:
    """Connect to IMAP, fetch UNSEEN emails, ingest each through the pipeline.

    Returns the number of messages successfully ingested.
    """
    if not settings.imap_configured:
        log.debug("IMAP not configured — skipping poll")
        return 0

    count = 0
    mail: imaplib.IMAP4_SSL | None = None
    try:
        mail = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port)
        mail.login(settings.imap_user, settings.imap_password)
        mail.select(settings.imap_folder)

        status, data = mail.search(None, "UNSEEN")
        if status != "OK" or not data[0]:
            log.debug("No unseen emails")
            return 0

        msg_ids = data[0].split()
        log.info("Found %d unseen email(s)", len(msg_ids))

        for msg_id in msg_ids:
            try:
                status, msg_data = mail.fetch(msg_id, "(RFC822)")
                if status != "OK":
                    log.warning("Failed to fetch msg %s", msg_id)
                    continue

                raw_bytes = msg_data[0][1]
                msg = email.message_from_bytes(raw_bytes)

                from_addr = _parse_address(_decode_header_value(msg.get("From", "")))
                to_addr = _parse_address(_decode_header_value(msg.get("To", "")))
                subject = _decode_header_value(msg.get("Subject", ""))
                body = _get_text_body(msg)

                # Extract attachment metadata
                attachments = _extract_attachments(msg)
                attachments_json = json.dumps(attachments) if attachments else None

                # Run through ingest pipeline
                sr = ingest_message(
                    session,
                    channel=ChannelType.email,
                    from_address=from_addr,
                    to_address=to_addr,
                    subject=subject,
                    body=body,
                    raw_payload="",
                    attachments_json=attachments_json,
                )

                log.info(
                    "Ingested email from %s — subject=%s, intent=%s, id=%s",
                    from_addr, subject[:60], sr.intent_category.value, sr.id[:8],
                )

                # Mark as seen
                mail.store(msg_id, "+FLAGS", "\\Seen")
                count += 1

            except Exception:
                log.exception("Failed to process email msg_id=%s", msg_id)

    except Exception:
        log.exception("IMAP connection/poll failed")
    finally:
        if mail:
            try:
                mail.logout()
            except Exception:
                pass

    return count
