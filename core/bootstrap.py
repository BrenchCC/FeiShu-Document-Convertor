import os
import sys
import logging
from typing import Optional


sys.path.append(os.getcwd())

from config.config import AppConfig
from core.orchestrator import ImportOrchestrator
from data.source_adapters import GitHubSourceAdapter
from data.source_adapters import LocalSourceAdapter
from data.source_adapters import SourceAdapter
from integrations.feishu_api import DocWriterService
from integrations.feishu_api import FeishuAuthClient
from integrations.feishu_api import FeishuUserTokenManager
from integrations.feishu_api import MediaService
from integrations.feishu_api import NotifyService
from integrations.feishu_api import WebhookNotifyService
from integrations.feishu_api import WikiService
from integrations.llm_client import OpenAICompatibleLlmClient
from utils.http_client import HttpClient
from utils.markdown_processor import MarkdownProcessor


logger = logging.getLogger(__name__)


def build_http_client(config: AppConfig) -> HttpClient:
    """Create shared HTTP client from config.

    Args:
        config: Runtime configuration.
    """

    return HttpClient(
        timeout = config.request_timeout,
        max_retries = config.max_retries,
        retry_backoff = config.retry_backoff
    )


def build_markdown_processor() -> MarkdownProcessor:
    """Create markdown processor instance.

    Args:
        None
    """

    return MarkdownProcessor()


def build_llm_client(
    config: AppConfig,
    http_client: HttpClient,
    enable: bool
) -> Optional[OpenAICompatibleLlmClient]:
    """Create LLM client when enabled and ready.

    Args:
        config: Runtime configuration.
        http_client: Shared HTTP client.
        enable: Whether LLM fallback is enabled.
    """

    if not enable:
        return None
    client = OpenAICompatibleLlmClient(
        base_url = config.llm_base_url,
        api_key = config.llm_api_key,
        model = config.llm_model,
        http_client = http_client
    )
    if not client.is_ready():
        logger.warning(
            "LLM fallback enabled but LLM_BASE_URL/LLM_API_KEY/LLM_MODEL are incomplete."
        )
        return None
    return client


def build_user_token_manager(
    config: AppConfig,
    http_client: HttpClient
) -> FeishuUserTokenManager:
    """Create Feishu user token manager.

    Args:
        config: Runtime configuration.
        http_client: Shared HTTP client.
    """

    return FeishuUserTokenManager(
        app_id = config.feishu_app_id,
        app_secret = config.feishu_app_secret,
        base_url = config.feishu_base_url,
        http_client = http_client,
        access_token = config.feishu_user_access_token,
        refresh_token = config.feishu_user_refresh_token,
        cache_path = config.feishu_user_token_cache_path
    )


def build_app_auth(
    config: AppConfig,
    http_client: HttpClient
) -> FeishuAuthClient:
    """Create Feishu app auth client.

    Args:
        config: Runtime configuration.
        http_client: Shared HTTP client.
    """

    return FeishuAuthClient(
        app_id = config.feishu_app_id,
        app_secret = config.feishu_app_secret,
        base_url = config.feishu_base_url,
        http_client = http_client
    )


def build_doc_writer(
    config: AppConfig,
    http_client: HttpClient,
    app_auth: FeishuAuthClient,
    write_mode: str,
    chunk_workers: int
) -> DocWriterService:
    """Create Feishu doc writer service.

    Args:
        config: Runtime configuration.
        http_client: Shared HTTP client.
        app_auth: App auth client.
        write_mode: Write mode.
        chunk_workers: Chunk worker count.
    """

    folder_token = config.feishu_folder_token if write_mode in {"folder", "both"} else ""
    return DocWriterService(
        auth_client = app_auth,
        http_client = http_client,
        base_url = config.feishu_base_url,
        folder_token = folder_token,
        convert_max_bytes = config.feishu_convert_max_bytes,
        chunk_workers = int(chunk_workers)
    )


