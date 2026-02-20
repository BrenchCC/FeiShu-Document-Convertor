"""
Dependency injection utilities for FastAPI.
"""
import os
import sys
import logging

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

sys.path.append(os.getcwd())

from web.config import settings


logger = logging.getLogger(__name__)

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Return current user for API requests.

    Args:
        credentials: Authorization credentials.
    """

    expected_token = settings.SECRET_KEY
    if credentials.credentials != expected_token:
        raise HTTPException(status_code = 401, detail = "无效的访问令牌")

    logger.debug("用户认证成功")
    return {"user_id": "admin", "username": "管理员"}


def get_db_session():
    """Return a placeholder database session.

    Args:
        None
    """

    return {"session": "database_session"}
