"""Supplemental content is editable separately from the official catalog."""
import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

RESOURCE_FILE = Path(__file__).resolve().parents[1] / "data" / "lesson_resources.json"


def defaults():
    return [
        {"id": "quiz", "label": "اختبار إلكتروني", "demo": True, "text": "الاختبار الإلكتروني سيُفعّل في مرحلة لاحقة."},
        {"id": "worksheet", "label": "أوراق عمل إلكترونية", "demo": True, "text": "مساحة أوراق العمل الإلكترونية لهذا الدرس."},
        {"id": "film", "label": "فلم", "demo": True, "url": None, "text": "مساحة مخصّصة لفلم الدرس. لم يُرفق ملف لهذا الدرس بعد."},
        {"id": "activity", "label": "أنشطة", "demo": True, "text": "مساحة الأنشطة المرتبطة بهذا الدرس."},
        {"id": "game", "label": "ألعاب", "demo": True, "text": "نشاط تفاعلي تجريبي إلى أن تضاف ألعاب الدرس الفعلية."},
        {"id": "story_video", "label": "القصة المروية أو الفيديو", "demo": True, "url": None, "text": "مساحة القصة المروية أو الفيديو المرتبط بالدرس."},
    ]


@lru_cache(maxsize=1)
def overrides():
    return json.loads(RESOURCE_FILE.read_text(encoding="utf-8"))


def for_lesson(lesson_id: str):
    result = defaults()
    custom = overrides().get(lesson_id, {})
    for resource in result:
        replacement = custom.get(resource["id"], {})
        resource.update({k: v for k, v in replacement.items() if k in resource and k != "id"})
        if resource["id"] in {"film", "story_video"} and resource.get("url") and urlparse(resource["url"]).scheme != "https":
            resource["url"] = None
    return result
