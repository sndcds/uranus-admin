"""Strict source contract and authenticated notification API contracts."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.schemas.finding import Pagination

Locale = Literal["de", "da", "en"]
NotificationType = Literal["unpublished_upcoming_event", "quality_finding"]
NotificationStatus = Literal["pending", "active", "resolved", "suppressed", "expired"]
DeliveryKind = Literal["initial", "reminder", "escalation", "digest", "test"]
DeliveryStatus = Literal["queued", "sending", "sent", "failed", "permanent_failure", "cancelled"]


class StrictConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class NotificationRecipient(StrictConfig):
    email: EmailStr
    locale: Locale = "de"
    enabled: bool = True


class ReminderConfig(StrictConfig):
    enabled: bool = False
    days_after: int = Field(default=7, ge=1, le=90)


class UnpublishedConfig(StrictConfig):
    enabled: bool = False
    days_before: int = Field(default=14, ge=1, le=365)
    reminder: ReminderConfig = Field(default_factory=ReminderConfig)


class QualityConfig(StrictConfig):
    enabled: bool = False
    minimum_severity: Literal["info", "warning", "error"] = "warning"
    delivery: Literal["daily_digest"] = "daily_digest"


class NotificationEvents(StrictConfig):
    unpublished_upcoming_events: UnpublishedConfig = Field(default_factory=UnpublishedConfig)
    quality_findings: QualityConfig = Field(default_factory=QualityConfig)


class NotificationConfig(StrictConfig):
    version: Literal[1]
    recipients: list[NotificationRecipient] = Field(max_length=100)
    events: NotificationEvents

    @field_validator("version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Version must be an integer")
        return value

    @model_validator(mode="after")
    def unique_recipients(self) -> "NotificationConfig":
        addresses = [str(item.email).casefold() for item in self.recipients]
        if len(addresses) != len(set(addresses)):
            raise ValueError("Duplicate recipient")
        return self


class NotificationPayload(BaseModel):
    """Small, typed rendering/audit snapshot; never a raw source row or finding.message."""

    organization_name: str
    entity_name: str
    entity_type: str
    entity_key: str
    action_path: str
    event_status: Literal["draft", "review"] | None = None
    next_date: str | None = None
    days_until: int | None = None
    stage: int = 0
    episode: int = Field(default=1, ge=1)
    rule: str | None = None
    finding_id: str | None = None
    severity: str | None = None
    field: str | None = None
    relevance: list[str] = Field(default_factory=list)
    priority: Literal["urgent", "important", "improvement", "internal"] = "improvement"


class NotificationSummary(BaseModel):
    id: UUID
    notification_type: NotificationType
    organization_id: UUID
    entity_type: str | None
    entity_key: str | None
    entity_name: str | None
    finding_id: str | None
    rule: str | None
    status: NotificationStatus
    payload: NotificationPayload
    first_detected_at: datetime
    last_detected_at: datetime
    resolved_at: datetime | None
    expired_at: datetime | None


class NotificationDelivery(BaseModel):
    id: UUID
    organization_id: UUID
    recipient: str
    locale: Locale
    delivery_kind: DeliveryKind
    status: DeliveryStatus
    subject: str | None
    message_fingerprint: str
    attempt_count: int
    queued_at: datetime | None
    sending_at: datetime | None
    sent_at: datetime | None
    next_attempt_at: datetime | None
    last_error: str | None
    provider_message_id: str | None


class NotificationDetail(NotificationSummary):
    deliveries: list[NotificationDelivery]
    delivery_enabled: bool


class DeliveryDetail(NotificationDelivery):
    notifications: list[NotificationSummary]


class ConfigIssue(BaseModel):
    organization_id: UUID
    organization_name: str
    code: Literal["invalid_config"] = "invalid_config"


class NotificationHealth(BaseModel):
    delivery_enabled: bool
    source_capability: bool
    config_issues: list[ConfigIssue]


class NotificationCounts(BaseModel):
    active: int
    queued: int
    sent_today: int
    failed: int


class NotificationPage(BaseModel):
    items: list[NotificationSummary]
    pagination: Pagination
    summary: NotificationCounts
    health: NotificationHealth


class NotificationPreview(BaseModel):
    subject: str
    text: str
    html: str
    locale: Locale
    notification_ids: list[UUID]
    delivery_enabled: bool
