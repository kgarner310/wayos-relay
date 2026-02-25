import enum
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel, Relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------- Enums ----------

class ChannelType(str, enum.Enum):
    sms = "sms"
    email = "email"
    manual = "manual"  # simulate button


class IntentCategory(str, enum.Enum):
    coi = "coi"
    vehicle_add = "vehicle_add"
    driver_add = "driver_add"
    address_change = "address_change"
    payroll_change = "payroll_change"
    coverage_change = "coverage_change"
    other = "other"


class RequestStatus(str, enum.Enum):
    new = "new"
    reviewed = "reviewed"
    approved = "approved"
    rejected = "rejected"
    sent = "sent"


# ---------- Tables ----------

class RawMessage(SQLModel, table=True):
    __tablename__ = "raw_messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    channel: ChannelType
    sender: str  # phone number or email address
    subject: str = ""
    body: str
    raw_payload: str = ""  # full original data (JSON for SMS, headers for email)
    received_at: datetime = Field(default_factory=utcnow)

    # One-to-one relationship
    structured_request: Optional["StructuredRequest"] = Relationship(back_populates="raw_message")


class StructuredRequest(SQLModel, table=True):
    __tablename__ = "structured_requests"

    id: Optional[int] = Field(default=None, primary_key=True)
    raw_message_id: int = Field(foreign_key="raw_messages.id", unique=True)
    customer_name: str = ""
    policy_hint: str = ""  # any policy number fragment detected
    intent: IntentCategory = IntentCategory.other
    urgency: int = Field(default=3, ge=1, le=5)  # 1=low, 5=critical
    status: RequestStatus = RequestStatus.new

    # Generated drafts
    client_reply_draft: str = ""
    carrier_email_draft: str = ""
    ams_note_draft: str = ""

    # Approval metadata
    approved_by: str = ""
    approved_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    raw_message: Optional[RawMessage] = Relationship(back_populates="structured_request")
    audit_logs: list["AuditLog"] = Relationship(back_populates="structured_request")


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    structured_request_id: int = Field(foreign_key="structured_requests.id")
    action: str  # created, approved, rejected, sent, edited
    actor: str = "system"
    details: str = ""
    created_at: datetime = Field(default_factory=utcnow)

    structured_request: Optional[StructuredRequest] = Relationship(back_populates="audit_logs")
