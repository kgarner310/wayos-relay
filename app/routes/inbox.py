"""Web UI routes — server-rendered Jinja2 templates."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.database import get_session
from app.models import AuditLog, StructuredRequest

router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def inbox_list(request: Request, session: Session = Depends(get_session)):
    stmt = (
        select(StructuredRequest)
        .order_by(StructuredRequest.urgency.desc(), StructuredRequest.created_at.desc())  # type: ignore[union-attr]
    )
    requests_list = session.exec(stmt).all()
    # Eagerly load raw_message for each
    for sr in requests_list:
        _ = sr.raw_message
    return templates.TemplateResponse("inbox.html", {
        "request": request,
        "requests": requests_list,
    })


@router.get("/request/{request_id}", response_class=HTMLResponse)
def request_detail(request_id: int, request: Request, session: Session = Depends(get_session)):
    sr = session.get(StructuredRequest, request_id)
    if not sr:
        return HTMLResponse("<h1>Not Found</h1>", status_code=404)
    _ = sr.raw_message  # eager load

    audit_stmt = (
        select(AuditLog)
        .where(AuditLog.structured_request_id == request_id)
        .order_by(AuditLog.created_at.asc())  # type: ignore[union-attr]
    )
    audit_logs = session.exec(audit_stmt).all()

    return templates.TemplateResponse("detail.html", {
        "request": request,
        "sr": sr,
        "audit_logs": audit_logs,
    })
