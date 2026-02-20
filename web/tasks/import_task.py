"""
Import task implementation.

Runs asynchronous or synchronous import tasks.
"""
import os
import sys
import time
import logging

from celery import shared_task

sys.path.append(os.getcwd())

from config.config import AppConfig
from core.bootstrap import build_http_client
from core.bootstrap import build_orchestrator
from core.bootstrap import build_source_adapter_from_request
from core.bootstrap import build_user_token_manager
from core.bootstrap import is_placeholder_folder_token
from web.models.task import Task, TaskStatus


logger = logging.getLogger(__name__)


@shared_task(bind = True, max_retries = 3)
def start_import_task(self, task_id: str, request: dict):
    """Start import task.

    Args:
        self: Celery task instance.
        task_id: Task id.
        request: Request payload.
    """

    logger.info(f"开始执行导入任务: {task_id}")

    task = Task.get(task_id)
    if not task:
        logger.error(f"任务 {task_id} 不存在")
        return

    try:
        task.status = TaskStatus.RUNNING
        task.start_time = time.time()
        task.save()

        config = AppConfig.from_env()
        http_client = build_http_client(config = config)
        is_dry_run = bool(request.get("dry_run", False))
        if (
            not is_dry_run
            and request["write_mode"] in {"folder", "both"}
            and is_placeholder_folder_token(
                token = config.feishu_folder_token
            )
        ):
            logger.warning(
                "FEISHU_FOLDER_TOKEN looks like placeholder value: %s. "
                "Skip pre-check and continue request; Feishu API will return explicit error if invalid.",
                config.feishu_folder_token
            )

        adapter = build_source_adapter_from_request(
            request = request,
            http_client = http_client
        )
        user_token_manager = None
        if request.get("write_mode") in {"wiki", "both"}:
            user_token_manager = build_user_token_manager(
                config = config,
                http_client = http_client
            )

        enable_llm = request.get("llm_fallback", "toc_ambiguity") == "toc_ambiguity"
        orchestrator = build_orchestrator(
            config = config,
            source_adapter = adapter,
            http_client = http_client,
            write_mode = request.get("write_mode", "folder"),
            dry_run = bool(request.get("dry_run", False)),
            chunk_workers = int(request.get("chunk_workers", 2)),
            notify_level = request.get("notify_level", "normal"),
            enable_llm = enable_llm,
            chat_id = request.get("chat_id", "") or "",
            user_token_manager = user_token_manager,
            allow_missing_chat_id = True
        )

        result = orchestrator.run(
            space_name = request.get("space_name", ""),
            space_id = request.get("space_id", "") or "",
            chat_id = request.get("chat_id", "") or "",
            dry_run = bool(request.get("dry_run", False)),
            notify_level = request.get("notify_level", "normal"),
            write_mode = request["write_mode"],
            folder_subdirs = bool(request.get("folder_subdirs", False)),
            folder_root_subdir = bool(request.get("folder_root_subdir", True)),
            folder_root_subdir_name = request.get("folder_root_subdir_name", "") or "",
            structure_order = request.get("structure_order", "toc_first"),
            toc_file = request.get("toc_file", "TABLE_OF_CONTENTS.md"),
            folder_nav_doc = bool(request.get("folder_nav_doc", True)),
            folder_nav_title = request.get("folder_nav_title", "00-导航总目录"),
            llm_fallback = request.get("llm_fallback", "toc_ambiguity"),
            llm_max_calls = int(request.get("llm_max_calls", 3)),
            skip_root_readme = bool(request.get("skip_root_readme", False)),
            max_workers = int(request.get("max_workers", 1)),
            chunk_workers = int(request.get("chunk_workers", 2))
        )

        task.status = TaskStatus.COMPLETED
        task.end_time = time.time()
        task.total = result.total
        task.success = result.success
        task.failed = result.failed
        task.skipped = result.skipped
        task.failures = [str(failure) for failure in result.failures]
        task.skipped_items = [str(item) for item in result.skipped_items]
        task.created_docs = [doc.title for doc in result.created_docs]
        task.progress = 100
        task.message = "导入成功"
        task.save()

        logger.info(f"任务 {task_id} 执行完成")
        return {"status": "success", "result": result}

    except Exception as exc:
        logger.error("任务 %s 执行失败: %s", task_id, str(exc), exc_info = True)

        task.status = TaskStatus.FAILED
        task.end_time = time.time()
        task.message = str(exc)
        task.save()
        async_execution = os.getenv("ASYNC_TASK_EXECUTION", "false").lower() == "true"
        if isinstance(exc, ValueError) or not async_execution:
            raise
        raise self.retry(exc = exc, countdown = 30)
