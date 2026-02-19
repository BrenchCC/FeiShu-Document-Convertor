"""
导入任务实现

提供任务异步处理功能
"""

import logging
import os
import time

from celery import shared_task
from web.models.task import Task, TaskStatus
from core.orchestrator import ImportOrchestrator
from data.source_adapters import LocalSourceAdapter, GitHubSourceAdapter
from utils.http_client import HttpClient
from utils.markdown_processor import MarkdownProcessor
from config.config import AppConfig
from integrations.feishu_api import FeishuAuthClient
from integrations.feishu_api import DocWriterService
from integrations.feishu_api import MediaService
from integrations.feishu_api import WikiService
from integrations.feishu_api import NotifyService
from integrations.feishu_api import WebhookNotifyService
from integrations.feishu_api import FeishuUserTokenManager
from integrations.llm_client import OpenAICompatibleLlmClient

logger = logging.getLogger(__name__)


@shared_task(bind = True, max_retries = 3)
def start_import_task(self, task_id: str, request: dict):
    """开始导入任务"""
    logger.info(f"开始执行导入任务: {task_id}")

    task = Task.get(task_id)
    if not task:
        logger.error(f"任务 {task_id} 不存在")
        return

    try:
        # 更新任务状态为运行中
        task.status = TaskStatus.RUNNING
        task.start_time = time.time()
        task.save()

        # 加载配置
        config = AppConfig.from_env()

        # 初始化 HTTP 客户端
        http_client = HttpClient(
            timeout = config.request_timeout,
            max_retries = config.max_retries,
            retry_backoff = config.retry_backoff
        )
        is_dry_run = bool(request.get("dry_run", False))
        if (
            not is_dry_run
            and request["write_mode"] in {"folder", "both"}
            and _is_placeholder_folder_token(
                token = config.feishu_folder_token
            )
        ):
            logger.warning(
                "FEISHU_FOLDER_TOKEN looks like placeholder value: %s. "
                "Skip pre-check and continue request; Feishu API will return explicit error if invalid.",
                config.feishu_folder_token
            )

        # 初始化源适配器
        if request["source_type"] == "local":
            adapter = LocalSourceAdapter(root_path = request["path"])
        elif request["source_type"] == "github":
            adapter = GitHubSourceAdapter(
                repo = request["path"],
                ref = request.get("ref") or request.get("branch", "main"),
                subdir = request.get("subdir", ""),
                http_client = http_client
            )
        else:
            raise ValueError(f"不支持的源类型: {request['source_type']}")

        # 初始化 Markdown 处理器
        markdown_processor = MarkdownProcessor()

        # 初始化 LLM 客户端
        llm_client = None
        if config.llm_base_url and config.llm_api_key and config.llm_model:
            llm_client = OpenAICompatibleLlmClient(
                base_url = config.llm_base_url,
                api_key = config.llm_api_key,
                model = config.llm_model,
                http_client = http_client
            )
            if not llm_client.is_ready():
                logger.warning(
                    "LLM 配置不完整，将继续使用规则引擎"
                )
                llm_client = None

        # 根据是否为 dry_run 初始化服务
        if request["dry_run"]:
            orchestrator = ImportOrchestrator(
                source_adapter = adapter,
                markdown_processor = markdown_processor,
                config = config,
                llm_client = llm_client
            )
        else:
            # 初始化认证客户端
            app_auth = FeishuAuthClient(
                app_id = config.feishu_app_id,
                app_secret = config.feishu_app_secret,
                base_url = config.feishu_base_url,
                http_client = http_client
            )

            # 初始化文档写入服务
            doc_writer = DocWriterService(
                auth_client = app_auth,
                http_client = http_client,
                base_url = config.feishu_base_url,
                folder_token = config.feishu_folder_token if request["write_mode"] in {"folder", "both"} else "",
                convert_max_bytes = config.feishu_convert_max_bytes,
                chunk_workers = int(request.get("chunk_workers", 2))
            )

            # 初始化媒体上传服务
            media_service = MediaService(
                auth_client = app_auth,
                http_client = http_client,
                base_url = config.feishu_base_url
            )

            # 初始化 Wiki 服务（如果需要）
            wiki_service = None
            user_token_manager = None
            if request["write_mode"] in {"wiki", "both"}:
                user_token_manager = FeishuUserTokenManager(
                    app_id = config.feishu_app_id,
                    app_secret = config.feishu_app_secret,
                    base_url = config.feishu_base_url,
                    http_client = http_client,
                    access_token = config.feishu_user_access_token,
                    refresh_token = config.feishu_user_refresh_token,
                    cache_path = config.feishu_user_token_cache_path
                )

                wiki_service = WikiService(
                    auth_client = app_auth,
                    http_client = http_client,
                    base_url = config.feishu_base_url,
                    user_access_token = config.feishu_user_access_token,
                    user_token_manager = user_token_manager
                )

            # 初始化通知服务
            notify_service = None
            if request.get("notify_level", "normal") != "none":
                if config.feishu_webhook_url:
                    notify_service = WebhookNotifyService(
                        webhook_url = config.feishu_webhook_url,
                        http_client = http_client,
                        max_bytes = config.feishu_message_max_bytes
                    )
                else:
                    notify_service = NotifyService(
                        auth_client = app_auth,
                        http_client = http_client,
                        base_url = config.feishu_base_url,
                        max_bytes = config.feishu_message_max_bytes
                    )

            # 创建编排器
            orchestrator = ImportOrchestrator(
                source_adapter = adapter,
                markdown_processor = markdown_processor,
                config = config,
                doc_writer = doc_writer,
                media_service = media_service,
                wiki_service = wiki_service,
                notify_service = notify_service,
                llm_client = llm_client
            )

        # 执行导入
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

        # 更新任务结果
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

    except Exception as e:
        logger.error(f"任务 {task_id} 执行失败: {str(e)}", exc_info = True)

        # 更新任务状态为失败
        task.status = TaskStatus.FAILED
        task.end_time = time.time()
        task.message = str(e)
        task.save()
        async_execution = os.getenv("ASYNC_TASK_EXECUTION", "false").lower() == "true"
        if isinstance(e, ValueError) or not async_execution:
            raise
        raise self.retry(exc = e, countdown = 30)


def _is_placeholder_folder_token(token: str) -> bool:
    """Check whether one folder token looks like placeholder test value.

    Args:
        token: Folder token text.
    """

    normalized = (token or "").strip().lower()
    if not normalized:
        return False

    placeholders = {
        "test_folder_token",
        "your_folder_token",
        "example_folder_token",
        "folder_token",
        "<folder_token>"
    }
    if normalized in placeholders:
        return True
    if normalized.startswith("${") and normalized.endswith("}"):
        return True
    return False
