from datetime import date
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .domain import SECTIONS


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Credentials(StrictModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value):
        return value.lower()


class TeacherRegister(Credentials):
    full_name: str = Field(min_length=2, max_length=150)
    school: str = Field(default="", max_length=150)


class PlanContent(StrictModel):
    objectives: str = Field(min_length=1, max_length=4000)
    steps: str = Field(min_length=1, max_length=10000)
    assessment: str = Field(min_length=1, max_length=4000)
    materials: str = Field(default="", max_length=2000)
    duration: int = Field(default=45, ge=5, le=180)


class Question(StrictModel):
    prompt: str = Field(min_length=1, max_length=1500)
    options: list[str] = Field(min_length=2, max_length=6)
    correct: int = Field(ge=0, le=5)
    explanation: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_options(self):
        self.options = [value.strip() for value in self.options]
        if any(not value or len(value) > 500 for value in self.options):
            raise ValueError("الإجابات مطلوبة وبحد أقصى 500 حرف")
        if len(set(self.options)) != len(self.options) or self.correct >= len(self.options):
            raise ValueError("أدخل خيارات مختلفة وحدد الإجابة الصحيحة")
        return self


class AssessmentContent(StrictModel):
    instructions: str = Field(default="", max_length=2000)
    questions: list[Question] = Field(min_length=1, max_length=30)


class DocumentWrite(StrictModel):
    kind: Literal["plan", "assessment"]
    title: str = Field(min_length=2, max_length=180)
    grade: int = Field(ge=1, le=12)
    book_id: str | None = Field(default=None, max_length=100)
    lesson_id: str | None = Field(default=None, max_length=100)
    content: dict
    version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_content(self):
        self.content = (PlanContent if self.kind == "plan" else AssessmentContent).model_validate(self.content).model_dump()
        if self.kind == "plan" and (not self.book_id or not self.lesson_id):
            raise ValueError("التحضير يحتاج كتابًا ودرسًا")
        if self.lesson_id and not self.book_id:
            raise ValueError("حدد الكتاب الخاص بالدرس")
        return self


class ArchiveWrite(StrictModel):
    archived: bool
    version: int = Field(ge=1)


class EntryWrite(StrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_-]+$")
    section: str
    category: str
    title: str = Field(min_length=2, max_length=180)
    summary: str = Field(min_length=2, max_length=500)
    body: str = Field(min_length=2, max_length=30000)
    source_url: str | None = Field(default=None, max_length=2000)
    event_date: date | None = None
    archived: bool = False
    published: bool = True
    is_demo: bool = True
    activity: AssessmentContent | None = None

    @model_validator(mode="after")
    def validate_entry(self):
        if self.section not in SECTIONS or self.category not in SECTIONS[self.section]:
            raise ValueError("قسم أو تصنيف غير صالح")
        if self.source_url:
            url = urlsplit(self.source_url)
            if url.scheme != "https" or not url.hostname or url.username or url.password:
                raise ValueError("المصدر يجب أن يكون رابط HTTPS صالحًا")
        return self


class AssistantRequest(StrictModel):
    message: str = Field(min_length=1, max_length=500)
    grade: int | None = Field(default=None, ge=1, le=12)
