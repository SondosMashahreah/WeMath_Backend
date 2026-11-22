"""Bounded arithmetic interpreter. No eval, Python calls or arbitrary execution."""
import ast
import random
from string import Formatter
from fractions import Fraction
from typing import Literal
from pydantic import Field, model_validator
from .schemas import Strict, Question, DraftQuestion

NAME = r'^[a-z][a-z0-9_]{0,15}$'


class Variable(Strict):
    name: str = Field(pattern=NAME)
    minimum: int = Field(default=1, ge=-10000, le=10000)
    maximum: int = Field(default=10, ge=-10000, le=10000)
    step: int = Field(default=1, ge=1, le=10000)

    @model_validator(mode='after')
    def range_valid(self):
        if self.minimum > self.maximum or self.name == 'answer':
            raise ValueError('تحقق من مجال المتغير واسمه؛ answer محجوز للإجابة')
        return self


def parse(expression):
    try:
        tree = ast.parse(expression, mode='eval')
    except (SyntaxError, RecursionError):
        raise ValueError('صيغة رياضية غير صحيحة') from None
    allowed = (ast.Expression, ast.Constant, ast.Name, ast.Load, ast.BinOp, ast.UnaryOp,
               ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
               ast.UAdd, ast.USub, ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)
    nodes = list(ast.walk(tree))
    if len(nodes) > 80 or any(not isinstance(node, allowed) for node in nodes):
        raise ValueError('استخدم العمليات الحسابية والمقارنات فقط، دون دوال أو كود')
    for node in nodes:
        if isinstance(node, ast.Constant) and (type(node.value) is not int or abs(node.value) > 1000000):
            raise ValueError('الثوابت أعداد صحيحة بين -1000000 و1000000؛ اكتب الكسر مثل 1/2')
    return tree.body


