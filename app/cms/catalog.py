from app.platform.domain import SECTIONS

RESOURCE_LABELS = {"quiz": "الامتحانات", "worksheet": "أوراق العمل", "film": "الأفلام", "activity": "الأنشطة", "game": "الألعاب", "story_video": "القصص والفيديو"}
SECTION_LABELS = {"workshops": "الورشات", "competitions": "المسابقات", "initiatives": "المبادرات وقصص النجاح", "teacher_resources": "مكتبة المعلم"}
MODULES = {**{key: {"label": label, "resource": True, "categories": {}} for key, label in RESOURCE_LABELS.items()},
           **{key: {"label": SECTION_LABELS[key], "resource": False, "categories": categories} for key, categories in SECTIONS.items()}}


def blank_template(module):
    return {"title": "", "summary": "", "body": "", "source_url": "", "lesson_id": "", "category": "",
            "event_date": "", "organizer": "", "audience": "", "location": "", "registration_start": "",
            "registration_end": "", "attachments": [], "questions": [], "results": "", "examples": []}
