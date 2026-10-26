from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class StudentDetails(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    full_name: str = Field(min_length=2, max_length=150)
    grade: int = Field(ge=1, le=12)
    identity_number: str | None = Field(default=None, pattern=r"^[0-9]{6,12}$")
    school: str | None = Field(default=None, max_length=150)
    phone: str | None = Field(default=None, pattern=r"^\+?[0-9]{7,15}$")
    directorate: str | None = Field(default=None, max_length=150)


class AccountCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class RegisterRequest(AccountCredentials):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr | None = None
    role: Literal["student", "parent"] = "student"
    grade: int | None = Field(default=None, ge=1, le=12)
    identity_number: str | None = Field(default=None, pattern=r"^[0-9]{6,12}$")
    school: str | None = Field(default=None, max_length=150)
    phone: str | None = Field(default=None, pattern=r"^\+?[0-9]{7,15}$")
    directorate: str | None = Field(default=None, max_length=150)

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if len(value) < 2:
            raise ValueError("الاسم مطلوب")
        return value

    @model_validator(mode="after")
    def check_student_grade(self):
        if self.role == "student" and self.grade is None:
            raise ValueError("صف الطالب مطلوب")
        return self


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ChildCreateRequest(RegisterRequest):
    role: Literal["student"] = "student"


class PasswordResetRequest(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class ChildUpdateRequest(StudentDetails):
    is_active: bool = True
