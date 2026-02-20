"""Notification management API.

Provides Feishu webhook and chat-id notifications.
"""

import os
import sys
import logging
from typing import List
from typing import Optional

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

sys.path.append(os.getcwd())

from integrations.feishu_api import NotifyService, WebhookNotifyService

router = APIRouter()
logger = logging.getLogger(__name__)


class TestNotificationRequest(BaseModel):
    """Notification test request."""
    webhook_url: Optional[str] = None
    chat_id: Optional[str] = None
    level: str = "normal"


class TestNotificationResult(BaseModel):
    """Notification test response."""
    success: bool
    message: str
    webhook_sent: Optional[bool] = None
    chat_id_sent: Optional[bool] = None


@router.post("/test", response_model = TestNotificationResult)
async def test_notification(request: TestNotificationRequest):
    """Test notification channels."""
    try:
        logger.info("测试通知功能")

        results = {
            "success": False,
            "message": "",
            "webhook_sent": False,
            "chat_id_sent": False
        }

        sent_count = 0

        # Test webhook notification
        if request.webhook_url:
            try:
                from utils.http_client import HttpClient
                http_client = HttpClient()
                notify_service = WebhookNotifyService(request.webhook_url, http_client)
                notify_service.send_status(
                    "",
                    "这是一个测试通知，用于验证通知功能是否正常工作。"
                )
                results["webhook_sent"] = True
                sent_count += 1
            except Exception as e:
                logger.error(f"Webhook通知失败: {str(e)}")
                results["message"] += f"Webhook通知失败: {str(e)}\n"

        # Test chat-id notification
        if request.chat_id:
            try:
                from web.config import settings
                from integrations.feishu_api import FeishuAuthClient
                http_client = HttpClient()
                auth_client = FeishuAuthClient(
                    app_id = settings.FEISHU_APP_ID or "",
                    app_secret = settings.FEISHU_APP_SECRET or "",
                    base_url = "https://open.feishu.cn",
                    http_client = http_client
                )
                notify_service = NotifyService(auth_client, http_client, "https://open.feishu.cn")
                notify_service.send_status(
                    request.chat_id,
                    "这是一个测试通知，用于验证通知功能是否正常工作。"
                )
                results["chat_id_sent"] = True
                sent_count += 1
            except Exception as e:
                logger.error(f"Chat ID通知失败: {str(e)}")
                results["message"] += f"Chat ID通知失败: {str(e)}\n"

        if sent_count == 0:
            results["success"] = False
            if not results["message"]:
                results["message"] = "未提供有效的通知方式"
        else:
            results["success"] = True
            if not results["message"]:
                results["message"] = "通知测试成功"

        logger.info(f"通知测试完成: 成功发送{sent_count}个通知")
        return results

    except Exception as e:
        logger.error(f"测试通知失败: {str(e)}", exc_info = True)
        raise HTTPException(status_code = 500, detail = f"测试通知失败: {str(e)}")


@router.post("/webhook")
async def send_webhook_notification(
    webhook_url: str,
    title: str,
    content: str,
    level: str = "normal"
):
    """Send webhook notification."""
    try:
        logger.info(f"发送Webhook通知: {title}")

        from utils.http_client import HttpClient
        http_client = HttpClient()
        notify_service = WebhookNotifyService(webhook_url, http_client)
        notify_service.send_status("", f"{title}\n\n{content}")

        return {"success": True, "message": "通知已发送"}

    except Exception as e:
        logger.error(f"发送Webhook通知失败: {str(e)}", exc_info = True)
        raise HTTPException(status_code = 500, detail = f"发送通知失败: {str(e)}")


@router.post("/chat_id")
async def send_chat_id_notification(
    chat_id: str,
    title: str,
    content: str,
    level: str = "normal"
):
    """Send chat-id notification."""
    try:
        logger.info(f"发送Chat ID通知: {title}")

        from web.config import settings
        from integrations.feishu_api import FeishuAuthClient
        from utils.http_client import HttpClient
        http_client = HttpClient()
        auth_client = FeishuAuthClient(
            app_id = settings.FEISHU_APP_ID or "",
            app_secret = settings.FEISHU_APP_SECRET or "",
            base_url = "https://open.feishu.cn",
            http_client = http_client
        )
        notify_service = NotifyService(auth_client, http_client, "https://open.feishu.cn")
        notify_service.send_status(chat_id, f"{title}\n\n{content}")

        return {"success": True, "message": "通知已发送"}

    except Exception as e:
        logger.error(f"发送Chat ID通知失败: {str(e)}", exc_info = True)
        raise HTTPException(status_code = 500, detail = f"发送通知失败: {str(e)}")
