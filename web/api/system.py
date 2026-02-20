"""System management API.

Provides system info and configuration management.
"""

import os
import sys
import logging
from typing import Optional

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

sys.path.append(os.getcwd())

from web.config import settings
from config.config import get_project_root

router = APIRouter()
logger = logging.getLogger(__name__)


class SystemInfo(BaseModel):
    """System info payload."""
    version: str
    status: str
    features: list


class Config(BaseModel):
    """System config payload."""
    feishu_app_id: Optional[str] = None
    feishu_app_secret: Optional[str] = None
    feishu_user_access_token: Optional[str] = None
    feishu_user_refresh_token: Optional[str] = None
    feishu_folder_token: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model: Optional[str] = None


@router.get("/info", response_model = SystemInfo)
async def get_system_info():
    """Return system info."""
    return {
        "version": "1.0.0",
        "status": "running",
        "features": [
            "本地目录导入",
            "GitHub仓库导入",
            "飞书云盘文件夹写入",
            "知识库写入",
            "任务状态监控",
            "通知功能"
        ]
    }


@router.get("/config", response_model = Config)
async def get_system_config():
    """Return system config."""
    return {
        "feishu_app_id": settings.FEISHU_APP_ID,
        "feishu_app_secret": "****" if settings.FEISHU_APP_SECRET else None,
        "feishu_user_access_token": "****" if settings.FEISHU_USER_ACCESS_TOKEN else None,
        "feishu_user_refresh_token": "****" if settings.FEISHU_USER_REFRESH_TOKEN else None,
        "feishu_folder_token": settings.FEISHU_FOLDER_TOKEN,
        "llm_base_url": settings.LLM_BASE_URL,
        "llm_api_key": "****" if settings.LLM_API_KEY else None,
        "llm_model": settings.LLM_MODEL
    }


@router.post("/config")
async def update_system_config(config: Config):
    """Update system config."""
    try:
        from dotenv import set_key, load_dotenv

        load_dotenv()

        env_file = str(get_project_root() / ".env")

        if config.feishu_app_id is not None:
            set_key(env_file, "FEISHU_APP_ID", config.feishu_app_id)
            os.environ["FEISHU_APP_ID"] = config.feishu_app_id
            settings.FEISHU_APP_ID = config.feishu_app_id

        if config.feishu_app_secret is not None:
            set_key(env_file, "FEISHU_APP_SECRET", config.feishu_app_secret)
            os.environ["FEISHU_APP_SECRET"] = config.feishu_app_secret
            settings.FEISHU_APP_SECRET = config.feishu_app_secret

        if config.feishu_user_access_token is not None:
            set_key(env_file, "FEISHU_USER_ACCESS_TOKEN", config.feishu_user_access_token)
            os.environ["FEISHU_USER_ACCESS_TOKEN"] = config.feishu_user_access_token
            settings.FEISHU_USER_ACCESS_TOKEN = config.feishu_user_access_token

        if config.feishu_user_refresh_token is not None:
            set_key(env_file, "FEISHU_USER_REFRESH_TOKEN", config.feishu_user_refresh_token)
            os.environ["FEISHU_USER_REFRESH_TOKEN"] = config.feishu_user_refresh_token
            settings.FEISHU_USER_REFRESH_TOKEN = config.feishu_user_refresh_token

        if config.feishu_folder_token is not None:
            set_key(env_file, "FEISHU_FOLDER_TOKEN", config.feishu_folder_token)
            os.environ["FEISHU_FOLDER_TOKEN"] = config.feishu_folder_token
            settings.FEISHU_FOLDER_TOKEN = config.feishu_folder_token

        if config.llm_base_url is not None:
            set_key(env_file, "LLM_BASE_URL", config.llm_base_url)
            os.environ["LLM_BASE_URL"] = config.llm_base_url
            settings.LLM_BASE_URL = config.llm_base_url

        if config.llm_api_key is not None:
            set_key(env_file, "LLM_API_KEY", config.llm_api_key)
            os.environ["LLM_API_KEY"] = config.llm_api_key
            settings.LLM_API_KEY = config.llm_api_key

        if config.llm_model is not None:
            set_key(env_file, "LLM_MODEL", config.llm_model)
            os.environ["LLM_MODEL"] = config.llm_model
            settings.LLM_MODEL = config.llm_model

        logger.info("系统配置已更新")
        return {"message": "配置已更新"}

    except Exception as e:
        logger.error(f"更新系统配置失败: {str(e)}", exc_info = True)
        raise HTTPException(status_code = 500, detail = f"更新配置失败: {str(e)}")
