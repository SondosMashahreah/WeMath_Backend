from app.exams.schemas import DraftQuestion
from typing import Literal
from datetime import date
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.schemas.auth import AccountCredentials
from .catalog import MODULES


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class WorkspaceWrite(Strict):
    name: str = Field(min_length=2, max_length=150)
    modules: list[str] = Field(min_length=1, max_length=10)
    member_ids: list[int] = Field(default_factory=list, max_length=500)
    can_publish: bool = False
    active: bool = True
    version: int | None = Field(default=None, ge=1)

    @field_validator("modules")
    @classmethod
    def valid_modules(cls, value):
        if len(set(value)) != len(value) or not set(value) <= MODULES.keys():
            raise ValueError("اختر أقسامًا صحيحة دون تكرار")
        return value


class StaffCreate(AccountCredentials):
    full_name: str = Field(min_length=2, max_length=150)


class StaffUpdate(Strict):
    is_active: bool
    password: str | None = Field(default=None, min_length=8, max_length=128)


class Payload(Strict):
    summary: str = Field(default="", max_length=500)
    body: str = Field(default="", max_length=30000)
    source_url: str = Field(default="", max_length=2000)
    lesson_id: str = Field(default="", max_length=200)
    category: str = Field(default="", max_length=32)
    event_date: date | None = None
    organizer: str = Field(default="", max_length=180)
    audience: str = Field(default="", max_length=300)
    location: str = Field(default="", max_length=300)
    registration_start: date | None = None
    registration_end: date | None = None
    attachments: list[str] = Field(default_factory=list, max_length=30)
    questions: list[DraftQuestion] = Field(default_factory=list, max_length=30)
    results: str = Field(default="", max_length=2000)
    examples: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("event_date", "registration_start", "registration_end", mode="before")
    @classmethod
    def blank_date(cls, value):
        return value or None

    @model_validator(mode="after")
    def links_and_dates(self):
        for value in [self.source_url, *self.attachments, self.results]:
            if not value:
                continue
            link = urlsplit(value)
            if len(value) > 2000 or link.scheme != "https" or not link.hostname or link.username or link.password:
                raise ValueError("استخدم روابط HTTPS صالحة دون بيانات دخول")
        if self.registration_start and self.registration_end and self.registration_end < self.registration_start:
            raise ValueError("نهاية التسجيل تسبق بدايته")
        return self


class ContentWrite(Strict):
    workspace_id: int
    module: str
    title: str = Field(min_length=2, max_length=180)
    payload: Payload
    version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def workshop_date_range(self):
        if self.module == "workshops" and self.payload.event_date and not 1900 <= self.payload.event_date.year <= 2199:
            raise ValueError("موعد الورشة يجب أن يكون بين 1900 و2199")
        return self

    @field_validator("module")
    @classmethod
    def valid_module(cls, value):
        if value not in MODULES:
            raise ValueError("قسم غير صالح")
        return value


class Transition(Strict):
    version: int = Field(ge=1)
    status: Literal["draft", "review", "published", "archived"]
