from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.schemas.action import Action
from app.schemas.finding import Pagination, Severity

AssignmentStatus = Literal["open", "in_progress", "done", "cancelled"]
WorkflowType = Literal["geocode_request", "notification_delivery"]


class AdminOption(BaseModel):
    id: UUID
    login: str = Field(min_length=1, max_length=320)


class AdminOptionPage(BaseModel):
    items: list[AdminOption]
    admin_timezone: str


class AssignmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    finding_id: str | None = Field(default=None, min_length=1, max_length=8192)
    workflow_type: WorkflowType | None = None
    workflow_key: str | None = Field(default=None, min_length=1, max_length=1024)
    entity_type: str | None = Field(default=None, min_length=1, max_length=64)
    entity_key: str | None = Field(default=None, min_length=1, max_length=1024)
    assigned_to_admin_id: UUID
    status: Literal["open", "in_progress"] = "open"
    due_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def task_identity(self) -> "AssignmentCreate":
        finding = self.finding_id is not None
        workflow = self.workflow_type is not None or self.workflow_key is not None
        if finding == workflow:
            raise ValueError("Provide either finding_id or a workflow identity")
        if workflow and (
            self.workflow_type is None
            or self.workflow_key is None
            or self.entity_type is None
            or self.entity_key is None
        ):
            raise ValueError("Workflow assignments require complete workflow and entity identity")
        if finding and (self.entity_type is not None or self.entity_key is not None):
            raise ValueError("Finding assignments derive entity identity from the finding")
        return self


class AssignmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    assigned_to_admin_id: UUID | None = None
    status: AssignmentStatus | None = None
    due_at: AwareDatetime | None = None
    snoozed_until: AwareDatetime | None = None

    @model_validator(mode="after")
    def patch_fields(self) -> "AssignmentUpdate":
        if not self.model_fields_set - {"version"}:
            raise ValueError("Provide at least one changed field")
        for field in ("assigned_to_admin_id", "status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class AssignmentLookup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    finding_id: str | None = Field(default=None, min_length=1, max_length=8192)
    workflow_type: WorkflowType | None = None
    workflow_key: str | None = Field(default=None, min_length=1, max_length=1024)

    @model_validator(mode="after")
    def task_identity(self) -> "AssignmentLookup":
        finding = self.finding_id is not None
        workflow = self.workflow_type is not None or self.workflow_key is not None
        if finding == workflow or workflow != (
            self.workflow_type is not None and self.workflow_key is not None
        ):
            raise ValueError("Provide one complete assignment identity")
        return self


class Assignment(BaseModel):
    id: UUID
    finding_id: str | None
    workflow_type: WorkflowType | None
    workflow_key: str | None
    entity_type: str
    entity_key: str
    assigned_to: AdminOption
    assigned_by_subject: str
    status: AssignmentStatus
    due_at: datetime | None
    snoozed_until: datetime | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    version: int


InboxKind = Literal["assignment", "finding", "geocode_request", "notification_delivery"]
InboxScope = Literal["all", "mine", "unassigned"]
InboxAttention = Literal["all", "critical", "due_today", "overdue", "snoozed"]


class InboxFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: InboxScope = "all"
    attention: InboxAttention = "all"
    kind: InboxKind | None = None
    entity_type: str | None = Field(default=None, min_length=1, max_length=64)
    page: int = Field(default=1, ge=1, le=100_000)
    page_size: int = Field(default=25, ge=1, le=100)


class InboxItem(BaseModel):
    id: str = Field(min_length=1, max_length=8192)
    kind: InboxKind
    title: str = Field(min_length=1, max_length=500)
    summary: str = Field(min_length=1, max_length=5000)
    entity_type: str = Field(min_length=1, max_length=64)
    entity_key: str = Field(min_length=1, max_length=1024)
    entity_name: str = Field(min_length=1, max_length=500)
    organization_name: str | None = Field(default=None, max_length=500)
    entity_action: Action | None = None
    severity: Severity | None
    status: str = Field(min_length=1, max_length=64)
    workflow_status: str | None = Field(default=None, max_length=64)
    candidate_count: int | None = Field(default=None, ge=0)
    occurred_at: datetime
    due_at: datetime | None
    snoozed_until: datetime | None
    finding_snoozed_until: datetime | None
    is_overdue: bool
    due_today: bool
    assignment: Assignment | None
    href: str


class InboxCounts(BaseModel):
    critical: int = Field(ge=0)
    mine: int = Field(ge=0)
    unassigned: int = Field(ge=0)
    due_today: int = Field(ge=0)
    overdue: int = Field(ge=0)
    snoozed: int = Field(ge=0)


class InboxPage(BaseModel):
    items: list[InboxItem]
    counts: InboxCounts
    pagination: Pagination
    observed_at: datetime
    admin_timezone: str
