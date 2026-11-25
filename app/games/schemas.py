from fractions import Fraction
from typing import Literal
from urllib.parse import urlsplit
from pydantic import Field, model_validator
from app.exams.schemas import Strict

Kind = Literal['matching', 'memory', 'quiz', 'true_false', 'sorting', 'wheel', 'number_line', 'fractions', 'maze']


def number(value):
    try:
        if len(str(value)) > 30: raise ValueError()
        result = Fraction(str(value))
        if abs(result) > 10000 or result.denominator > 10000: raise ValueError()
        return result
    except (ValueError, ZeroDivisionError):
        raise ValueError('اكتب عددًا أو كسرًا صالحًا مثل 3/4 ضمن الحدود') from None


class Settings(Strict):
    theme: Literal['orange', 'green', 'purple'] = 'orange'
    seconds: int = Field(default=0, ge=0, le=3600)
    max_mistakes: int = Field(default=0, ge=0, le=100)
    points: int = Field(default=10, ge=1, le=100)
    sound: bool = False
    shuffle: bool = True


class Item(Strict):
    prompt: str = Field(default='', max_length=1500)
    answer: str = Field(default='', max_length=500)
    options: list[str] = Field(default_factory=lambda: ['', '', '', ''], min_length=2, max_length=6)
    correct: int = Field(default=-1, ge=-1, le=5)
    explanation: str = Field(default='', max_length=2000)
    image_url: str = Field(default='', max_length=2000)
    image_alt: str = Field(default='', max_length=300)
    group: int = Field(default=0, ge=0, le=5)
    value: str = Field(default='0', max_length=30)
    numerator: int = Field(default=1, ge=0, le=12)
    denominator: int = Field(default=2, ge=1, le=12)

    @model_validator(mode='after')
    def lengths_and_image(self):
        if any(len(option) > 500 for option in self.options): raise ValueError('الخيار أطول من 500 حرف')
        if self.image_url:
            url = urlsplit(self.image_url)
            if url.scheme != 'https' or not url.hostname or url.username or url.password:
                raise ValueError('صورة السؤال تحتاج رابط HTTPS صالحًا')
        return self


class DraftGame(Strict):
    schema_version: Literal[1] = 1
    kind: Kind = 'matching'
    instructions: str = Field(default='', max_length=2000)
    settings: Settings = Field(default_factory=Settings)
    items: list[Item] = Field(default_factory=list, max_length=20)
    groups: list[str] = Field(default_factory=lambda: ['أعداد زوجية', 'أعداد فردية'], min_length=2, max_length=6)
    minimum: str = Field(default='0', max_length=30)
    maximum: str = Field(default='10', max_length=30)
    step: str = Field(default='1', max_length=30)

    @model_validator(mode='after')
    def bound_groups(self):
        if any(len(g) > 80 for g in self.groups): raise ValueError('اسم المجموعة أطول من 80 حرفًا')
        return self


class Game(DraftGame):
    @model_validator(mode='after')
    def playable(self):
        if not self.items: raise ValueError('أضف عنصرًا واحدًا على الأقل')
        if self.kind in ('matching', 'memory'):
            if not 2 <= len(self.items) <= 12: raise ValueError('المطابقة والذاكرة تحتاجان 2 إلى 12 زوجًا')
            for field in ('prompt', 'answer'):
                values = [getattr(item, field).strip() for item in self.items]
                if any(not v for v in values) or len(set(values)) != len(values):
                    raise ValueError('أكمل العمليات والإجابات دون تكرار في الأزواج')
        if self.kind == 'sorting' and (any(not g.strip() for g in self.groups) or len(set(g.strip() for g in self.groups)) != len(self.groups)):
            raise ValueError('أسماء مجموعات التصنيف مطلوبة ومختلفة')
        if self.kind == 'number_line':
            low, high, step = number(self.minimum), number(self.maximum), number(self.step)
            if low >= high or step <= 0 or (high-low)/step > 40 or ((high-low)/step).denominator != 1:
                raise ValueError('خط الأعداد يحتاج بداية أقل من النهاية وخطوة موجبة وتقسيمًا منتظمًا حتى 40 فاصلة')
        for item in self.items:
            if self.kind not in ('number_line', 'fractions') and not item.prompt.strip(): raise ValueError('نص السؤال مطلوب')
            if item.image_url and not item.image_alt.strip(): raise ValueError('وصف الصورة مطلوب')
            if self.kind in ('quiz', 'true_false', 'wheel', 'maze'):
                if any(not v.strip() for v in item.options) or len(set(v.strip() for v in item.options)) != len(item.options) or not 0 <= item.correct < len(item.options):
                    raise ValueError('أكمل خيارات مختلفة وحدد الإجابة الصحيحة')
                if self.kind == 'true_false' and item.options != ['صح', 'خطأ']: raise ValueError('خيارات صح/خطأ هي صح ثم خطأ')
            if self.kind == 'sorting' and item.group >= len(self.groups): raise ValueError('اختر مجموعة موجودة لكل عنصر')
            if self.kind == 'fractions' and item.numerator > item.denominator: raise ValueError('الكسور البصرية من صفر إلى واحد؛ البسط لا يتجاوز المقام')
            if self.kind == 'number_line':
                target = number(item.value)
                if not low <= target <= high or ((target-low)/step).denominator != 1:
                    raise ValueError('العدد المطلوب يجب أن يقع على إحدى علامات خط الأعداد')
        return self


class GameWrite(Strict):
    title: str = Field(min_length=2, max_length=180)
    grade: int = Field(ge=1, le=12)
    book_id: str | None = Field(default=None, max_length=100)
    unit_id: str | None = Field(default=None, max_length=100)
    lesson_id: str | None = Field(default=None, max_length=100)
    game: DraftGame
    external_url: str = Field(default='', max_length=2000)
    version: int | None = Field(default=None, ge=1)

    @model_validator(mode='after')
    def link(self):
        if self.external_url:
            u = urlsplit(self.external_url)
            if u.scheme != 'https' or not u.hostname or u.username or u.password: raise ValueError('الرابط الخارجي يجب أن يكون HTTPS')
        return self


class Transition(Strict):
    version: int = Field(ge=1)
    status: Literal['draft', 'review', 'published', 'archived']
