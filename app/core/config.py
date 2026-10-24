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

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()