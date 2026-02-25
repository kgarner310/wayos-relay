#!/usr/bin/env python
"""Standalone IMAP email poller.

Runs in a loop, polling the configured IMAP mailbox every N seconds
(default 30).  Each new email is ingested through the full pipeline
(parse → draft → status=review) so it appears in the web UI.

Usage:
    python poller.py

Environment:
    All settings come from .env via pydantic-settings (see app/config.py).
    Set IMAP_HOST, IMAP_USER, IMAP_PASSWORD at minimum.
"""
import logging
import signal
import sys
import time

from app.config import settings
from app.database import create_db_and_tables, engine
from app.services.email_ingest import poll_mailbox

from sqlmodel import Session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
log = logging.getLogger("poller")

_running = True


def _handle_signal(signum: int, frame: object) -> None:
    global _running
    log.info("Received signal %d — shutting down", signum)
    _running = False


def main() -> None:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # Ensure DB tables exist (same as server startup)
    create_db_and_tables()

    interval = settings.imap_poll_interval_seconds

    if not settings.imap_configured:
        log.error(
            "IMAP not configured. Set IMAP_HOST, IMAP_USER, and IMAP_PASSWORD "
            "in .env before running the poller."
        )
        sys.exit(1)

    log.info(
        "Starting IMAP poller — host=%s user=%s folder=%s interval=%ds",
        settings.imap_host,
        settings.imap_user,
        settings.imap_folder,
        interval,
    )

    while _running:
        try:
            with Session(engine) as session:
                count = poll_mailbox(session)
                if count:
                    log.info("Ingested %d new email(s) this cycle", count)
        except Exception:
            log.exception("Poller cycle error")

        # Sleep in small increments so we can respond to signals quickly
        for _ in range(interval):
            if not _running:
                break
            time.sleep(1)

    log.info("Poller stopped")


if __name__ == "__main__":
    main()
