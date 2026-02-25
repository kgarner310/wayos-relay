"""Tests for digest generation and rendering."""
import json
from datetime import datetime, timezone

import pytest
from sqlmodel import Session, create_engine, select, SQLModel

from app.digest import (
    _group_by_intent,
    render_digest_html,
    generate_digest,
)
from app.models import (
    DigestRun,
    DigestItem,
    IntentCategory,
    MessageStatus,
    RawMessage,
    StructuredRequest,
    ChannelType,
)


@pytest.fixture
def session():
    """In-memory SQLite session for testing."""
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as sess:
        yield sess


def _make_request(
    session: Session,
    intent: IntentCategory = IntentCategory.coi,
    urgency: int = 50,
    confidence: int = 80,
    customer_name: str = "Test Customer",
    policy_number: str = "POL-001",
    status: MessageStatus = MessageStatus.review,
) -> StructuredRequest:
    """Helper to create a RawMessage + StructuredRequest pair."""
    raw = RawMessage(
        channel=ChannelType.email,
        from_address="test@example.com",
        subject="Test subject",
        body_text="Test body",
        raw_payload="{}",
        status=status,
    )
    session.add(raw)
    session.flush()

    sr = StructuredRequest(
        raw_message_id=raw.id,
        intent_category=intent,
        extracted_entities_json=json.dumps({
            "customer_name": customer_name,
            "policy_number": policy_number,
        }),
        urgency_score=urgency,
        confidence_score=confidence,
    )
    session.add(sr)
    session.flush()
    return sr


# ======================================================================
# Group by intent
# ======================================================================


class TestGroupByIntent:
    def test_empty_list(self) -> None:
        groups = _group_by_intent([])
        assert groups == {}

    def test_single_intent(self, session: Session) -> None:
        sr = _make_request(session, intent=IntentCategory.coi)
        groups = _group_by_intent([sr])
        assert "coi" in groups
        assert len(groups["coi"]) == 1

    def test_multiple_intents(self, session: Session) -> None:
        sr1 = _make_request(session, intent=IntentCategory.coi)
        sr2 = _make_request(session, intent=IntentCategory.vehicle_add)
        sr3 = _make_request(session, intent=IntentCategory.coi)
        groups = _group_by_intent([sr1, sr2, sr3])
        assert len(groups["coi"]) == 2
        assert len(groups["vehicle_add"]) == 1

    def test_preserves_order_within_group(self, session: Session) -> None:
        sr1 = _make_request(session, intent=IntentCategory.coi, urgency=90)
        sr2 = _make_request(session, intent=IntentCategory.coi, urgency=30)
        groups = _group_by_intent([sr1, sr2])
        # Order should be preserved (sr1 first since it was first in input)
        assert groups["coi"][0].urgency_score == 90
        assert groups["coi"][1].urgency_score == 30


# ======================================================================
# Render digest HTML
# ======================================================================


class TestRenderDigestHTML:
    def test_empty_digest(self) -> None:
        html = render_digest_html([], period_label="morning")
        assert "ServiceInbox" in html
        assert "Morning" in html
        assert "0 items" in html

    def test_includes_period_label(self) -> None:
        html = render_digest_html([], period_label="afternoon")
        assert "Afternoon" in html

    def test_includes_timestamp(self) -> None:
        ts = datetime(2026, 2, 25, 14, 30, 0, tzinfo=timezone.utc)
        html = render_digest_html([], generated_at=ts)
        assert "February 25, 2026" in html

    def test_includes_category_sections(self, session: Session) -> None:
        sr1 = _make_request(session, intent=IntentCategory.coi)
        sr2 = _make_request(session, intent=IntentCategory.vehicle_add)
        html = render_digest_html([sr1, sr2])
        assert "Certificates of Insurance" in html
        assert "Vehicle Add Endorsements" in html

    def test_includes_customer_name(self, session: Session) -> None:
        sr = _make_request(session, customer_name="Alice Johnson")
        html = render_digest_html([sr])
        assert "Alice Johnson" in html

    def test_includes_policy_number(self, session: Session) -> None:
        sr = _make_request(session, policy_number="BOP-2024-1234")
        html = render_digest_html([sr])
        assert "BOP-2024-1234" in html

    def test_urgent_banner_present(self, session: Session) -> None:
        sr = _make_request(session, urgency=85)
        html = render_digest_html([sr])
        assert "urgent" in html.lower()
        assert "1 urgent item" in html

    def test_no_urgent_banner_when_all_low(self, session: Session) -> None:
        sr = _make_request(session, urgency=30)
        html = render_digest_html([sr])
        assert "urgent item" not in html

    def test_item_count_in_summary(self, session: Session) -> None:
        sr1 = _make_request(session, intent=IntentCategory.coi)
        sr2 = _make_request(session, intent=IntentCategory.coi)
        sr3 = _make_request(session, intent=IntentCategory.driver_add)
        html = render_digest_html([sr1, sr2, sr3])
        assert "3 items" in html

    def test_urgency_color_coding(self, session: Session) -> None:
        sr_high = _make_request(session, urgency=85)
        sr_med = _make_request(session, urgency=50)
        sr_low = _make_request(session, urgency=20)
        html = render_digest_html([sr_high, sr_med, sr_low])
        # Red for high, yellow for medium, green for low
        assert "#e74c3c" in html  # high urgency
        assert "#f39c12" in html  # medium urgency
        assert "#27ae60" in html  # low urgency


# ======================================================================
# Generate digest (full pipeline)
# ======================================================================


class TestGenerateDigest:
    def test_no_pending_returns_none(self, session: Session) -> None:
        result = generate_digest(session, period_label="morning")
        assert result is None

    def test_generates_digest_run(self, session: Session) -> None:
        _make_request(session, intent=IntentCategory.coi)
        _make_request(session, intent=IntentCategory.vehicle_add)
        session.commit()

        run = generate_digest(session, period_label="morning")
        assert run is not None
        assert run.item_count == 2
        assert run.period_label == "morning"
        assert run.html_snapshot != ""

    def test_creates_digest_items(self, session: Session) -> None:
        sr1 = _make_request(session, intent=IntentCategory.coi)
        sr2 = _make_request(session, intent=IntentCategory.vehicle_add)
        session.commit()

        run = generate_digest(session, period_label="test")
        assert run is not None

        items = session.exec(
            select(DigestItem).where(DigestItem.digest_run_id == run.id)
        ).all()
        assert len(items) == 2

    def test_stores_recipients(self, session: Session) -> None:
        _make_request(session)
        session.commit()

        run = generate_digest(
            session,
            period_label="test",
            recipient_emails=["a@test.com", "b@test.com"],
        )
        assert run is not None
        assert "a@test.com" in run.sent_to
        assert "b@test.com" in run.sent_to

    def test_skips_non_review_status(self, session: Session) -> None:
        _make_request(session, status=MessageStatus.review)
        _make_request(session, status=MessageStatus.sent)
        _make_request(session, status=MessageStatus.rejected)
        session.commit()

        run = generate_digest(session, period_label="test")
        assert run is not None
        assert run.item_count == 1

    def test_html_snapshot_is_valid_html(self, session: Session) -> None:
        _make_request(session)
        session.commit()

        run = generate_digest(session, period_label="test")
        assert run is not None
        assert run.html_snapshot.startswith("<!DOCTYPE html>")
        assert "</html>" in run.html_snapshot
