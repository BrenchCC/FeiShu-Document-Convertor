import os
import sys
import logging
import argparse


sys.path.append(os.getcwd())

from config.config import AppConfig
from core.bootstrap import build_http_client
from core.bootstrap import build_orchestrator
from core.bootstrap import build_user_token_manager
from core.bootstrap import build_source_adapter_from_cli
from core.bootstrap import validate_runtime_credentials
from utils.logging_setup import configure_runtime_logging
from utils.logging_setup import _cleanup_old_log_files
from utils.logging_setup import _new_run_log_path
from utils.oauth_local_auth import persist_user_tokens_to_env
from utils.oauth_local_auth import capture_oauth_code_by_local_server


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
        help = "Source type: local or github"
    )
    parser.add_argument(
        "--path",
        default = "",
        help = "Local source directory or one .md/.markdown/.docx file path (required when --source local)"
    )
    parser.add_argument(
        "--repo",
        default = "",
        help = "GitHub repo: owner/name or full URL (required when --source github)"
    )
    parser.add_argument("--ref", default = "main", help = "GitHub branch/tag/commit name")
    parser.add_argument(
        "--subdir",
        default = "",
        help = "GitHub subdirectory path (relative to repo root)"
    )

    parser.add_argument(
        "--auth-code",
        default = "",
        help = "One-time Feishu OAuth code to bootstrap user token"
    )
    parser.add_argument(
        "--oauth-redirect-uri",
        default = "",
        help = "OAuth redirect URI used with --auth-code/--print-auth-url/--oauth-local-server"
    )
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
    parser.add_argument(
        "--oauth-timeout",
        type = int,
        default = 300,
        help = "OAuth callback wait timeout in seconds"
    )
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
        help = (
            "When write-mode includes folder, auto-create subfolders by source directories"
        )
    )
    parser.add_argument(
        "--skip-root-readme",
        action = "store_true",
        help = "Skip only root README.md/readme.md when planning document manifest"
    )
    parser.add_argument(
        "--folder-root-subdir",
        action = argparse.BooleanOptionalAction,
        default = True,
        help = "When write-mode includes folder, create one task root subfolder first"
    )
    parser.add_argument(
        "--folder-root-subdir-name",
        default = "",
        help = "Optional task root subfolder name; auto-generated when empty"
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
        help = (
            "Generate folder navigation document after import "
            "(folder-subdirs=true uses LLM folder nav; failure skips nav doc)"
        )
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
    parser.add_argument(
        "--max-workers",
        type = int,
        default = 1,
        help = (
            "Document import workers: 1 means sequential; >1 enables grouped multiprocessing "
            "by top-level subdir; recommended 2-4 for Feishu API stability"
        )
    )
    parser.add_argument(
        "--chunk-workers",
        type = int,
        default = 2,
        help = (
            "Per-document chunk planning worker threads (API writes remain sequential); "
            "recommend <= CPU logical cores"
        )
    )
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
    if args.chunk_workers < 1:
        raise ValueError("--chunk-workers must be >= 1")
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
    if args.folder_root_subdir and args.write_mode not in {"folder", "both"}:
        logger.warning("--folder-root-subdir only applies when --write-mode is folder or both")
    if args.folder_root_subdir_name and not args.folder_root_subdir:
        logger.warning("--folder-root-subdir-name is ignored when --no-folder-root-subdir")

    http_client = build_http_client(config = config)

    user_token_manager = None
    need_user_token_manager = (
        args.write_mode in {"wiki", "both"}
        or args.print_auth_url
        or args.oauth_local_server
    )
    if need_user_token_manager:
        user_token_manager = build_user_token_manager(
            config = config,
            http_client = http_client
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

    source_adapter = build_source_adapter_from_cli(
        source = args.source,
        path = args.path,
        repo = args.repo,
        ref = args.ref,
        subdir = args.subdir,
        http_client = http_client
    )
    enable_llm = args.llm_fallback == "toc_ambiguity"

    if not args.dry_run:
        validate_runtime_credentials(
            config = config,
            write_mode = args.write_mode,
            notify_level = args.notify_level,
            chat_id = args.chat_id,
            has_user_token_override = bool(args.auth_code or args.oauth_local_server)
        )

    orchestrator = build_orchestrator(
        config = config,
        source_adapter = source_adapter,
        http_client = http_client,
        write_mode = args.write_mode,
        dry_run = args.dry_run,
        chunk_workers = args.chunk_workers,
        notify_level = args.notify_level,
        enable_llm = enable_llm,
        chat_id = args.chat_id,
        user_token_manager = user_token_manager
    )

    result = orchestrator.run(
        space_name = args.space_name,
        space_id = args.space_id,
        chat_id = args.chat_id,
        dry_run = args.dry_run,
        notify_level = args.notify_level,
        write_mode = args.write_mode,
        folder_subdirs = args.folder_subdirs,
        folder_root_subdir = args.folder_root_subdir,
        folder_root_subdir_name = args.folder_root_subdir_name,
        structure_order = args.structure_order,
        toc_file = args.toc_file,
        folder_nav_doc = args.folder_nav_doc,
        folder_nav_title = args.folder_nav_title,
        llm_fallback = args.llm_fallback,
        llm_max_calls = args.llm_max_calls,
        skip_root_readme = args.skip_root_readme,
        max_workers = args.max_workers,
        chunk_workers = args.chunk_workers
    )

    if result.failed > 0:
        return 2
    return 0


if __name__ == "__main__":
    configure_runtime_logging()

    try:
        exit_code = main()
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        exit_code = 130
    except Exception as exc:
        logger.exception("Fatal error: %s", str(exc))
        exit_code = 1

    sys.exit(exit_code)
