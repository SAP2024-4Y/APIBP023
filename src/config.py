import warnings

from pydantic_settings import BaseSettings

_DEFAULT_SECRET_KEY = "exam-eval-super-secret-key-change-in-prod-2024"


class Settings(BaseSettings):
    SECRET_KEY: str = _DEFAULT_SECRET_KEY
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/exam_eval.db"
    PORT: int = 8080

    class Config:
        env_file = ".env"


settings = Settings()

if settings.SECRET_KEY == _DEFAULT_SECRET_KEY:
    warnings.warn(
        "SECRET_KEY is set to the default development value. "
        "Set the SECRET_KEY environment variable before deploying to production.",
        stacklevel=1,
    )
