"""
Import management API.

Provides task creation, status querying, and result retrieval.
"""
import os
import sys
import uuid
import logging
from typing import List
from typing import Optional

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

sys.path.append(os.getcwd())

from web.models.task import Task, TaskStatus
from web.api.task_helpers import get_task_or_404

router = APIRouter()
logger = logging.getLogger(__name__)


class ImportRequest(BaseModel):
    """Import request payload."""
    source_type: str  # "local" or "github"
    path: str
    write_mode: str  # "folder", "wiki", "both"
    space_name: Optional[str] = None
    space_id: Optional[str] = None
    chat_id: Optional[str] = None
    ref: Optional[str] = None
    branch: Optional[str] = None
    commit: Optional[str] = None
    subdir: Optional[str] = None
    import_type: Optional[str] = "directory"
    structure_order: str = "toc_first"
    toc_file: str = "TABLE_OF_CONTENTS.md"
    folder_subdirs: bool = False
    folder_root_subdir: bool = True
    folder_root_subdir_name: str = ""
    folder_nav_doc: bool = True
    folder_nav_title: str = "00-导航总目录"
    llm_fallback: str = "toc_ambiguity"
    llm_max_calls: int = 3
    skip_root_readme: bool = False
    max_workers: int = 1
    chunk_workers: int = 2
    notify_level: str = "normal"
    dry_run: bool = False


class ImportResult(BaseModel):
    """Import result payload."""
    task_id: str
    status: str
    total: int
    success: int
    failed: int
    skipped: int
    failures: List[str]
    skipped_items: List[str]
    created_docs: List[str]


@router.post("/start")
async def start_import(request: ImportRequest):
    """Start an import task."""
    try:
        task_id = str(uuid.uuid4())
        logger.info(f"开始导入任务: {task_id} - {request.source_type}")

        task = Task(
            task_id = task_id,
            source_type = request.source_type,
            path = request.path,
            write_mode = request.write_mode,
            space_name = request.space_name,
            branch = request.ref or request.branch,
            commit_hash = request.commit,
            max_workers = request.max_workers,
            chunk_workers = request.chunk_workers,
            notify_level = request.notify_level,
            dry_run = request.dry_run
        )

        task.save()

        from web.tasks.import_task import start_import_task
        if os.getenv("ASYNC_TASK_EXECUTION", "false").lower() == "true":
            logger.info("异步执行任务（需要Celery和Redis）")
            start_import_task.delay(task_id, request.model_dump())
        else:
            logger.info("同步执行任务（离线模式）")
            start_import_task(task_id, request.model_dump())

        logger.info(f"导入任务已启动: {task_id}")
        return {"task_id": task_id, "status": "started"}

    except Exception as exc:
        logger.error(f"启动导入任务失败: {str(exc)}", exc_info = True)
        raise HTTPException(status_code = 500, detail = f"启动任务失败: {str(exc)}")


@router.get("/status/{task_id}")
async def get_import_status(task_id: str):
    """Return task status."""
    try:
        logger.info(f"获取任务状态: {task_id}")

        task = get_task_or_404(task_id = task_id)

        return {
            "task_id": task_id,
            "status": task.status,
            "progress": task.progress,
            "message": task.message,
            "start_time": task.start_time,
            "end_time": task.end_time
        }

    except Exception as exc:
        logger.error(f"获取任务状态失败: {str(exc)}", exc_info = True)
        raise HTTPException(status_code = 500, detail = f"获取任务状态失败: {str(exc)}")


@router.get("/result/{task_id}", response_model = ImportResult)
async def get_import_result(task_id: str):
    """Return task result."""
    try:
        logger.info(f"获取任务结果: {task_id}")

        task = get_task_or_404(task_id = task_id)
        if task.status != TaskStatus.COMPLETED:
            raise HTTPException(status_code = 400, detail = "任务尚未完成")

        return {
            "task_id": task_id,
            "status": task.status,
            "total": task.total,
            "success": task.success,
            "failed": task.failed,
            "skipped": task.skipped,
            "failures": task.failures,
            "skipped_items": task.skipped_items,
            "created_docs": task.created_docs
        }

    except Exception as exc:
        logger.error(f"获取任务结果失败: {str(exc)}", exc_info = True)
        raise HTTPException(status_code = 500, detail = f"获取任务结果失败: {str(exc)}")


@router.post("/cancel/{task_id}")
async def cancel_import_task(task_id: str):
    """Cancel an import task."""
    try:
        logger.info(f"取消任务: {task_id}")

        task = get_task_or_404(task_id = task_id)

        if task.status != TaskStatus.RUNNING:
            raise HTTPException(status_code = 400, detail = "任务已完成或失败，无法取消")

        task.status = TaskStatus.CANCELLED
        task.message = "任务已取消"
        task.save()

        logger.info(f"任务已取消: {task_id}")
        return {"message": "任务已取消"}

    except Exception as exc:
        logger.error(f"取消任务失败: {str(exc)}", exc_info = True)
        raise HTTPException(status_code = 500, detail = f"取消任务失败: {str(exc)}")
