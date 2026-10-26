"""A bounded arithmetic and curriculum helper; no external AI service is connected."""
import ast
import math
import operator
import re

from sqlalchemy import select

from app.models.curriculum import CurriculumBook, CurriculumLesson, CurriculumUnit

TRANSLATION = str.maketrans("٠١٢٣٤٥٦٧٨٩×÷−", "0123456789*/-")
OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Pow: operator.pow}


def calculate(expression):
    if len(expression) > 100:
        raise ValueError()
    tree = ast.parse(expression, mode="eval")
    if sum(1 for _ in ast.walk(tree)) > 40:
        raise ValueError()
    steps = []

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = node.value
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 8:
                raise ValueError()
            value = OPERATORS[type(node.op)](left, right)
            steps.append(f"{ast.unparse(node)} = {value:g}")
        else:
            raise ValueError()
        if isinstance(value, complex) or not math.isfinite(value) or abs(value) > 1e12:
            raise ValueError()
        return value

    return visit(tree.body), steps


def respond(db, data):
    expression = data.message.translate(TRANSLATION).strip().replace("^", "**")
    expression = re.sub(r"^(احسب|كم يساوي)\s*", "", expression).rstrip("؟?=").strip()
    base = {"is_demo": True, "mode": "local", "sources": [], "steps": []}
    if re.fullmatch(r"[0-9\s.+*/()\-]+", expression):
        try:
            result, steps = calculate(expression)
            return {**base, "answer": f"الناتج = {result:g}", "steps": steps}
        except (ValueError, SyntaxError, ZeroDivisionError, OverflowError, TypeError):
            return {**base, "answer": "تعذّر حساب العبارة. استخدم أعدادًا وعمليات بسيطة، وتأكد من الأقواس وعدم القسمة على صفر."}
    term = re.sub(r"^(ابحث عن|ابحث|درس)\s*", "", data.message).strip()
    statement = (select(CurriculumLesson, CurriculumBook).join(CurriculumUnit, CurriculumLesson.unit_id == CurriculumUnit.id)
                 .join(CurriculumBook, CurriculumUnit.book_id == CurriculumBook.id).where(CurriculumLesson.title.icontains(term, autoescape=True)))
    if data.grade:
        statement = statement.where(CurriculumBook.grade == data.grade)
    rows = db.execute(statement.order_by(CurriculumBook.grade, CurriculumBook.id, CurriculumLesson.position).limit(5)).all()
    return {**base, "answer": "وجدت هذه الدروس في فهرس المنهاج:" if rows else "أستطيع حساب عبارة مثل (١٢ + ٨) ÷ ٤، أو البحث عن عنوان درس مثل الكسور. هذه نسخة تجريبية محدودة؛ لا يوجد نموذج ذكاء اصطناعي متصل.",
            "sources": [{"title": lesson.title, "grade": book.grade, "book": book.title, "source_url": book.source_url} for lesson, book in rows]}
