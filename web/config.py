"""
Configuration module for web service.

Loads environment variables and exposes a settings object.
"""
import os
import sys
from pathlib import Path
from typing import Optional


project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from config.config import load_dotenv_if_exists

load_dotenv_if_exists()


class Settings:
    """Application settings."""

    # Feishu settings
    FEISHU_APP_ID: Optional[str] = os.getenv("FEISHU_APP_ID")
    FEISHU_APP_SECRET: Optional[str] = os.getenv("FEISHU_APP_SECRET")
    FEISHU_USER_ACCESS_TOKEN: Optional[str] = os.getenv("FEISHU_USER_ACCESS_TOKEN")
    FEISHU_USER_REFRESH_TOKEN: Optional[str] = os.getenv("FEISHU_USER_REFRESH_TOKEN")
    FEISHU_FOLDER_TOKEN: Optional[str] = os.getenv("FEISHU_FOLDER_TOKEN")

    # LLM settings
    LLM_BASE_URL: Optional[str] = os.getenv("LLM_BASE_URL")
    LLM_API_KEY: Optional[str] = os.getenv("LLM_API_KEY")
    LLM_MODEL: Optional[str] = os.getenv("LLM_MODEL", "gpt-3.5-turbo")

    # App settings
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./storage/web/tasks.db")
    WEB_HOST: str = os.getenv("WEB_HOST", os.getenv("HOST", "0.0.0.0"))
    WEB_PORT: int = int(os.getenv("WEB_PORT", os.getenv("PORT", "8000")))
    WEB_RELOAD: bool = os.getenv("WEB_RELOAD", "true").lower() == "true"
    WEB_PUBLIC_BASE_URL: str = os.getenv("WEB_PUBLIC_BASE_URL", "")

    # Task defaults
    DEFAULT_MAX_WORKERS: int = int(os.getenv("DEFAULT_MAX_WORKERS", "2"))
    DEFAULT_CHUNK_WORKERS: int = int(os.getenv("DEFAULT_CHUNK_WORKERS", "4"))
    DEFAULT_NOTIFY_LEVEL: str = os.getenv("DEFAULT_NOTIFY_LEVEL", "normal")

    # Storage
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "uploads")
    TEMP_DIR: str = os.getenv("TEMP_DIR", "temp")

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "default-secret-key-change-in-production")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))


settings = Settings()
