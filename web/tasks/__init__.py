"""
任务队列模块

提供任务异步处理功能
"""

import logging
import os

from celery import Celery

from web.config import settings

logger = logging.getLogger(__name__)

# 创建Celery应用（使用内存broker和backend，不需要Redis）
celery_app = Celery(
    "tasks",
    broker = "memory://",
    backend = "cache+memory://"
)

# 配置Celery
celery_app.conf.update(
    task_serializer = "json",
    accept_content = ["json"],
    result_serializer = "json",
    timezone = "Asia/Shanghai",
    enable_utc = True,
    task_track_started = True,
    task_time_limit = 3600,  # 任务超时时间（秒）
    broker_connection_retry_on_startup = True
)

# 自动发现任务
celery_app.autodiscover_tasks(
    ["web.tasks"],
    force = True
)
