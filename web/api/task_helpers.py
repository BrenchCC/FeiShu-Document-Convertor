"""Shared helpers for task-based APIs."""

import os
import sys

from fastapi import HTTPException

sys.path.append(os.getcwd())

from web.models.task import Task


def get_task_or_404(task_id: str) -> Task:
    """Return task or raise HTTP 404.

    Args:
        task_id: Task id string.
    """

    task = Task.get(task_id)
    if not task:
        raise HTTPException(status_code = 404, detail = "任务不存在")
    return task
