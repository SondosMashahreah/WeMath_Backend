SECTIONS = {
    "workshops": {"scientific": "ورش علمية", "universities": "جامعات ومؤسسات", "directorates": "مديريات التربية"},
    "competitions": {"scientific": "مسابقات علمية", "international": "مسابقات دولية"},
    "initiatives": {"schools": "مبادرات المدارس", "directorates": "مبادرات المديريات", "teachers": "مبادرات المعلمين", "students": "مبادرات الطلاب", "teacher_stories": "قصص نجاح المعلمين", "student_stories": "قصص نجاح الطلاب", "school_stories": "قصص نجاح المدارس"},
    "research": {"scientific": "أبحاث علمية", "classroom": "أبحاث صفية"},
    "teacher_resources": {"activities": "أنشطة وألعاب", "questions": "بنك الأسئلة", "preparation": "نماذج تحضير"},
}


class PlatformError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status
