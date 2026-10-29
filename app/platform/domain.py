SECTIONS = {
    "workshops": {"scientific": "ورش عالمية", "universities": "جامعات ومؤسسات", "directorates": "مديريات التربية"},
    "competitions": {"scientific": "مسابقات محلية", "international": "مسابقات عالمية"},
    "initiatives": {"schools": "مبادرات المدارس", "directorates": "مبادرات المديريات", "teachers": "مبادرات المعلمين", "students": "مبادرات الطلاب", "teacher_stories": "قصص نجاح المعلمين", "student_stories": "قصص نجاح الطلاب", "school_stories": "قصص نجاح المدارس"},
    "teacher_resources": {"activities": "أنشطة وألعاب", "questions": "بنك الأسئلة", "preparation": "نماذج تحضير"},
}


class PlatformError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status