def calculate(node, values):
    if isinstance(node, ast.Constant):
        result = Fraction(node.value)
    elif isinstance(node, ast.Name):
        if node.id not in values:
            raise ValueError('متغير غير معروف: ' + node.id)
        result = values[node.id]
    elif isinstance(node, ast.UnaryOp):
        value = calculate(node.operand, values)
        result = -value if isinstance(node.op, ast.USub) else value
    elif isinstance(node, ast.BinOp):
        a, b = calculate(node.left, values), calculate(node.right, values)
        if isinstance(a, bool) or isinstance(b, bool):
            raise ValueError('لا تستخدم المقارنة داخل عملية حسابية')
        if isinstance(node.op, ast.Add): result = a + b
        elif isinstance(node.op, ast.Sub): result = a - b
        elif isinstance(node.op, ast.Mult): result = a * b
        elif isinstance(node.op, ast.Div): result = a / b
        elif isinstance(node.op, ast.FloorDiv): result = Fraction(a // b)
        elif isinstance(node.op, ast.Mod): result = a % b
        else:
            if b.denominator != 1 or not 0 <= b <= 6:
                raise ValueError('الأس عدد صحيح من 0 إلى 6')
            result = a ** int(b)
    elif isinstance(node, ast.Compare):
        a = calculate(node.left, values)
        result = True
        for op, right in zip(node.ops, node.comparators):
            b = calculate(right, values)
            if isinstance(op, ast.Eq): valid = a == b
            elif isinstance(op, ast.NotEq): valid = a != b
            elif isinstance(op, ast.Lt): valid = a < b
            elif isinstance(op, ast.LtE): valid = a <= b
            elif isinstance(op, ast.Gt): valid = a > b
            else: valid = a >= b
            result = result and valid
            a = b
    else:
        raise ValueError('صيغة غير مدعومة')
    if not isinstance(result, bool) and (abs(result.numerator) > 10**12 or result.denominator > 10**9):
        raise ValueError('النتيجة تتجاوز الحدود المسموحة')
    return result


class MathTemplate(Strict):
    type: Literal['mcq', 'true_false'] = 'mcq'
    prompt: str = Field(min_length=1, max_length=1500)
    variables: list[Variable] = Field(min_length=1, max_length=6)
    constraints: list[str] = Field(default_factory=list, max_length=8)
    answer: str = Field(min_length=1, max_length=200)
    distractors: list[str] = Field(default_factory=lambda: ['answer+1', 'answer-1', 'answer+2'], max_length=5)
    explanation: str = Field(default='', max_length=2000)
    image_url: str = Field(default='', max_length=2000)
    image_alt: str = Field(default='', max_length=300)
    points: int = Field(default=1, ge=1, le=100)

    @model_validator(mode='after')
    def validate_template(self):
        names = {v.name for v in self.variables}
        if len(names) != len(self.variables):
            raise ValueError('أسماء المتغيرات يجب أن تكون مختلفة')
        if self.type == 'mcq' and not self.distractors:
            raise ValueError('أضف تعبيرًا لإجابة بديلة على الأقل')
        for expression, allowed, boolean in [(self.answer, names, self.type == 'true_false'), *[(c, names, True) for c in self.constraints], *[(d, names | {'answer'}, False) for d in self.distractors if self.type == 'mcq']]:
            if not expression or len(expression) > 200:
                raise ValueError('التعبير من 1 إلى 200 حرف')
            node = parse(expression)
            if isinstance(node, ast.Compare) != boolean:
                raise ValueError('الشروط وصح/خطأ تحتاج مقارنة؛ الإجابة العددية تحتاج عملية حسابية')
            if any(n.id not in allowed for n in ast.walk(node) if isinstance(n, ast.Name)):
                raise ValueError('التعبير يحتوي متغيرًا غير معروف')
        # Python's formatter is used only after restricting fields to plain names.
        for source in (self.prompt, self.explanation):
            try:
                fields = list(Formatter().parse(source))
            except ValueError:
                raise ValueError('تحقق من أقواس المتغيرات في النص') from None
            for _, name, spec, conversion in fields:
                if name is not None and (name not in names | {'answer'} or spec or conversion):
                    raise ValueError('حقول النص هي أسماء المتغيرات أو answer؛ أقواس LaTeX تكتب مزدوجة')
        if '{answer}' in self.prompt:
            raise ValueError('لا تضع الإجابة في نص السؤال')
        DraftQuestion(prompt=self.prompt, options=['', ''], image_url=self.image_url, image_alt=self.image_alt)
        if self.image_url and not self.image_alt:
            raise ValueError('أضف وصف الصورة')
        return self


class GenerateRequest(Strict):
    workspace_id: int
    template: MathTemplate
    count: int = Field(default=5, ge=1, le=30)
    seed: int = Field(default=1, ge=0, le=2147483647)


def display(value):
    if isinstance(value, bool): return 'صح' if value else 'خطأ'
    return str(value)


def render(source, values):
    return source.format_map({key: display(value) for key, value in values.items()})


def generate(data):
    t = data.template
    rng = random.Random(data.seed)
    answer = parse(t.answer)
    constraints = [parse(c) for c in t.constraints]
    distractors = [parse(d) for d in t.distractors] if t.type == 'mcq' else []
    questions, seen = [], set()
    for _ in range(2000):
        values = {v.name: Fraction(rng.randrange(v.minimum, v.maximum + 1, v.step)) for v in t.variables}
        try:
            if not all(calculate(c, values) for c in constraints): continue
            result = calculate(answer, values)
            values['answer'] = result
            prompt = render(t.prompt, values)
            if prompt in seen: continue
            if t.type == 'true_false':
                options, correct = ['صح', 'خطأ'], 0 if result else 1
            else:
                answers = [result, *[calculate(d, values) for d in distractors]]
                if len(set(answers)) != len(answers) or any(isinstance(v, bool) for v in answers): continue
                options = [display(v) for v in answers]
                rng.shuffle(options)
                correct = options.index(display(result))
            question = Question(type=t.type, prompt=prompt, options=options, correct=correct,
                                explanation=render(t.explanation, values), image_url=t.image_url,
                                image_alt=t.image_alt, points=t.points)
        except (ZeroDivisionError, ValueError, OverflowError):
            continue
        seen.add(prompt)
        questions.append(question.model_dump())
        if len(questions) == data.count:
            return questions
    raise ValueError('تعذر توليد العدد المطلوب بأسئلة مختلفة وصحيحة. وسّع مجال الأرقام، أو قلل العدد، أو راجع الشروط والبدائل.')
