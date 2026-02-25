import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())


# ---------- Enums ----------

class ChannelType(str, enum.Enum):
    sms = "sms"
    email = "email"
    manual = "manual"


class IntentCategory(str, enum.Enum):
    coi = "coi"
    vehicle_add = "vehicle_add"
    driver_add = "driver_add"
    address_change = "address_change"
    payroll_change = "payroll_change"
    coverage_change = "coverage_change"
    other = "other"


class MessageStatus(str, enum.Enum):
    new = "new"
    parsed = "parsed"
    review = "review"
    approved = "approved"
    sent = "sent"
    rejected = "rejected"
    error = "error"


class ApprovalAction(str, enum.Enum):
    approve = "approve"
    reject = "reject"


class OutboundKind(str, enum.Enum):
    client = "client"
    carrier = "carrier"


# ---------- Tables ----------

class RawMessage(SQLModel, table=True):
    __tablename__ = "raw_messages"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    channel: ChannelType
    from_address: str
    to_address: str = ""
    subject: Optional[str] = None
    body_text: str
    received_at: datetime = Field(default_factory=utcnow)
    attachments_json: Optional[str] = None
    status: MessageStatus = MessageStatus.new

    structured_request: Optional["StructuredRequest"] = Relationship(
        back_populates="raw_message"
    )


class StructuredRequest(SQLModel, table=True):
    __tablename__ = "structured_requests"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    raw_message_id: str = Field(foreign_key="raw_messages.id", unique=True)
    intent_category: IntentCategory = IntentCategory.other
    extracted_entities_json: str = "{}"
    urgency_score: int = Field(default=30, ge=0, le=100)
    confidence_score: int = Field(default=50, ge=0, le=100)
    created_at: datetime = Field(default_factory=utcnow)

    raw_message: Optional[RawMessage] = Relationship(back_populates="structured_request")
    draft_artifacts: Optional["DraftArtifacts"] = Relationship(
        back_populates="structured_request"
    )
    approval_events: list["ApprovalEvent"] = Relationship(back_populates="structured_request")
    outbound_messages: list["OutboundMessage"] = Relationship(back_populates="structured_request")


class DraftArtifacts(SQLModel, table=True):
    __tablename__ = "draft_artifacts"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    structured_request_id: str = Field(foreign_key="structured_requests.id", unique=True)
    client_reply_draft: str = ""
    carrier_email_draft: str = ""
    ams_note_draft: str = ""
    internal_checklist: str = "[]"  # JSON array
    created_at: datetime = Field(default_factory=utcnow)

    structured_request: Optional[StructuredRequest] = Relationship(
        back_populates="draft_artifacts"
    )


class ApprovalEvent(SQLModel, table=True):
    __tablename__ = "approval_events"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    structured_request_id: str = Field(foreign_key="structured_requests.id")
    action: ApprovalAction
    actor_name: str = ""
    actor_email: str = ""
    approved_at: datetime = Field(default_factory=utcnow)
    edits_json: Optional[str] = None

    structured_request: Optional[StructuredRequest] = Relationship(
        back_populates="approval_events"
    )


class OutboundMessage(SQLModel, table=True):
    __tablename__ = "outbound_messages"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    structured_request_id: str = Field(foreign_key="structured_requests.id")
    kind: OutboundKind
    to_address: str
    subject: str = ""
    body: str = ""
    sent_at: Optional[datetime] = None
    transport: str = "smtp"
    result_json: str = "{}"

    structured_request: Optional[StructuredRequest] = Relationship(
        back_populates="outbound_messages"
    )


# ---------- Digest Tables ----------

class DigestRun(SQLModel, table=True):
    """A single digest generation run (e.g. 8am batch)."""
    __tablename__ = "digest_runs"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    generated_at: datetime = Field(default_factory=utcnow)
    period_label: str = ""  # "morning", "midday", "afternoon", or "manual"
    item_count: int = 0
    sent_to: str = ""  # comma-separated emails that received this digest
    html_snapshot: str = ""  # rendered HTML for archive/reprint


class DigestItem(SQLModel, table=True):
    """Links a StructuredRequest into a specific DigestRun."""
    __tablename__ = "digest_items"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    digest_run_id: str = Field(foreign_key="digest_runs.id")
    structured_request_id: str = Field(foreign_key="structured_requests.id")
