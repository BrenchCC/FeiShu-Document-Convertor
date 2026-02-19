import os

from dataclasses import dataclass


@dataclass
class AppConfig:
    """Application runtime configuration.

    Args:
        feishu_base_url: Feishu open platform base url.
        feishu_webhook_url: Group bot webhook URL for progress notification.
        feishu_app_id: App id for Feishu custom app bot.
        feishu_app_secret: App secret for Feishu custom app bot.
        feishu_user_access_token: User access token for wiki space creation.
        feishu_user_refresh_token: User refresh token for auto refresh.
        feishu_user_token_cache_path: Cache file path for persisted user tokens.
        feishu_folder_token: Optional folder token for future folder-based routing.
        request_timeout: HTTP timeout in seconds.
        max_retries: Maximum retry count for HTTP requests.
        retry_backoff: Retry backoff multiplier in seconds.
        image_url_template: Template used to build image url from media token.
        feishu_message_max_bytes: Max bytes for one outgoing notify message.
        feishu_convert_max_bytes: Max bytes for one markdown convert call.
        notify_level: Notification verbosity.
        llm_base_url: OpenAI-compatible LLM base URL.
        llm_api_key: OpenAI-compatible LLM API key.
        llm_model: LLM model name for TOC ambiguity fallback.
    """

    feishu_base_url: str
    feishu_webhook_url: str
    feishu_app_id: str
    feishu_app_secret: str
    feishu_user_access_token: str
    feishu_user_refresh_token: str
    feishu_user_token_cache_path: str
    feishu_folder_token: str
    request_timeout: float
    max_retries: int
    retry_backoff: float
    image_url_template: str
    feishu_message_max_bytes: int
    feishu_convert_max_bytes: int
    notify_level: str
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Build configuration from environment variables.

        Args:
            cls: Class reference used by dataclass factory.
        """

        _load_dotenv_if_exists()

        return cls(
            feishu_base_url = os.getenv("FEISHU_BASE_URL", "https://open.feishu.cn").rstrip("/"),
            feishu_webhook_url = os.getenv("FEISHU_WEBHOOK_URL", ""),
            feishu_app_id = os.getenv("FEISHU_APP_ID", os.getenv("FEISHU_WRITER_APP_ID", "")),
            feishu_app_secret = os.getenv(
                "FEISHU_APP_SECRET",
                os.getenv("FEISHU_WRITER_APP_SECRET", "")
            ),
            feishu_user_access_token = os.getenv("FEISHU_USER_ACCESS_TOKEN", ""),
            feishu_user_refresh_token = os.getenv("FEISHU_USER_REFRESH_TOKEN", ""),
            feishu_user_token_cache_path = os.getenv(
                "FEISHU_USER_TOKEN_CACHE_PATH",
                "cache/user_token.json"
            ),
            feishu_folder_token = os.getenv("FEISHU_FOLDER_TOKEN", ""),
            request_timeout = float(os.getenv("REQUEST_TIMEOUT", "30")),
            max_retries = int(os.getenv("MAX_RETRIES", "3")),
            retry_backoff = float(os.getenv("RETRY_BACKOFF", "1.0")),
            image_url_template = os.getenv(
                "FEISHU_IMAGE_URL_TEMPLATE",
                "https://open.feishu.cn/open-apis/drive/v1/medias/{token}/download"
            ),
            feishu_message_max_bytes = int(os.getenv("FEISHU_MESSAGE_MAX_BYTES", "18000")),
            feishu_convert_max_bytes = int(os.getenv("FEISHU_CONVERT_MAX_BYTES", "45000")),
            notify_level = os.getenv("NOTIFY_LEVEL", "normal"),
            llm_base_url = os.getenv("LLM_BASE_URL", ""),
            llm_api_key = os.getenv("LLM_API_KEY", ""),
            llm_model = os.getenv("LLM_MODEL", "")
        )


def _load_dotenv_if_exists(dotenv_path: str = ".env") -> None:
    """Load .env key-values into process env if file exists.

    Args:
        dotenv_path: .env file path.
    """

    # 尝试从项目根目录加载 .env 文件
    # 项目根目录是 config 目录的父目录
    import pathlib
    project_root = pathlib.Path(__file__).parent.parent
    env_path = project_root / dotenv_path

    if not env_path.exists():
        return

    with open(env_path, "r", encoding = "utf-8") as fp:
        for raw_line in fp:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