def build_media_service(
    config: AppConfig,
    http_client: HttpClient,
    app_auth: FeishuAuthClient
) -> MediaService:
    """Create Feishu media service.

    Args:
        config: Runtime configuration.
        http_client: Shared HTTP client.
        app_auth: App auth client.
    """

    return MediaService(
        auth_client = app_auth,
        http_client = http_client,
        base_url = config.feishu_base_url
    )


def build_wiki_service(
    config: AppConfig,
    http_client: HttpClient,
    app_auth: FeishuAuthClient,
    write_mode: str,
    user_token_manager: Optional[FeishuUserTokenManager]
) -> Optional[WikiService]:
    """Create Feishu wiki service when write mode requires it.

    Args:
        config: Runtime configuration.
        http_client: Shared HTTP client.
        app_auth: App auth client.
        write_mode: Write mode.
        user_token_manager: Optional user token manager.
    """

    if write_mode not in {"wiki", "both"}:
        return None
    return WikiService(
        auth_client = app_auth,
        http_client = http_client,
        base_url = config.feishu_base_url,
        user_access_token = config.feishu_user_access_token,
        user_token_manager = user_token_manager
    )


def build_notify_service(
    config: AppConfig,
    http_client: HttpClient,
    app_auth: FeishuAuthClient,
    notify_level: str,
    allow_missing_chat_id: bool,
    chat_id: str = ""
) -> Optional[object]:
    """Create Feishu notification service based on config.

    Args:
        config: Runtime configuration.
        http_client: Shared HTTP client.
        app_auth: App auth client.
        notify_level: Notification level.
        allow_missing_chat_id: Whether to allow NotifyService without chat id.
        chat_id: Optional chat id for notification.
    """

    if notify_level == "none":
        return None
    if config.feishu_webhook_url:
        return WebhookNotifyService(
            webhook_url = config.feishu_webhook_url,
            http_client = http_client,
            max_bytes = config.feishu_message_max_bytes
        )
    if chat_id or allow_missing_chat_id:
        return NotifyService(
            auth_client = app_auth,
            http_client = http_client,
            base_url = config.feishu_base_url,
            max_bytes = config.feishu_message_max_bytes
        )
    return None


def build_orchestrator(
    config: AppConfig,
    source_adapter: SourceAdapter,
    http_client: HttpClient,
    write_mode: str,
    dry_run: bool,
    chunk_workers: int,
    notify_level: str,
    enable_llm: bool,
    chat_id: str = "",
    user_token_manager: Optional[FeishuUserTokenManager] = None,
    allow_missing_chat_id: bool = False
) -> ImportOrchestrator:
    """Build orchestrator and its dependencies.

    Args:
        config: Runtime configuration.
        source_adapter: Source adapter.
        http_client: Shared HTTP client.
        write_mode: Write mode.
        dry_run: Whether to skip Feishu writes.
        chunk_workers: Chunk worker count.
        notify_level: Notification level.
        enable_llm: Whether to enable LLM fallback.
        chat_id: Chat id used for notifications.
        user_token_manager: Optional user token manager.
        allow_missing_chat_id: Whether to allow NotifyService without chat id.
    """

    markdown_processor = build_markdown_processor()
    llm_client = build_llm_client(
        config = config,
        http_client = http_client,
        enable = enable_llm
    )

    if dry_run:
        return ImportOrchestrator(
            source_adapter = source_adapter,
            markdown_processor = markdown_processor,
            config = config,
            llm_client = llm_client
        )

    app_auth = build_app_auth(config = config, http_client = http_client)
    doc_writer = build_doc_writer(
        config = config,
        http_client = http_client,
        app_auth = app_auth,
        write_mode = write_mode,
        chunk_workers = chunk_workers
    )
    media_service = build_media_service(
        config = config,
        http_client = http_client,
        app_auth = app_auth
    )
    wiki_service = build_wiki_service(
        config = config,
        http_client = http_client,
        app_auth = app_auth,
        write_mode = write_mode,
        user_token_manager = user_token_manager
    )
    notify_service = build_notify_service(
        config = config,
        http_client = http_client,
        app_auth = app_auth,
        notify_level = notify_level,
        allow_missing_chat_id = allow_missing_chat_id,
        chat_id = chat_id
    )

    return ImportOrchestrator(
        source_adapter = source_adapter,
        markdown_processor = markdown_processor,
        config = config,
        doc_writer = doc_writer,
        media_service = media_service,
        wiki_service = wiki_service,
        notify_service = notify_service,
        llm_client = llm_client
    )


