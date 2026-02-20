"""Task management API.

Provides task list, detail, delete, and retry endpoints.
"""

import os
import sys
import logging
from typing import List

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

sys.path.append(os.getcwd())

from web.models.task import Task, TaskStatus
from web.api.task_helpers import get_task_or_404
from web.tasks.import_task import start_import_task

router = APIRouter()
logger = logging.getLogger(__name__)


class TaskList(BaseModel):
    """Task list payload."""
    total: int
    tasks: List[dict]


@router.get("/", response_model = TaskList)
async def get_tasks(page: int = 1, page_size: int = 10, status: str = None):
    """Return task list."""
    try:
        logger.info(f"获取任务列表: 第{page}页，每页{page_size}条")

        tasks = Task.get_all()

        # Status filtering
        if status:
            tasks = [task for task in tasks if task.status == status]

        # Pagination
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paged_tasks = tasks[start_idx:end_idx]

        # Format output
        formatted_tasks = []
        for task in paged_tasks:
            formatted_tasks.append({
                "task_id": task.task_id,
                "source_type": task.source_type,
                "path": task.path,
                "write_mode": task.write_mode,
                "status": task.status,
                "progress": task.progress,
                "total": task.total,
                "success": task.success,
                "failed": task.failed,
                "skipped": task.skipped,
                "start_time": task.start_time,
                "end_time": task.end_time
            })

        logger.info(f"返回任务数量: {len(formatted_tasks)}")
        return {
            "total": len(tasks),
            "tasks": formatted_tasks
        }

    except Exception as e:
        logger.error(f"获取任务列表失败: {str(e)}", exc_info = True)
        raise HTTPException(status_code = 500, detail = f"获取任务列表失败: {str(e)}")


@router.get("/{task_id}")
async def get_task_detail(task_id: str):
    """Return task detail."""
    try:
        logger.info(f"获取任务详情: {task_id}")

        task = get_task_or_404(task_id = task_id)

        return {
            "task_id": task.task_id,
            "source_type": task.source_type,
            "path": task.path,
            "write_mode": task.write_mode,
            "space_name": task.space_name,
            "branch": task.branch,
            "commit": task.commit,
            "max_workers": task.max_workers,
            "chunk_workers": task.chunk_workers,
            "notify_level": task.notify_level,
            "dry_run": task.dry_run,
            "status": task.status,
            "progress": task.progress,
            "message": task.message,
            "total": task.total,
            "success": task.success,
            "failed": task.failed,
            "skipped": task.skipped,
            "failures": task.failures,
            "skipped_items": task.skipped_items,
            "created_docs": task.created_docs,
            "start_time": task.start_time,
            "end_time": task.end_time
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取任务详情失败: {str(e)}", exc_info = True)
        raise HTTPException(status_code = 500, detail = f"获取任务详情失败: {str(e)}")


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    """Delete task."""
    try:
        logger.info(f"删除任务: {task_id}")

        task = get_task_or_404(task_id = task_id)

        Task.delete(task_id)
        logger.info(f"任务已删除: {task_id}")

        return {"message": "任务已删除"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除任务失败: {str(e)}", exc_info = True)
        raise HTTPException(status_code = 500, detail = f"删除任务失败: {str(e)}")


@router.post("/{task_id}/retry")
async def retry_task(task_id: str):
    """Retry task."""
    try:
        logger.info(f"重试任务: {task_id}")

        task = get_task_or_404(task_id = task_id)

        if task.status == TaskStatus.RUNNING:
            raise HTTPException(status_code = 400, detail = "任务正在运行，无法重试")

        # Create new task
        new_task_id = Task.create_from_task(task)

        # Start async task
        request = {
            "source_type": task.source_type,
            "path": task.path,
            "write_mode": task.write_mode,
            "space_name": task.space_name,
            "branch": task.branch,
            "commit": task.commit,
            "max_workers": task.max_workers,
            "chunk_workers": task.chunk_workers,
            "notify_level": task.notify_level,
            "dry_run": task.dry_run
        }

        start_import_task.delay(new_task_id, request)

        logger.info(f"任务重试已启动: {new_task_id}")
        return {"task_id": new_task_id, "message": "任务已重试"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重试任务失败: {str(e)}", exc_info = True)
        raise HTTPException(status_code = 500, detail = f"重试任务失败: {str(e)}")
