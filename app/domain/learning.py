"""Framework-free family limits."""
MAX_CHILDREN = 5


class DomainError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def available_slot(used_slots):
    for slot in range(1, MAX_CHILDREN + 1):
        if slot not in used_slots:
            return slot
    raise DomainError("يمكن إضافة خمسة أطفال كحد أقصى", 409)
