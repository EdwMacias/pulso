from datetime import UTC, date, datetime
from enum import Enum
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Priority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class TaskStatus(str, Enum):
    pending = "pending"
    completed = "completed"
    cancelled = "cancelled"


class Recurrence(str, Enum):
    none = "none"
    daily = "daily"
    weekly = "weekly"


class ReminderStatus(str, Enum):
    active = "active"
    cancelled = "cancelled"


class ResponseMode(str, Enum):
    text = "text"
    audio = "audio"
    both = "both"


def valid_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("unknown IANA timezone") from exc
    return value


class UserOut(ORMModel):
    id: str
    email: EmailStr
    email_verified_at: datetime | None
    timezone: str


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class AuthResponse(BaseModel):
    user: UserOut
    csrf_token: str


class RegisterResponse(AuthResponse):
    verification_required: bool


class EmailIn(BaseModel):
    email: EmailStr


class TokenIn(BaseModel):
    token: str = Field(min_length=20, max_length=512)


class ResetPasswordIn(TokenIn):
    password: str = Field(min_length=12, max_length=128)


class MessageResponse(BaseModel):
    message: str


class PreferencesOut(BaseModel):
    timezone: str
    response_mode: ResponseMode


class PreferencesPatch(BaseModel):
    timezone: str | None = None
    response_mode: ResponseMode | None = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("timezone cannot be null")
        return valid_timezone(value)

    @field_validator("response_mode")
    @classmethod
    def response_mode_not_null(cls, value: ResponseMode | None) -> ResponseMode:
        if value is None:
            raise ValueError("response_mode cannot be null")
        return value


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    priority: Priority = Priority.medium
    status: TaskStatus = TaskStatus.pending


class TaskPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    priority: Priority | None = None
    status: TaskStatus | None = None

    @field_validator("title", "priority", "status")
    @classmethod
    def required_fields_not_null(cls, value):
        if value is None:
            raise ValueError("field cannot be null")
        return value


class TaskOut(ORMModel):
    id: str
    title: str
    description: str | None
    priority: Priority
    status: TaskStatus
    created_at: datetime
    completed_at: datetime | None


class ReminderCreate(BaseModel):
    task_id: str
    scheduled_at: datetime
    timezone: str
    recurrence: Recurrence = Recurrence.none

    _timezone = field_validator("timezone")(valid_timezone)

    @field_validator("scheduled_at")
    @classmethod
    def require_offset(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("scheduled_at must include a UTC offset")
        return value.astimezone(UTC)


class ReminderPatch(BaseModel):
    scheduled_at: datetime | None = None
    timezone: str | None = None
    recurrence: Recurrence | None = None
    status: ReminderStatus | None = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("timezone cannot be null")
        return valid_timezone(value)

    @field_validator("recurrence", "status")
    @classmethod
    def enum_fields_not_null(cls, value):
        if value is None:
            raise ValueError("field cannot be null")
        return value

    @field_validator("scheduled_at")
    @classmethod
    def require_offset(cls, value: datetime | None) -> datetime | None:
        if value is None:
            raise ValueError("scheduled_at cannot be null")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("scheduled_at must include a UTC offset")
        return value.astimezone(UTC)


class ReminderOut(BaseModel):
    id: str
    task_id: str
    scheduled_at: datetime
    timezone: str
    recurrence: Recurrence
    status: ReminderStatus


class AnalyticsSummary(BaseModel):
    total_tasks: int
    pending_tasks: int
    completed_tasks: int
    completion_rate: float


class ChatIn(BaseModel):
    content: str = Field(min_length=1, max_length=10_000)


class ChatMessageOut(ORMModel):
    id: str
    role: str
    content: str
    created_at: datetime


class DocumentOut(ORMModel):
    id: str
    original_name: str
    size_bytes: int
    page_count: int | None
    status: str
    error_message: str | None
    created_at: datetime


class DocumentDetailOut(DocumentOut):
    pass


class DocumentQuestionIn(BaseModel):
    question: str = Field(min_length=1, max_length=4_000)


class DocumentSourceOut(BaseModel):
    chunk_index: int
    page_number: int
    score: float
    matched_terms: list[str]
    content: str


class DocumentAnswerOut(BaseModel):
    answer: str
    source_pages: list[int]
    sources: list[DocumentSourceOut]
    total_chunks: int
    retrieval: str = "bm25"


class TaskSuggestion(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2_000)
    priority: Priority = Priority.medium
    kind: Literal["general", "cobro", "pago"] = "general"
    invoice_number: str | None = Field(default=None, max_length=60)
    issuer: str | None = Field(default=None, max_length=200)
    customer: str | None = Field(default=None, max_length=200)
    amount: str | None = Field(default=None, max_length=60)
    due_date: date | None = None
    remind_at: datetime | None = None
    page: int | None = Field(default=None, ge=1)
    evidence: str | None = Field(default=None, max_length=500)

    @field_validator("remind_at")
    @classmethod
    def require_offset(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("remind_at must include a UTC offset")
        return value


class TaskSuggestionsOut(BaseModel):
    suggestions: list[TaskSuggestion]


class DocumentTasksIn(BaseModel):
    tasks: list[TaskSuggestion] = Field(min_length=1, max_length=20)


class DocumentTasksOut(BaseModel):
    created_tasks: int
    created_reminders: int


class NotificationOut(BaseModel):
    id: str
    title: str
    content: str
    status: str
    created_at: datetime


class WhatsAppLinkIn(BaseModel):
    phone: str = Field(min_length=8, max_length=16)


class WhatsAppLinkPending(BaseModel):
    status: Literal["pending"]
    masked_phone: str
    code: str
    expires_at: datetime


class WhatsAppLinkStatus(BaseModel):
    status: Literal["unlinked", "pending", "verified"]
    masked_phone: str | None = None
    expires_at: datetime | None = None
    verified_at: datetime | None = None
