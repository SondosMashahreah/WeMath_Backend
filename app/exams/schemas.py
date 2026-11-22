"""Shared question contract for draft editors, publication and reusable banks."""
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class DraftQuestion(Strict):
    type: Literal['mcq', 'true_false'] = 'mcq'
    prompt: str = Field(default='', max_length=1500)
    options: list[str] = Field(min_length=2, max_length=6)
    correct: int = Field(default=-1, ge=-1, le=5)
    explanation: str = Field(default='', max_length=2000)
    image_url: str = Field(default='', max_length=2000)
    image_alt: str = Field(default='', max_length=300)
    points: int = Field(default=1, ge=1, le=100)

    @field_validator('image_url')
    @classmethod
    def image_link(cls, value):
        if value:
            url = urlsplit(value)
            if url.scheme != 'https' or not url.hostname or url.username or url.password:
                raise ValueError('صورة السؤال تحتاج رابط HTTPS صالحًا دون بيانات دخول')
        return value

    @field_validator('options')
    @classmethod
    def bound_options(cls, value):
        if any(len(option) > 500 for option in value):
            raise ValueError('كل خيار بحد أقصى 500 حرف')
        return value


class Question(DraftQuestion):
    prompt: str = Field(min_length=1, max_length=1500)
    correct: int = Field(ge=0, le=5)

    @model_validator(mode='after')
    def complete(self):
        self.options = [value.strip() for value in self.options]
        if any(not value for value in self.options) or len(set(self.options)) != len(self.options) or self.correct >= len(self.options):
            raise ValueError('أدخل خيارات مختلفة وحدد الإجابة الصحيحة')
        if self.type == 'true_false' and self.options != ['صح', 'خطأ']:
            raise ValueError('خيارات صح أو خطأ يجب أن تكون: صح، خطأ')
        if self.image_url and not self.image_alt:
            raise ValueError('أضف وصفًا للصورة لتسهيل الوصول')
        return self


class Exam(Strict):
    instructions: str = Field(default='', max_length=30000)
    questions: list[Question] = Field(min_length=1, max_length=30)
