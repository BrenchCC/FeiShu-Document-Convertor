import os
import sys
import logging
import datetime

logger = logging.getLogger(__name__)

LOG_FILE_ENV_KEY = "KNOWLEDGE_GENERATOR_LOG_PATH"
DEFAULT_LOG_DIR = os.path.join("logs", "cli")
DEFAULT_LOG_PREFIX = "knowledge_generator"
DEFAULT_WEB_LOG_DIR = os.path.join("logs", "web")
DEFAULT_WEB_LOG_PREFIX = "feishu_web"
DEFAULT_MAX_LOG_FILES = 10
DEFAULT_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def configure_runtime_logging(
    log_dir: str = DEFAULT_LOG_DIR,
    log_prefix: str = DEFAULT_LOG_PREFIX,
    max_files: int = DEFAULT_MAX_LOG_FILES,
    level: int = logging.INFO
) -> str:
    """Configure stream + file logging and cleanup old log files.

    Args:
        log_dir: Log directory path.
        log_prefix: Log file name prefix.
        max_files: Max log files to retain.
        level: Root logger level.
    """

    log_path = _new_run_log_path(log_dir = log_dir, log_prefix = log_prefix)
    formatter = logging.Formatter(DEFAULT_LOG_FORMAT)

    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    stream_handler = logging.StreamHandler(stream = sys.stdout)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(log_path, encoding = "utf-8")
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    root_logger.setLevel(level)
    os.environ[LOG_FILE_ENV_KEY] = log_path
    _cleanup_old_log_files(
        log_dir = log_dir,
        log_prefix = log_prefix,
        max_files = max_files
    )
    logger.info("main log file ready: %s", log_path)
    return log_path


def configure_stream_logging(level: int = logging.INFO) -> None:
    """Configure console-only logging for services.

    Args:
        level: Root logger level.
    """

    formatter = logging.Formatter(DEFAULT_LOG_FORMAT)
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
    stream_handler = logging.StreamHandler(stream = sys.stdout)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)
    root_logger.setLevel(level)


def configure_web_logging(
    log_dir: str = DEFAULT_WEB_LOG_DIR,
    log_prefix: str = DEFAULT_WEB_LOG_PREFIX,
    max_files: int = DEFAULT_MAX_LOG_FILES,
    level: int = logging.INFO
) -> str:
    """Configure stream + file logging for web service.

    Args:
        log_dir: Log directory path.
        log_prefix: Log file name prefix.
        max_files: Max log files to retain.
        level: Root logger level.
    """

    return configure_runtime_logging(
        log_dir = log_dir,
        log_prefix = log_prefix,
        max_files = max_files,
        level = level
    )


def ensure_worker_log_handler(level: int = logging.INFO) -> None:
    """Attach stream/file handlers for worker process when root logger is empty.

    Args:
        level: Root logger level.
    """

    root_logger = logging.getLogger()
    formatter = logging.Formatter(DEFAULT_LOG_FORMAT)

    has_stream_handler = any(
        isinstance(handler, logging.StreamHandler)
        and not isinstance(handler, logging.FileHandler)
        for handler in root_logger.handlers
    )
    if not has_stream_handler:
        stream_handler = logging.StreamHandler(stream = sys.stdout)
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)

    log_file_path = os.environ.get(LOG_FILE_ENV_KEY, "").strip()
    if log_file_path:
        expected_path = os.path.abspath(log_file_path)
        has_file_handler = any(
            isinstance(handler, logging.FileHandler)
            and os.path.abspath(getattr(handler, "baseFilename", "")) == expected_path
            for handler in root_logger.handlers
        )
        if not has_file_handler:
            try:
                file_handler = logging.FileHandler(log_file_path, encoding = "utf-8")
                file_handler.setFormatter(formatter)
                root_logger.addHandler(file_handler)
            except OSError:
                pass

    root_logger.setLevel(level)


def _new_run_log_path(log_dir: str, log_prefix: str) -> str:
    """Build one per-run log file path.

    Args:
        log_dir: Log directory path.
        log_prefix: Log file name prefix.
    """

    os.makedirs(log_dir, exist_ok = True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{log_prefix}_{timestamp}_{os.getpid()}.log"
    return os.path.join(log_dir, filename)


def _cleanup_old_log_files(log_dir: str, log_prefix: str, max_files: int) -> None:
    """Keep only the latest log files under one prefix.

    Args:
        log_dir: Log directory path.
        log_prefix: Log file name prefix.
        max_files: Max log files to retain.
    """

    if max_files < 1:
        return

    try:
        filenames = os.listdir(log_dir)
    except FileNotFoundError:
        return

    candidates = []
    for filename in filenames:
        if not filename.startswith(f"{log_prefix}_") or not filename.endswith(".log"):
            continue
        full_path = os.path.join(log_dir, filename)
        if not os.path.isfile(full_path):
            continue
        candidates.append(full_path)

    candidates.sort(
        key = lambda path: os.path.getmtime(path),
        reverse = True
    )
    for stale_path in candidates[max_files:]:
        try:
            os.remove(stale_path)
        except OSError:
            continue
