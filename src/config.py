"""
Architect Agent - Configuration
================================
Application settings loaded from environment variables.
"""
from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List
import json
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # ============ App Settings ============
    APP_NAME: str = "Architect Agent"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # ============ MongoDB ============
    MONGODB_URI: str
    MONGODB_DB_NAME: str = "architect_agent"
    MONGODB_MAX_POOL_SIZE: int = 10
    MONGODB_MIN_POOL_SIZE: int = 1

    # ============ Claude API ============
    ANTHROPIC_API_KEY: str
    CLAUDE_MODEL: str = "claude-sonnet-4-20250514"
    CLAUDE_MAX_TOKENS: int = 4096
    CLAUDE_TEMPERATURE: float = 0.7

    # ============ Redis (Optional) ============
    REDIS_URL: str = ""

    # ============ CORS ============
    CORS_ORIGINS: List[str] = ["*"]

    # תיקון: טיפול ב-CORS_ORIGINS ריק או לא תקין
    @field_validator('CORS_ORIGINS', mode='before')
    @classmethod
    def parse_cors_origins(cls, v):
        """פרסור CORS_ORIGINS מ-string ל-list."""
        if isinstance(v, str):
            if not v or v.strip() == "":
                return ["*"]
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                # אם לא JSON, מפריד לפי פסיקים
                return [x.strip() for x in v.split(',')]
        return v

    # ============ Agent Settings ============
    MAX_ITERATIONS: int = 5
    MIN_CONFIDENCE: float = 0.7
    HISTORY_LIMIT: int = 10  # Max messages to include in LLM context

    # ============ Logging ============
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()