def build_source_adapter_from_cli(
    source: str,
    path: str,
    repo: str,
    ref: str,
    subdir: str,
    http_client: HttpClient
) -> SourceAdapter:
    """Build source adapter from CLI inputs.

    Args:
        source: Source type (local/github).
        path: Local path when source is local.
        repo: Repo when source is github.
        ref: Repo ref when source is github.
        subdir: Repo subdir when source is github.
        http_client: Shared HTTP client.
    """

    if source == "local":
        return LocalSourceAdapter(root_path = path)
    return GitHubSourceAdapter(
        repo = repo,
        ref = ref,
        subdir = subdir,
        http_client = http_client
    )


def build_source_adapter_from_request(
    request: dict,
    http_client: HttpClient
) -> SourceAdapter:
    """Build source adapter from API request payload.

    Args:
        request: Web request dict.
        http_client: Shared HTTP client.
    """

    source_type = request.get("source_type", "")
    if source_type == "local":
        return LocalSourceAdapter(root_path = request["path"])
    if source_type == "github":
        return GitHubSourceAdapter(
            repo = request["path"],
            ref = request.get("ref") or request.get("branch", "main"),
            subdir = request.get("subdir", ""),
            http_client = http_client
        )
    raise ValueError(f"Unsupported source type: {source_type}")


def validate_runtime_credentials(
    config: AppConfig,
    write_mode: str,
    notify_level: str,
    chat_id: str,
    has_user_token_override: bool = False
) -> None:
    """Validate required credentials for non-dry-run execution.

    Args:
        config: Runtime configuration.
        write_mode: Write mode.
        notify_level: Notification level.
        chat_id: Chat id used for notifications.
        has_user_token_override: Extra user token source indicator.
    """

    writer_missing = []
    if not config.feishu_app_id:
        writer_missing.append("FEISHU_APP_ID")
    if not config.feishu_app_secret:
        writer_missing.append("FEISHU_APP_SECRET")
    if writer_missing:
        raise ValueError(f"Missing app bot env: {', '.join(writer_missing)}")

    if notify_level != "none" and not config.feishu_webhook_url and not chat_id:
        raise ValueError(
            "Notification enabled but no target configured. "
            "Set FEISHU_WEBHOOK_URL or pass --chat-id."
        )

    has_token_cache = os.path.exists(config.feishu_user_token_cache_path)
    has_user_token_source = any(
        [
            config.feishu_user_access_token,
            config.feishu_user_refresh_token,
            has_token_cache,
            has_user_token_override
        ]
    )
    if write_mode in {"wiki", "both"} and not has_user_token_source:
        logger.warning(
            "FEISHU_USER_ACCESS_TOKEN/FEISHU_USER_REFRESH_TOKEN are empty. "
            "If target space does not exist, auto-create will fail; "
            "you can pass --space-id to reuse existing space."
        )

    if write_mode in {"folder", "both"} and not config.feishu_folder_token:
        raise ValueError(
            "FEISHU_FOLDER_TOKEN is required when --write-mode is folder or both"
        )
    if write_mode in {"folder", "both"} and is_placeholder_folder_token(
        token = config.feishu_folder_token
    ):
        raise ValueError(
            "FEISHU_FOLDER_TOKEN looks like a placeholder value. "
            "Please set a real Feishu folder token before folder import."
        )


def is_placeholder_folder_token(token: str) -> bool:
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
