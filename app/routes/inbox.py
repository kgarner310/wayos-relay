"""Web UI routes — server-rendered Jinja2 templates."""
import json
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.database import get_session
from app.models import (
    DigestRun,
    IntentCategory,
    MessageStatus,
    RawMessage,
    StructuredRequest,
)

router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory="app/templates")


# ---------- Dashboard (home page) ----------

@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    # Pending items count
    pending_stmt = (
        select(StructuredRequest)
        .join(RawMessage, StructuredRequest.raw_message_id == RawMessage.id)
        .where(RawMessage.status == MessageStatus.review)
    )
    pending = list(session.exec(pending_stmt).all())

    # Group pending by intent
    by_intent: dict[str, int] = {}
    for sr in pending:
        key = sr.intent_category.value
        by_intent[key] = by_intent.get(key, 0) + 1

    # Urgent count
    urgent_count = sum(1 for sr in pending if sr.urgency_score >= 70)

    # Recent digests
    digest_stmt = (
        select(DigestRun)
        .order_by(DigestRun.generated_at.desc())  # type: ignore[union-attr]
        .limit(5)
    )
    recent_digests = list(session.exec(digest_stmt).all())

    # Total processed today (all statuses)
    all_stmt = select(StructuredRequest).order_by(
        StructuredRequest.created_at.desc()  # type: ignore[union-attr]
    )
    all_requests = list(session.exec(all_stmt).all())
    total = len(all_requests)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "pending_count": len(pending),
        "urgent_count": urgent_count,
        "total_count": total,
        "by_intent": by_intent,
        "recent_digests": recent_digests,
    })


# ---------- Inbox (full list with filters) ----------

@router.get("/inbox", response_class=HTMLResponse)
def inbox_list(
    request: Request,
    status: Optional[str] = Query(None),
    intent: Optional[str] = Query(None),
    sort: str = Query("urgency_desc"),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    stmt = select(StructuredRequest)

    # --- Filters ---
    if status:
        try:
            status_enum = MessageStatus(status)
            stmt = stmt.join(RawMessage).where(RawMessage.status == status_enum)
        except ValueError:
            pass

    if intent:
        try:
            intent_enum = IntentCategory(intent)
            stmt = stmt.where(StructuredRequest.intent_category == intent_enum)
        except ValueError:
            pass

    # --- Sort ---
    sort_map = {
        "urgency_desc": [
            StructuredRequest.urgency_score.desc(),   # type: ignore[union-attr]
            StructuredRequest.created_at.desc(),       # type: ignore[union-attr]
        ],
        "urgency_asc": [
            StructuredRequest.urgency_score.asc(),    # type: ignore[union-attr]
            StructuredRequest.created_at.desc(),       # type: ignore[union-attr]
        ],
        "newest": [StructuredRequest.created_at.desc()],   # type: ignore[union-attr]
        "oldest": [StructuredRequest.created_at.asc()],    # type: ignore[union-attr]
        "confidence_desc": [
            StructuredRequest.confidence_score.desc(),  # type: ignore[union-attr]
            StructuredRequest.created_at.desc(),        # type: ignore[union-attr]
        ],
    }
    order_clauses = sort_map.get(sort, sort_map["urgency_desc"])
    for clause in order_clauses:
        stmt = stmt.order_by(clause)

    requests_list = session.exec(stmt).all()
    for sr in requests_list:
        _ = sr.raw_message
        _ = sr.draft_artifacts

    all_statuses = [s.value for s in MessageStatus]
    all_intents = [i.value for i in IntentCategory]

    return templates.TemplateResponse("inbox.html", {
        "request": request,
        "requests": requests_list,
        "json_loads": json.loads,
        "current_status": status or "",
        "current_intent": intent or "",
        "current_sort": sort,
        "all_statuses": all_statuses,
        "all_intents": all_intents,
    })


# ---------- Digest history ----------

@router.get("/digests", response_class=HTMLResponse)
def digest_list(
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    stmt = select(DigestRun).order_by(DigestRun.generated_at.desc())  # type: ignore[union-attr]
    digests = list(session.exec(stmt).all())
    return templates.TemplateResponse("digests.html", {
        "request": request,
        "digests": digests,
    })


# ---------- Request detail ----------

@router.get("/request/{request_id}", response_class=HTMLResponse)
def request_detail(
    request_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    sr = session.get(StructuredRequest, request_id)
    if not sr:
        return HTMLResponse("<h1>Not Found</h1>", status_code=404)

    _ = sr.raw_message
    _ = sr.draft_artifacts
    _ = sr.approval_events
    _ = sr.outbound_messages

    entities = json.loads(sr.extracted_entities_json)
    checklist = json.loads(sr.draft_artifacts.internal_checklist) if sr.draft_artifacts else []

    timeline = _build_timeline_for_template(sr)

    return templates.TemplateResponse("detail.html", {
        "request": request,
        "sr": sr,
        "entities": entities,
        "checklist": checklist,
        "timeline": timeline,
    })


def _build_timeline_for_template(sr: StructuredRequest) -> list[dict]:
    """Build a sorted event timeline for the detail page template."""
    raw = sr.raw_message
    events: list[dict] = []

    if raw:
        events.append({
            "timestamp": raw.received_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "icon": "&#128232;",
            "label": "Message Received",
            "detail": f"Inbound {raw.channel.value.upper()} from {raw.from_address}",
        })

    events.append({
        "timestamp": sr.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "icon": "&#128269;",
        "label": "Classified",
        "detail": (
            f"Intent: {sr.intent_category.value.replace('_', ' ').title()}, "
            f"Urgency: {sr.urgency_score}, Confidence: {sr.confidence_score}%"
        ),
    })

    drafts = sr.draft_artifacts
    if drafts:
        events.append({
            "timestamp": drafts.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "icon": "&#128221;",
            "label": "Drafts Generated",
            "detail": "Client reply, carrier email, AMS note generated",
        })

    for ae in sr.approval_events:
        icon = "&#9989;" if ae.action.value == "approve" else "&#10060;"
        label = "Approved" if ae.action.value == "approve" else "Rejected"
        detail = f"By {ae.actor_name}"
        if ae.actor_email:
            detail += f" ({ae.actor_email})"
        if ae.edits_json:
            detail += " &mdash; drafts were edited before sending"
        events.append({
            "timestamp": ae.approved_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "icon": icon,
            "label": label,
            "detail": detail,
        })

    for om in sr.outbound_messages:
        events.append({
            "timestamp": om.sent_at.strftime("%Y-%m-%d %H:%M:%S UTC") if om.sent_at else "pending",
            "icon": "&#128228;",
            "label": f"Outbound ({om.kind.value.title()})",
            "detail": f"To: {om.to_address} via {om.transport.upper()}",
        })

    events.sort(key=lambda e: e["timestamp"])
    return events
