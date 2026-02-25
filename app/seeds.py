"""Load seed data from seeds/sample_messages.json into the database."""
import json
from pathlib import Path

from sqlmodel import Session

from app.database import engine
from app.ingest import ingest_message
from app.models import ChannelType

SEED_FILE = Path(__file__).parent.parent / "seeds" / "sample_messages.json"


def load_seeds() -> int:
    """Load sample messages. Returns count of messages ingested."""
    if not SEED_FILE.exists():
        return 0

    with open(SEED_FILE) as f:
        messages = json.load(f)

    count = 0
    with Session(engine) as session:
        for msg in messages:
            channel = ChannelType(msg.get("channel", "manual"))
            ingest_message(
                session,
                channel=channel,
                from_address=msg["sender"],
                subject=msg.get("subject") or None,
                body=msg["body"],
                raw_payload=json.dumps(msg),
            )
            count += 1

    return count


if __name__ == "__main__":
    from app.database import create_db_and_tables

    create_db_and_tables()
    n = load_seeds()
    print(f"Loaded {n} seed messages.")
