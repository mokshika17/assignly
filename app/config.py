from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Assignly"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REMEMBER_ME_EXPIRE_MINUTES: int = 43200  # 30 days

    # Caching
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL_DASHBOARD: int = 60
    CACHE_TTL_PROJECTS: int = 120
    CACHE_TTL_TASKS: int = 60

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()
settings = get_settings()

settings = get_settings()
