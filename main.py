import os
import sys
import argparse
import logging


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
from utils.oauth_local_auth import capture_oauth_code_by_local_server
from utils.oauth_local_auth import persist_user_tokens_to_env


logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for import command.

    Args:
        None
    """

    parser = argparse.ArgumentParser(
        description = "Import local/GitHub markdown into Feishu docx + wiki"
    )
    parser.add_argument(
        "--source",
        choices = ["local", "github"],
        required = True,
        help = "Source type"
    )
    parser.add_argument("--path", default = "", help = "Local source directory path")
    parser.add_argument("--repo", default = "", help = "GitHub repo owner/name or url")
    parser.add_argument("--ref", default = "main", help = "GitHub branch/tag/commit")
    parser.add_argument("--subdir", default = "", help = "GitHub subdirectory path")

    parser.add_argument("--auth-code", default = "", help = "One-time Feishu OAuth code to bootstrap user token")
    parser.add_argument("--oauth-redirect-uri", default = "", help = "OAuth redirect URI used with --auth-code")
    parser.add_argument(
        "--oauth-scope",
        default = "wiki:wiki offline_access",
        help = "OAuth scope used by --print-auth-url"
    )
    parser.add_argument("--oauth-state", default = "kg_state", help = "OAuth state used by --print-auth-url")
    parser.add_argument("--print-auth-url", action = "store_true", help = "Print OAuth authorize URL and exit")
    parser.add_argument(
        "--oauth-local-server",
        action = "store_true",
        help = "Start local callback server, capture code, and exchange token automatically"
    )
    parser.add_argument("--oauth-timeout", type = int, default = 300, help = "OAuth callback wait timeout seconds")
    parser.add_argument(
        "--oauth-open-browser",
        action = argparse.BooleanOptionalAction,
        default = True,
        help = "Open OAuth URL in browser automatically for local auth"
    )
    parser.add_argument(
        "--persist-user-token-env",
        action = argparse.BooleanOptionalAction,
        default = True,
        help = "Persist FEISHU_USER_ACCESS_TOKEN and FEISHU_USER_REFRESH_TOKEN into .env"
    )

    parser.add_argument("--space-name", default = "", help = "Feishu wiki space name")
    parser.add_argument("--space-id", default = "", help = "Existing Feishu wiki space id")
    parser.add_argument("--chat-id", default = "", help = "Feishu chat id for notifications")
    parser.add_argument(
        "--write-mode",
        choices = ["folder", "wiki", "both"],
        default = "folder",
        help = "Write target mode: folder/wiki/both"
    )
    parser.add_argument(
        "--folder-subdirs",
        action = argparse.BooleanOptionalAction,
        default = False,
        help = "When write-mode includes folder, auto-create subfolders by source directories"
    )
    parser.add_argument(
        "--structure-order",
        choices = ["toc_first", "path"],
        default = "toc_first",
        help = "Document ordering strategy for multi-markdown imports"
    )
    parser.add_argument(
        "--toc-file",
        default = "TABLE_OF_CONTENTS.md",
        help = "TOC markdown path relative to source root"
    )
    parser.add_argument(
        "--folder-nav-doc",
        action = argparse.BooleanOptionalAction,
        default = True,
        help = "Generate folder navigation document after markdown import"
    )
    parser.add_argument(
        "--folder-nav-title",
        default = "00-导航总目录",
        help = "Folder navigation document title"
    )
    parser.add_argument(
        "--llm-fallback",
        choices = ["off", "toc_ambiguity"],
        default = "toc_ambiguity",
        help = "LLM fallback mode for TOC ambiguity"
    )
    parser.add_argument(
        "--llm-max-calls",
        type = int,
        default = 3,
        help = "Maximum LLM fallback calls in one import run"
    )

    parser.add_argument("--dry-run", action = "store_true", help = "Parse only, no Feishu writes")
    parser.add_argument("--max-workers", type = int, default = 1, help = "Reserved for future parallelism")
    parser.add_argument(
        "--notify-level",
        choices = ["none", "minimal", "normal"],
        default = "normal",
        help = "Notification verbosity"
    )

    return parser.parse_args()


def main() -> int:
    """CLI entrypoint.

    Args:
        None
    """

    args = parse_args()
    config = AppConfig.from_env()

    if args.source == "local" and not args.path:
        raise ValueError("--path is required when --source local")
    if args.source == "github" and not args.repo:
        raise ValueError("--repo is required when --source github")
    if args.max_workers < 1:
        raise ValueError("--max-workers must be >= 1")
    if args.llm_max_calls < 0:
        raise ValueError("--llm-max-calls must be >= 0")
    if args.oauth_timeout < 1:
        raise ValueError("--oauth-timeout must be >= 1")
    if args.auth_code and not args.oauth_redirect_uri:
        raise ValueError("--oauth-redirect-uri is required when --auth-code is provided")
    if args.print_auth_url and not args.oauth_redirect_uri:
        raise ValueError("--oauth-redirect-uri is required when --print-auth-url")
    if args.oauth_local_server and not args.oauth_redirect_uri:
        raise ValueError("--oauth-redirect-uri is required when --oauth-local-server")
    if args.oauth_local_server and args.auth_code:
        raise ValueError("--oauth-local-server and --auth-code cannot be used together")
    if args.write_mode in {"wiki", "both"} and not args.space_name and not args.space_id:
        raise ValueError("--space-name or --space-id is required when --write-mode is wiki or both")
    if args.folder_subdirs and args.write_mode not in {"folder", "both"}:
        logger.warning("--folder-subdirs only applies when --write-mode is folder or both")

    if args.max_workers > 1:
        logger.warning("max_workers > 1 is reserved in v1; running sequentially")

    http_client = HttpClient(
        timeout = config.request_timeout,
        max_retries = config.max_retries,
        retry_backoff = config.retry_backoff
    )

    user_token_manager = None
    need_user_token_manager = (
        args.write_mode in {"wiki", "both"}
        or args.print_auth_url
        or args.oauth_local_server
    )
    if need_user_token_manager:
        user_token_manager = FeishuUserTokenManager(
            app_id = config.feishu_app_id,
            app_secret = config.feishu_app_secret,
            base_url = config.feishu_base_url,
            http_client = http_client,
            access_token = config.feishu_user_access_token,
            refresh_token = config.feishu_user_refresh_token,
            cache_path = config.feishu_user_token_cache_path
        )

    if args.print_auth_url:
        print(
            user_token_manager.build_authorize_url(
                redirect_uri = args.oauth_redirect_uri,
                scope = args.oauth_scope,
                state = args.oauth_state
            )
        )
        return 0

    if args.oauth_local_server:
        authorize_url = user_token_manager.build_authorize_url(
            redirect_uri = args.oauth_redirect_uri,
            scope = args.oauth_scope,
            state = args.oauth_state
        )
        auth_code = capture_oauth_code_by_local_server(
            authorize_url = authorize_url,
            redirect_uri = args.oauth_redirect_uri,
            timeout_seconds = args.oauth_timeout,
            open_browser = args.oauth_open_browser
        )
        user_token_manager.exchange_code_for_token(
            code = auth_code,
            redirect_uri = args.oauth_redirect_uri
        )
        logger.info(
            "OAuth local auth succeeded. token cache path = %s",
            config.feishu_user_token_cache_path
        )
        if args.persist_user_token_env:
            persist_user_tokens_to_env(
                access_token = user_token_manager.access_token,
                refresh_token = user_token_manager.refresh_token,
                token_cache_path = config.feishu_user_token_cache_path
            )
            logger.info("Updated .env with user token fields.")

    source_adapter = _build_source_adapter(args = args, http_client = http_client)
    markdown_processor = MarkdownProcessor()
    llm_client = None
    if args.llm_fallback == "toc_ambiguity":
        llm_client = OpenAICompatibleLlmClient(
            base_url = config.llm_base_url,
            api_key = config.llm_api_key,
            model = config.llm_model,
            http_client = http_client
        )
        if not llm_client.is_ready():
            logger.warning(
                "LLM fallback enabled but LLM_BASE_URL/LLM_API_KEY/LLM_MODEL are incomplete; "
                "planner will continue with rules only."
            )

    if args.dry_run:
        orchestrator = ImportOrchestrator(
            source_adapter = source_adapter,
            markdown_processor = markdown_processor,
            config = config,
            llm_client = llm_client
        )
    else:
        _validate_runtime_credentials(args = args, config = config)
        app_auth = FeishuAuthClient(
            app_id = config.feishu_app_id,
            app_secret = config.feishu_app_secret,
            base_url = config.feishu_base_url,
            http_client = http_client
        )
        doc_writer = DocWriterService(
            auth_client = app_auth,
            http_client = http_client,
            base_url = config.feishu_base_url,
            folder_token = config.feishu_folder_token if args.write_mode in {"folder", "both"} else "",
            convert_max_bytes = config.feishu_convert_max_bytes
        )
        media_service = MediaService(
            auth_client = app_auth,
            http_client = http_client,
            base_url = config.feishu_base_url
        )

        wiki_service = None
        if args.write_mode in {"wiki", "both"}:
            if args.auth_code:
                user_token_manager.exchange_code_for_token(
                    code = args.auth_code,
                    redirect_uri = args.oauth_redirect_uri
                )
                logger.info(
                    "OAuth code exchanged successfully; token cache path = %s",
                    config.feishu_user_token_cache_path
                )
                if args.persist_user_token_env:
                    persist_user_tokens_to_env(
                        access_token = user_token_manager.access_token,
                        refresh_token = user_token_manager.refresh_token,
                        token_cache_path = config.feishu_user_token_cache_path
                    )
                    logger.info("Updated .env with user token fields.")

            wiki_service = WikiService(
                auth_client = app_auth,
                http_client = http_client,
                base_url = config.feishu_base_url,
                user_access_token = config.feishu_user_access_token,
                user_token_manager = user_token_manager
            )

        notify_service = None
        if args.notify_level != "none":
            if config.feishu_webhook_url:
                notify_service = WebhookNotifyService(
                    webhook_url = config.feishu_webhook_url,
                    http_client = http_client,
                    max_bytes = config.feishu_message_max_bytes
                )
            elif args.chat_id:
                notify_service = NotifyService(
                    auth_client = app_auth,
                    http_client = http_client,
                    base_url = config.feishu_base_url,
                    max_bytes = config.feishu_message_max_bytes
                )

        orchestrator = ImportOrchestrator(
            source_adapter = source_adapter,
            markdown_processor = markdown_processor,
            config = config,
            doc_writer = doc_writer,
            media_service = media_service,
            wiki_service = wiki_service,
            notify_service = notify_service,
            llm_client = llm_client
        )

    result = orchestrator.run(
        space_name = args.space_name,
        space_id = args.space_id,
        chat_id = args.chat_id,
        dry_run = args.dry_run,
        notify_level = args.notify_level,
        write_mode = args.write_mode,
        folder_subdirs = args.folder_subdirs,
        structure_order = args.structure_order,
        toc_file = args.toc_file,
        folder_nav_doc = args.folder_nav_doc,
        folder_nav_title = args.folder_nav_title,
        llm_fallback = args.llm_fallback,
        llm_max_calls = args.llm_max_calls
    )

    if result.failed > 0:
        return 2
    return 0


def _build_source_adapter(args: argparse.Namespace, http_client: HttpClient) -> SourceAdapter:
    """Create source adapter from CLI arguments.

    Args:
        args: Parsed CLI arguments.
        http_client: Shared HTTP client.
    """

    if args.source == "local":
        return LocalSourceAdapter(root_path = args.path)

    return GitHubSourceAdapter(
        repo = args.repo,
        ref = args.ref,
        subdir = args.subdir,
        http_client = http_client
    )


def _validate_runtime_credentials(args: argparse.Namespace, config: AppConfig) -> None:
    """Validate required credentials for non-dry-run execution.

    Args:
        args: Parsed CLI arguments.
        config: Runtime configuration.
    """

    writer_missing = []
    if not config.feishu_app_id:
        writer_missing.append("FEISHU_APP_ID")
    if not config.feishu_app_secret:
        writer_missing.append("FEISHU_APP_SECRET")
    if writer_missing:
        raise ValueError(f"Missing app bot env: {', '.join(writer_missing)}")

    if args.notify_level != "none" and not config.feishu_webhook_url and not args.chat_id:
        raise ValueError(
            "Notification enabled but no target configured. "
            "Set FEISHU_WEBHOOK_URL or pass --chat-id."
        )

    has_token_cache = os.path.exists(config.feishu_user_token_cache_path)
    has_user_token_source = any(
        [
            config.feishu_user_access_token,
            config.feishu_user_refresh_token,
            args.auth_code,
            args.oauth_local_server,
            has_token_cache
        ]
    )
    if args.write_mode in {"wiki", "both"} and not args.space_id and not has_user_token_source:
        logger.warning(
            "FEISHU_USER_ACCESS_TOKEN/FEISHU_USER_REFRESH_TOKEN are empty. "
            "If target space does not exist, auto-create will fail; "
            "you can pass --space-id to reuse existing space."
        )

    if args.write_mode in {"folder", "both"} and not config.feishu_folder_token:
        raise ValueError(
            "FEISHU_FOLDER_TOKEN is required when --write-mode is folder or both"
        )


if __name__ == "__main__":
    logging.basicConfig(
        level = logging.INFO,
        format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers = [logging.StreamHandler()]
    )

    try:
        exit_code = main()
    except Exception as exc:
        logger.exception("Fatal error: %s", str(exc))
        exit_code = 1

    sys.exit(exit_code)
