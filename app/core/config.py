from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Sentinel AI"
    DATABASE_URL: str = "postgresql+psycopg2://sentinel:password@localhost:5432/sentinel_db"
    REDIS_URL: str = "redis://localhost:6379/0"
    GEMINI_API_KEY: str | None = None
    GITHUB_TOKEN: str | None = None
    GITHUB_REPO: str | None = None  # e.g. "username/sentinel-sample-repo"

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'

settings = Settings()
