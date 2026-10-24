from datetime import datetime

from pydantic import BaseModel, EmailStr


class CurrentUserResponse(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    is_active: bool
    is_verified: bool
    roles: list[str]
    created_at: datetime