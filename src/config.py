from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SECRET_KEY: str = "exam-eval-super-secret-key-change-in-prod-2024"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/exam_eval.db"
    PORT: int = 8080

    class Config:
        env_file = ".env"


settings = Settings()
