import hashlib
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "WeMath API"
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8100

    DB_HOST: str = "localhost"
    DB_PORT: int = 5433
    DB_NAME: str = "wemath"
    DB_USER: str = "wemath"
    DB_PASSWORD: str = "wemath_password"

    DATABASE_URL: str

    JWT_SECRET_KEY: str = Field(min_length=32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def reject_example_key(cls, value):
        if value.startswith("CHANGE_ME") or hashlib.sha256(value.encode()).hexdigest() == "99fb1f136b270197eaf2d2b2c2b0715f6a873a733e3609835fe3713020e9b22d":
            raise ValueError("Generate a new JWT_SECRET_KEY; the example key must not be used")
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()