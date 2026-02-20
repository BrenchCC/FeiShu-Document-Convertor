"""Task queue module.

Provides asynchronous task execution helpers.
"""

import logging
import os

from celery import Celery

from web.config import settings

logger = logging.getLogger(__name__)

# Create Celery app with memory broker/backend (no Redis required)
celery_app = Celery(
    "tasks",
    broker = "memory://",
    backend = "cache+memory://"
)

# Configure Celery
celery_app.conf.update(
    task_serializer = "json",
    accept_content = ["json"],
    result_serializer = "json",
    timezone = "Asia/Shanghai",
    enable_utc = True,
    task_track_started = True,
    task_time_limit = 3600,  # Task timeout (seconds)
    broker_connection_retry_on_startup = True
)

# Auto-discover tasks
celery_app.autodiscover_tasks(
    ["web.tasks"],
    force = True
)
