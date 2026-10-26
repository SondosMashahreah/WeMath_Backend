from datetime import datetime

from pydantic import BaseModel, EmailStr


class CurrentUserResponse(BaseModel):
    id: int
    full_name: str
    username: str
    grade: int | None = None
    email: EmailStr | None
    is_active: bool
    is_verified: bool
    roles: list[str]
    created_at: datetime