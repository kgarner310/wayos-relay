"""Web UI routes — server-rendered Jinja2 templates."""
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.database import get_session
from app.models import StructuredRequest

router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def inbox_list(request: Request, session: Session = Depends(get_session)):
    stmt = (
        select(StructuredRequest)
        .order_by(
            StructuredRequest.urgency_score.desc(),  # type: ignore[union-attr]
            StructuredRequest.created_at.desc(),  # type: ignore[union-attr]
        )
    )
    requests_list = session.exec(stmt).all()
    for sr in requests_list:
        _ = sr.raw_message
        _ = sr.draft_artifacts

    return templates.TemplateResponse("inbox.html", {
        "request": request,
        "requests": requests_list,
        "json_loads": json.loads,
    })


@router.get("/request/{request_id}", response_class=HTMLResponse)
def request_detail(request_id: str, request: Request, session: Session = Depends(get_session)):
    sr = session.get(StructuredRequest, request_id)
    if not sr:
        return HTMLResponse("<h1>Not Found</h1>", status_code=404)

    _ = sr.raw_message
    _ = sr.draft_artifacts
    _ = sr.approval_events
    _ = sr.outbound_messages

    entities = json.loads(sr.extracted_entities_json)
    checklist = json.loads(sr.draft_artifacts.internal_checklist) if sr.draft_artifacts else []

    return templates.TemplateResponse("detail.html", {
        "request": request,
        "sr": sr,
        "entities": entities,
        "checklist": checklist,
    })
