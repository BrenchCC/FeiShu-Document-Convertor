import os
import time
import logging
import threading
import webbrowser
import urllib.parse

from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer


logger = logging.getLogger(__name__)


def capture_oauth_code_by_local_server(
    authorize_url: str,
    redirect_uri: str,
    timeout_seconds: int,
    open_browser: bool
) -> str:
    """Capture OAuth code via one-time local callback server.

    Args:
        authorize_url: OAuth authorize URL.
        redirect_uri: Configured OAuth callback URI.
        timeout_seconds: Wait timeout for callback.
        open_browser: Whether to open default browser automatically.
    """

    parsed = urllib.parse.urlparse(redirect_uri)
    if parsed.scheme != "http":
        raise ValueError("--oauth-local-server currently only supports http redirect_uri")

    host = parsed.hostname or ""
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("--oauth-local-server requires localhost/127.0.0.1 redirect_uri")

    port = parsed.port or 80
    callback_path = parsed.path or "/"
    holder = {
        "code": "",
        "error": "",
        "state": ""
    }
    done = threading.Event()

    class OAuthCallbackHandler(BaseHTTPRequestHandler):
        """Handle one OAuth callback request."""

        def do_GET(self) -> None:
            """Process callback and capture query parameters.

            Args:
                self: Request handler.
            """

            request_url = urllib.parse.urlparse(self.path)
            if request_url.path != callback_path:
                self.send_response(404)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"Not Found")
                return

            query = urllib.parse.parse_qs(request_url.query)
            holder["code"] = query.get("code", [""])[0]
            holder["error"] = query.get("error", [""])[0]
            holder["state"] = query.get("state", [""])[0]
            done.set()

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            if holder["code"]:
                message = "Feishu OAuth success. You can close this page."
            else:
                message = "Feishu OAuth callback received, but code is empty."
            self.wfile.write(message.encode("utf-8"))

        def log_message(self, fmt: str, *args) -> None:
            """Suppress builtin HTTP access log output.

            Args:
                self: Request handler.
                fmt: Log format string.
                args: Format arguments.
            """

            return

    try:
        server = HTTPServer((host, port), OAuthCallbackHandler)
    except OSError as exc:
        raise RuntimeError(f"Failed to bind local OAuth callback server at {redirect_uri}: {str(exc)}") from exc
    server.timeout = 0.5

    def _serve_until_done() -> None:
        """Serve callback endpoint until done or timeout.

        Args:
            None
        """

        deadline = time.time() + timeout_seconds
        while time.time() < deadline and not done.is_set():
            server.handle_request()

    worker = threading.Thread(target = _serve_until_done, daemon = True)
    worker.start()

    logger.info("OAuth authorize URL: %s", authorize_url)
    if open_browser:
        webbrowser.open(authorize_url, new = 2)
        logger.info("Opened browser for OAuth authorization.")
    else:
        logger.info("Please open this OAuth URL manually in browser.")
        print(authorize_url)

    worker.join(timeout = timeout_seconds + 1)
    server.server_close()

    if not done.is_set():
        raise TimeoutError("OAuth callback timed out, no code received")

    if holder["error"]:
        raise RuntimeError(f"OAuth callback error: {holder['error']}")
    if not holder["code"]:
        raise RuntimeError("OAuth callback missing code parameter")
    return holder["code"]


def persist_user_tokens_to_env(
    access_token: str,
    refresh_token: str,
    token_cache_path: str,
    dotenv_path: str = ".env"
) -> None:
    """Persist user token fields into local .env file.

    Args:
        access_token: Latest user access token.
        refresh_token: Latest user refresh token.
        token_cache_path: Token cache file path.
        dotenv_path: Dotenv file path.
    """

    if access_token:
        _upsert_dotenv_key(
            dotenv_path = dotenv_path,
            key = "FEISHU_USER_ACCESS_TOKEN",
            value = access_token
        )
    if refresh_token:
        _upsert_dotenv_key(
            dotenv_path = dotenv_path,
            key = "FEISHU_USER_REFRESH_TOKEN",
            value = refresh_token
        )
    if token_cache_path:
        _upsert_dotenv_key(
            dotenv_path = dotenv_path,
            key = "FEISHU_USER_TOKEN_CACHE_PATH",
            value = token_cache_path
        )


def _upsert_dotenv_key(dotenv_path: str, key: str, value: str) -> None:
    """Insert or update one key in dotenv file.

    Args:
        dotenv_path: Dotenv file path.
        key: Env variable key.
        value: Env variable value.
    """

    lines = []
    if os.path.exists(dotenv_path):
        with open(dotenv_path, "r", encoding = "utf-8") as fp:
            lines = fp.readlines()

    target_prefix = f"{key}="
    replaced = False
    new_lines = []
    for raw_line in lines:
        line = raw_line.rstrip("\n")
        if line.startswith(target_prefix):
            new_lines.append(f"{key}={value}\n")
            replaced = True
        else:
            new_lines.append(raw_line)

    if not replaced:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] = new_lines[-1] + "\n"
        new_lines.append(f"{key}={value}\n")

    with open(dotenv_path, "w", encoding = "utf-8") as fp:
        fp.writelines(new_lines)
