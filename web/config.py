"""
配置管理模块

读取环境变量和配置文件，提供统一的配置访问接口
"""

import os
from typing import Optional

from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


class Settings:
    """应用配置"""

    # 飞书配置
    FEISHU_APP_ID: Optional[str] = os.getenv("FEISHU_APP_ID")
    FEISHU_APP_SECRET: Optional[str] = os.getenv("FEISHU_APP_SECRET")
    FEISHU_USER_ACCESS_TOKEN: Optional[str] = os.getenv("FEISHU_USER_ACCESS_TOKEN")
    FEISHU_USER_REFRESH_TOKEN: Optional[str] = os.getenv("FEISHU_USER_REFRESH_TOKEN")
    FEISHU_FOLDER_TOKEN: Optional[str] = os.getenv("FEISHU_FOLDER_TOKEN")

    # LLM配置
    LLM_BASE_URL: Optional[str] = os.getenv("LLM_BASE_URL")
    LLM_API_KEY: Optional[str] = os.getenv("LLM_API_KEY")
    LLM_MODEL: Optional[str] = os.getenv("LLM_MODEL", "gpt-3.5-turbo")

    # 应用配置
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data.db")
    WEB_HOST: str = os.getenv("WEB_HOST", os.getenv("HOST", "0.0.0.0"))
    WEB_PORT: int = int(os.getenv("WEB_PORT", os.getenv("PORT", "8000")))
    WEB_RELOAD: bool = os.getenv("WEB_RELOAD", "true").lower() == "true"
    WEB_PUBLIC_BASE_URL: str = os.getenv("WEB_PUBLIC_BASE_URL", "")

    # 任务配置
    DEFAULT_MAX_WORKERS: int = int(os.getenv("DEFAULT_MAX_WORKERS", "2"))
    DEFAULT_CHUNK_WORKERS: int = int(os.getenv("DEFAULT_CHUNK_WORKERS", "4"))
    DEFAULT_NOTIFY_LEVEL: str = os.getenv("DEFAULT_NOTIFY_LEVEL", "normal")

    # 文件存储
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "uploads")
    TEMP_DIR: str = os.getenv("TEMP_DIR", "temp")

    # 安全配置
    SECRET_KEY: str = os.getenv("SECRET_KEY", "default-secret-key-change-in-production")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))


settings = Settings()
