"""Supplemental content is editable separately from the official catalog."""
import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

RESOURCE_FILE = Path(__file__).resolve().parents[1] / "data" / "lesson_resources.json"


def defaults():
    return [
        {"id": "learn", "label": "تعلّم", "demo": True, "text": "افتح الكتاب واقرأ الدرس، ثم اكتب فكرة فهمتها وسؤالًا ترغب في مناقشته."},
        {"id": "video", "label": "شاهد", "demo": True, "url": None, "text": "مساحة مخصّصة لفيديو الدرس. لم يُرفق فيديو لهذا الدرس بعد."},
        {"id": "practice", "label": "تدرّب", "demo": True, "text": "تجربة عامة للواجهة وليست اختبارًا من المنهاج.", "question": "كم ضلعًا للمسدس؟", "choices": [4, 5, 6], "answer": 6},
        {"id": "game", "label": "استكشف", "demo": True, "text": "غيّر عدد أضلاع الشكل ولاحظ الفرق. نشاط هندسي تجريبي عام."},
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
        if resource["id"] == "video" and resource.get("url") and urlparse(resource["url"]).scheme != "https":
            resource["url"] = None
    return result
