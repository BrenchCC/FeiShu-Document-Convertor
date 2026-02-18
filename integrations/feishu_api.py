import os
import re
import time
import json
import hashlib
import logging
import mimetypes
import urllib.parse

from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional
from typing import Any
from typing import Callable

from core.exceptions import ApiResponseError
from core.exceptions import HttpRequestError
from utils.http_client import HttpClient
from utils.http_client import MultipartFile
from utils.markdown_block_parser import split_markdown_to_semantic_blocks
from utils.text_chunker import chunk_text_by_bytes
from utils.text_chunker import split_markdown_by_lines
from data.models import AssetRef
from data.models import WikiNodeRef


logger = logging.getLogger(__name__)


class FeishuAuthClient:
    """Handle tenant access token lifecycle for one Feishu app.

    Args:
        app_id: Feishu app id.
        app_secret: Feishu app secret.
        base_url: Feishu base domain.
        http_client: Shared HTTP client.
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        base_url: str,
        http_client: HttpClient
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client

        self._token = ""
        self._expires_at = 0.0

    def get_tenant_access_token(self) -> str:
        """Get a valid tenant access token.

        Args:
            self: Auth client instance.
        """

        now = time.time()
        if self._token and now < self._expires_at - 60:
            return self._token

        endpoint = f"{self.base_url}/open-apis/auth/v3/tenant_access_token/internal"
        response = self.http_client.request(
            method = "POST",
            url = endpoint,
            json_body = {
                "app_id": self.app_id,
                "app_secret": self.app_secret
            }
        )
        payload = response.json()

        if payload.get("code") != 0:
            raise ApiResponseError(
                f"Failed to get tenant token: {payload.get('msg', 'unknown error')}"
            )

        token = payload.get("tenant_access_token", "")
        expire = int(payload.get("expire", 7200))
        if not token:
            raise ApiResponseError("Feishu auth response missing tenant_access_token")

        self._token = token
        self._expires_at = now + expire
        return token


class FeishuUserTokenManager:
    """Manage user access token and refresh token lifecycle.

    Args:
        app_id: Feishu app id.
        app_secret: Feishu app secret.
        base_url: Feishu base domain.
        http_client: Shared HTTP client.
        access_token: Optional bootstrap access token.
        refresh_token: Optional bootstrap refresh token.
        cache_path: Local cache path for refreshed tokens.
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        base_url: str,
        http_client: HttpClient,
        access_token: str = "",
        refresh_token: str = "",
        cache_path: str = "cache/user_token.json"
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client

        self.access_token = access_token.strip()
        self.refresh_token = refresh_token.strip()
        self.cache_path = cache_path.strip()

        self._loaded_cache = False
        self._expires_at = 0.0

    def get_access_token(self, refresh_if_missing: bool = True) -> str:
        """Get current user access token.

        Args:
            refresh_if_missing: Whether to refresh when access token is missing.
        """

        self._load_cache_if_needed()
        if self.access_token:
            if self._is_access_token_valid():
                return self.access_token
            if self.refresh_token:
                return self.refresh_access_token()
            return self.access_token
        if refresh_if_missing and self.refresh_token:
            return self.refresh_access_token()
        return ""

    def refresh_access_token(self) -> str:
        """Refresh user access token by refresh token.

        Args:
            self: Token manager instance.
        """

        self._load_cache_if_needed()
        if not self.refresh_token:
            raise ApiResponseError(
                "Missing FEISHU_USER_REFRESH_TOKEN and no cached refresh token found."
            )

        body = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.app_id,
            "client_secret": self.app_secret
        }
        payload = self._request_oauth_token(body = body)
        return self._save_tokens_from_payload(payload = payload)

    def exchange_code_for_token(self, code: str, redirect_uri: str = "") -> str:
        """Exchange one-time OAuth code for user tokens.

        Args:
            code: Authorization code from redirect callback.
            redirect_uri: OAuth redirect URI used during authorization.
        """

        request_body = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.app_id,
            "client_secret": self.app_secret
        }
        if redirect_uri:
            request_body["redirect_uri"] = redirect_uri

        payload = self._request_oauth_token(body = request_body)
        return self._save_tokens_from_payload(payload = payload)

    def has_any_token(self) -> bool:
        """Check whether access token or refresh token is available.

        Args:
            self: Token manager instance.
        """

        self._load_cache_if_needed()
        return bool(self.access_token or self.refresh_token)

    def build_authorize_url(
        self,
        redirect_uri: str,
        scope: str,
        state: str = "kg_state"
    ) -> str:
        """Build browser authorization URL for OAuth code flow.

        Args:
            redirect_uri: OAuth callback URI.
            scope: Space-delimited scopes.
            state: Anti-CSRF state value.
        """

        query = urllib.parse.urlencode(
            {
                "client_id": self.app_id,
                "response_type": "code",
                "redirect_uri": redirect_uri,
                "scope": scope,
                "state": state
            },
            quote_via = urllib.parse.quote
        )
        return f"https://accounts.feishu.cn/open-apis/authen/v1/authorize?{query}"

    def _request_oauth_token(self, body: dict[str, str]) -> dict[str, Any]:
        """Call OAuth token endpoint and parse JSON payload.

        Args:
            body: OAuth token request body.
        """

        endpoint = f"{self.base_url}/open-apis/authen/v2/oauth/token"
        try:
            response = self.http_client.request(
                method = "POST",
                url = endpoint,
                json_body = body
            )
        except HttpRequestError as exc:
            raise ApiResponseError(f"OAuth token request failed: {str(exc)}") from exc

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise ApiResponseError(
                f"Invalid OAuth JSON response: {response.text[:200]}"
            ) from exc

        return payload

    def _save_tokens_from_payload(self, payload: dict[str, Any]) -> str:
        """Extract token fields, update cache, and return access token.

        Args:
            payload: OAuth token response payload.
        """

        token = str(payload.get("access_token", "")).strip()
        refresh = str(payload.get("refresh_token", "")).strip()
        expires_in_raw = payload.get("expires_in", payload.get("expires", 0))

        if not token:
            error_message = (
                payload.get("error_description")
                or payload.get("msg")
                or payload.get("error")
                or f"unexpected payload: {str(payload)[:200]}"
            )
            raise ApiResponseError(f"OAuth token exchange failed: {error_message}")

        self.access_token = token
        if refresh:
            self.refresh_token = refresh

        try:
            expires_in = int(expires_in_raw)
        except Exception:
            expires_in = 0
        self._expires_at = time.time() + max(expires_in, 0)

        self._save_cache()
        return token

    def _load_cache_if_needed(self) -> None:
        """Load token cache file once if available.

        Args:
            self: Token manager instance.
        """

        if self._loaded_cache:
            return
        self._loaded_cache = True

        if not self.cache_path:
            return

        cache_file = Path(self.cache_path)
        if not cache_file.exists():
            return

        try:
            payload = json.loads(cache_file.read_text(encoding = "utf-8"))
        except Exception:
            logger.warning("Failed to parse token cache file: %s", str(cache_file))
            return

        cached_access = str(payload.get("access_token", "")).strip()
        cached_refresh = str(payload.get("refresh_token", "")).strip()
        cached_expires_at_raw = payload.get("expires_at", 0.0)
        try:
            cached_expires_at = float(cached_expires_at_raw)
        except Exception:
            cached_expires_at = 0.0

        if cached_access:
            self.access_token = cached_access
        if cached_refresh:
            self.refresh_token = cached_refresh
        if cached_expires_at > 0:
            self._expires_at = cached_expires_at

    def _save_cache(self) -> None:
        """Persist latest tokens to local cache file.

        Args:
            self: Token manager instance.
        """

        if not self.cache_path:
            return

        cache_file = Path(self.cache_path)
        try:
            cache_file.parent.mkdir(parents = True, exist_ok = True)
            cache_file.write_text(
                json.dumps(
                    {
                        "access_token": self.access_token,
                        "refresh_token": self.refresh_token,
                        "expires_at": self._expires_at,
                        "updated_at": int(time.time())
                    },
                    ensure_ascii = False
                ),
                encoding = "utf-8"
            )
        except Exception:
            logger.warning("Failed to write token cache file: %s", str(cache_file))

    def _is_access_token_valid(self) -> bool:
        """Check whether cached access token is still valid.

        Args:
            self: Token manager instance.
        """

        if not self.access_token:
            return False
        if self._expires_at <= 0:
            # Expire time unknown (manual env token), let API judge it.
            return True
        return time.time() < self._expires_at - 60


class FeishuServiceBase:
    """Shared request helper for Feishu open APIs.

    Args:
        auth_client: Auth client used to generate access token.
        http_client: Shared HTTP client.
        base_url: Feishu base domain.
    """

    def __init__(
        self,
        auth_client: FeishuAuthClient,
        http_client: HttpClient,
        base_url: str
    ) -> None:
        self.auth_client = auth_client
        self.http_client = http_client
        self.base_url = base_url.rstrip("/")

    def _request_json(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
        data: Optional[dict] = None,
        files: Optional[Dict[str, MultipartFile]] = None
    ) -> dict:
        """Send signed request and parse Feishu JSON payload.

        Args:
            method: HTTP method.
            path: Open API path.
            params: Query parameters.
            json_body: JSON request body.
            data: Form fields.
            files: Multipart files.
        """

        token = self.auth_client.get_tenant_access_token()
        headers = {
            "Authorization": f"Bearer {token}"
        }
        endpoint = f"{self.base_url}{path}"
        response = self.http_client.request(
            method = method,
            url = endpoint,
            headers = headers,
            params = params,
            json_body = json_body,
            data = data,
            files = files
        )

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise ApiResponseError(
                f"Invalid JSON from {path}: {response.text[:200]}"
            ) from exc

        code = payload.get("code")
        if code != 0:
            raise ApiResponseError(
                f"Feishu API failed for {path}: code = {code}, msg = {payload.get('msg', 'unknown')}"
            )

        return payload


class NotifyService(FeishuServiceBase):
    """Send status messages to group chat by notification bot."""

    def __init__(
        self,
        auth_client: FeishuAuthClient,
        http_client: HttpClient,
        base_url: str,
        max_bytes: int = 18000
    ) -> None:
        super().__init__(
            auth_client = auth_client,
            http_client = http_client,
            base_url = base_url
        )
        self.max_bytes = max_bytes

    def send_status(self, chat_id: str, message: str) -> None:
        """Send a text status message.

        Args:
            chat_id: Target chat id.
            message: Message text.
        """

        if not chat_id:
            return

        chunks = chunk_text_by_bytes(text = message, max_bytes = self.max_bytes)
        for chunk in chunks:
            content = json.dumps({"text": chunk}, ensure_ascii = False)
            self._request_json(
                method = "POST",
                path = "/open-apis/im/v1/messages",
                params = {"receive_id_type": "chat_id"},
                json_body = {
                    "receive_id": chat_id,
                    "msg_type": "text",
                    "content": content
                }
            )


class WebhookNotifyService:
    """Send status messages by incoming webhook URL."""

    def __init__(self, webhook_url: str, http_client: HttpClient, max_bytes: int = 18000) -> None:
        self.webhook_url = webhook_url
        self.http_client = http_client
        self.max_bytes = max_bytes

    def send_status(self, chat_id: str, message: str) -> None:
        """Send webhook text message.

        Args:
            chat_id: Unused in webhook mode, kept for interface compatibility.
            message: Message text.
        """

        if not self.webhook_url:
            return

        chunks = chunk_text_by_bytes(text = message, max_bytes = self.max_bytes)
        for chunk in chunks:
            self.http_client.request(
                method = "POST",
                url = self.webhook_url,
                json_body = {
                    "msg_type": "text",
                    "content": {
                        "text": chunk
                    }
                }
            )


class DocWriterService(FeishuServiceBase):
    """Manage document creation and markdown conversion."""

    FOLDER_INVALID_CHARS_PATTERN = re.compile(r"[\\/:*?\"<>|]+")
    FOLDER_CONTROL_CHARS_PATTERN = re.compile(r"[\x00-\x1f\x7f]+")
    FOLDER_NAME_MAX_BYTES = 256
    FOLDER_CREATE_RETRY_CODE = "1061045"
    FOLDER_CREATE_MAX_ATTEMPTS = 4
    FOLDER_CREATE_BACKOFF_SECONDS = 0.05
    CREATE_CHILDREN_BATCH_SIZE = 20
    NATIVE_TEXT_BLOCK_MAX_BYTES = 3000

    BLOCK_TYPE_TEXT = 2
    BLOCK_TYPE_HEADING_BASE = 2
    BLOCK_TYPE_BULLET = 12
    BLOCK_TYPE_ORDERED = 13
    BLOCK_TYPE_CODE = 14
    BLOCK_TYPE_QUOTE = 15

    INLINE_MARKDOWN_PATTERN = re.compile(
        (
            r"\[(?P<link_text>[^\]]+)\]\((?P<link_url>[^)]+)\)"
            r"|\*\*(?P<bold>[^*]+)\*\*"
            r"|__(?P<bold_underline>[^_]+)__"
            r"|`(?P<inline_code>[^`]+)`"
            r"|~~(?P<strike>[^~]+)~~"
            r"|\*(?P<italic>[^*\n]+)\*"
            r"|_(?P<italic_underscore>[^_\n]+)_"
        )
    )

    HEADING_LINE_PATTERN = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$")
    BULLET_LINE_PATTERN = re.compile(r"^\s{0,3}[-*+]\s+(.+?)\s*$")
    ORDERED_LINE_PATTERN = re.compile(r"^\s{0,3}\d+[.)]\s+(.+?)\s*$")
    QUOTE_LINE_PATTERN = re.compile(r"^\s{0,3}>\s?(.+?)\s*$")
    TABLE_ALIGN_PATTERN = re.compile(
        r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$"
    )

    def __init__(
        self,
        auth_client: FeishuAuthClient,
        http_client: HttpClient,
        base_url: str,
        folder_token: str = "",
        convert_max_bytes: int = 45000
    ) -> None:
        super().__init__(
            auth_client = auth_client,
            http_client = http_client,
            base_url = base_url
        )
        self.folder_token = folder_token
        self.convert_max_bytes = convert_max_bytes
        self._folder_children_cache: Dict[str, Dict[str, str]] = {}
        self._folder_path_cache: Dict[str, str] = {}

    def create_doc(self, title: str, folder_token: str = "") -> str:
        """Create an empty docx document and return document_id.

        Args:
            title: Document title.
            folder_token: Optional folder token.
        """

        payload = self.create_doc_with_meta(
            title = title,
            folder_token = folder_token
        )
        return payload["document_id"]

    def create_doc_with_meta(self, title: str, folder_token: str = "") -> dict[str, str]:
        """Create an empty docx document and return metadata.

        Args:
            title: Document title.
            folder_token: Optional folder token.
        """

        payload_body = {"title": title}
        effective_folder_token = folder_token or self.folder_token
        if effective_folder_token:
            payload_body["folder_token"] = effective_folder_token

        payload = self._request_json(
            method = "POST",
            path = "/open-apis/docx/v1/documents",
            json_body = payload_body
        )
        data = payload.get("data", {})

        document_id_candidates = [
            data.get("document_id"),
            (data.get("document") or {}).get("document_id"),
            (data.get("document") or {}).get("token")
        ]
        document_id = next((item for item in document_id_candidates if item), "")
        if not document_id:
            raise ApiResponseError("create_doc response missing document_id")

        url_candidates = [
            data.get("url"),
            data.get("document_url"),
            (data.get("document") or {}).get("url"),
            (data.get("document") or {}).get("document_url")
        ]
        doc_url = next((item for item in url_candidates if item), "")
        return {
            "document_id": document_id,
            "url": doc_url
        }

    def ensure_folder_path(self, relative_dir: str, root_folder_token: str = "") -> str:
        """Ensure folder path exists under configured root folder.

        Args:
            relative_dir: Relative directory path from source markdown file.
            root_folder_token: Optional root folder token override.
        """

        effective_root_token = root_folder_token or self.folder_token
        if not effective_root_token:
            raise ApiResponseError(
                "FEISHU_FOLDER_TOKEN is required when using folder hierarchy mode."
            )

        normalized = relative_dir.strip().replace("\\", "/").strip("/")
        if not normalized:
            return effective_root_token

        cache_key = f"{effective_root_token}:{normalized}"
        cached = self._folder_path_cache.get(cache_key, "")
        if cached:
            return cached

        current_parent = effective_root_token
        segments = [segment for segment in normalized.split("/") if segment]
        current_path = ""

        for raw_segment in segments:
            folder_name = self._normalize_folder_name(name = raw_segment)
            if not folder_name:
                continue

            current_path = f"{current_path}/{folder_name}" if current_path else folder_name
            current_cache_key = f"{effective_root_token}:{current_path}"
            cached_token = self._folder_path_cache.get(current_cache_key, "")
            if cached_token:
                current_parent = cached_token
                continue

            child_token = self._find_child_folder_token(
                parent_token = current_parent,
                folder_name = folder_name
            )
            if not child_token:
                child_token = self._create_child_folder(
                    parent_token = current_parent,
                    folder_name = folder_name
                )

            self._folder_path_cache[current_cache_key] = child_token
            current_parent = child_token

        self._folder_path_cache[cache_key] = current_parent
        return current_parent

    def _normalize_folder_name(self, name: str) -> str:
        """Normalize one folder segment name for drive folder API.

        Args:
            name: Raw folder segment.
        """

        normalized = self.FOLDER_CONTROL_CHARS_PATTERN.sub(" ", name or "")
        normalized = self.FOLDER_INVALID_CHARS_PATTERN.sub(" ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        normalized = self._truncate_utf8_bytes(
            text = normalized,
            max_bytes = self.FOLDER_NAME_MAX_BYTES
        )
        return normalized

    def _truncate_utf8_bytes(self, text: str, max_bytes: int) -> str:
        """Truncate one string by UTF-8 bytes while keeping valid chars.

        Args:
            text: Input text.
            max_bytes: Max UTF-8 bytes.
        """

        if max_bytes <= 0:
            return ""

        result = ""
        used = 0
        for char in text:
            char_bytes = len(char.encode("utf-8"))
            if result and used + char_bytes > max_bytes:
                break
            if not result and char_bytes > max_bytes:
                return ""
            result += char
            used += char_bytes
        return result

    def _find_child_folder_token(self, parent_token: str, folder_name: str) -> str:
        """Find one direct child folder token by name.

        Args:
            parent_token: Parent folder token.
            folder_name: Child folder name.
        """

        child_map = self._list_child_folders(parent_token = parent_token)
        return child_map.get(folder_name, "")

    def _list_child_folders(self, parent_token: str) -> Dict[str, str]:
        """List direct child folders under one parent folder.

        Args:
            parent_token: Parent folder token.
        """

        if parent_token in self._folder_children_cache:
            return dict(self._folder_children_cache[parent_token])

        result: Dict[str, str] = {}
        page_token = ""
        while True:
            params = {
                "page_size": "200",
                "folder_token": parent_token
            }
            if page_token:
                params["page_token"] = page_token

            payload = self._request_json(
                method = "GET",
                path = "/open-apis/drive/v1/files",
                params = params
            )

            data = payload.get("data", {})
            for item in data.get("files", []):
                if not isinstance(item, dict):
                    continue

                item_type = str(item.get("type", "")).lower()
                if "folder" not in item_type:
                    continue

                folder_name = str(item.get("name", "")).strip()
                if not folder_name:
                    continue

                token_candidates = [
                    item.get("token"),
                    item.get("file_token"),
                    item.get("folder_token")
                ]
                folder_token = next((token for token in token_candidates if token), "")
                if folder_token:
                    result[folder_name] = folder_token

            if not data.get("has_more"):
                break
            page_token = str(data.get("next_page_token", "") or data.get("page_token", "")).strip()
            if not page_token:
                break

        self._folder_children_cache[parent_token] = dict(result)
        return result

    def _create_child_folder(self, parent_token: str, folder_name: str) -> str:
        """Create one child folder under parent and return its token.

        Args:
            parent_token: Parent folder token.
            folder_name: New folder name.
        """

        payload = {}
        for attempt in range(1, self.FOLDER_CREATE_MAX_ATTEMPTS + 1):
            try:
                payload = self._request_json(
                    method = "POST",
                    path = "/open-apis/drive/v1/files/create_folder",
                    json_body = {
                        "name": folder_name,
                        "folder_token": parent_token
                    }
                )
                break
            except ApiResponseError as exc:
                code = self._extract_api_error_code(message = str(exc))
                is_retryable = code == self.FOLDER_CREATE_RETRY_CODE
                is_last = attempt >= self.FOLDER_CREATE_MAX_ATTEMPTS
                if not is_retryable or is_last:
                    raise
                sleep_seconds = self.FOLDER_CREATE_BACKOFF_SECONDS * attempt
                logger.warning(
                    "create_folder retry: parent = %s, name = %s, code = %s, attempt = %d/%d",
                    parent_token,
                    folder_name,
                    code,
                    attempt,
                    self.FOLDER_CREATE_MAX_ATTEMPTS
                )
                time.sleep(sleep_seconds)

        data = payload.get("data", {})
        token_candidates = [
            data.get("token"),
            data.get("file_token"),
            data.get("folder_token"),
            (data.get("file") or {}).get("token"),
            (data.get("folder") or {}).get("token")
        ]
        folder_token = next((token for token in token_candidates if token), "")
        if not folder_token:
            raise ApiResponseError("create_folder response missing folder token")

        cache = self._folder_children_cache.setdefault(parent_token, {})
        cache[folder_name] = folder_token
        return folder_token

    def _extract_api_error_code(self, message: str) -> str:
        """Extract API error code from wrapped exception message.

        Args:
            message: Exception message text.
        """

        match = re.search(r"code\s*=\s*([0-9]+)", message)
        if not match:
            return ""
        return match.group(1)

    def convert_markdown(
        self,
        document_id: str,
        content: str,
        image_token_map: Optional[Dict[str, str]] = None,
        image_block_handler: Optional[Callable[[str, str], None]] = None
    ) -> None:
        """Convert markdown/html content and write it into doc blocks.

        Args:
            document_id: Feishu document id.
            content: Markdown content.
            image_token_map: Optional mapping from image url/path to uploaded media token.
            image_block_handler: Callback invoked with (image_url, real_block_id).
        """

        chunks = split_markdown_by_lines(
            content = content,
            max_bytes = self.convert_max_bytes
        )

        for chunk in chunks:
            self._convert_and_append_chunk(
                document_id = document_id,
                chunk = chunk,
                image_token_map = image_token_map,
                image_block_handler = image_block_handler,
                depth = 0
            )

    def _convert_and_append_chunk(
        self,
        document_id: str,
        chunk: str,
        image_token_map: Optional[Dict[str, str]],
        image_block_handler: Optional[Callable[[str, str], None]],
        depth: int
    ) -> None:
        """Convert one markdown chunk and append converted blocks to document.

        Args:
            document_id: Feishu document id.
            chunk: Markdown chunk content.
            image_token_map: Optional mapping from image url/path to media token.
            image_block_handler: Callback invoked with (image_url, real_block_id).
            depth: Current split recursion depth.
        """

        payload = self._request_json(
            method = "POST",
            path = "/open-apis/docx/v1/documents/blocks/convert",
            json_body = {
                "content": chunk,
                "content_type": "markdown"
            }
        )
        data = payload.get("data", {})
        first_level_block_ids = data.get("first_level_block_ids", [])
        descendants = data.get("blocks", [])

        if not first_level_block_ids or not descendants:
            return

        try:
            append_payload = self._request_json(
                method = "POST",
                path = f"/open-apis/docx/v1/documents/{document_id}/blocks/{document_id}/descendant",
                json_body = {
                    "children_id": first_level_block_ids,
                    "descendants": descendants,
                    "index": -1
                }
            )

            if image_block_handler:
                self._dispatch_image_handlers(
                    convert_image_mappings = data.get("block_id_to_image_urls", []),
                    block_id_relations = (append_payload.get("data") or {}).get("block_id_relations", []),
                    image_block_handler = image_block_handler
                )
        except Exception as exc:
            if self._should_split_chunk(exc = exc, chunk = chunk, depth = depth):
                logger.warning(
                    "descendant append failed, retry split: depth = %d, bytes = %d, err = %s",
                    depth,
                    len(chunk.encode("utf-8")),
                    str(exc)
                )
                split_chunks = self._split_chunk_for_retry(chunk = chunk)
                if len(split_chunks) == 1 and split_chunks[0] == chunk:
                    logger.warning(
                        "descendant split made no progress: depth = %d, bytes = %d",
                        depth,
                        len(chunk.encode("utf-8"))
                    )
                    raise

                for sub_chunk in split_chunks:
                    self._convert_and_append_chunk(
                        document_id = document_id,
                        chunk = sub_chunk,
                        image_token_map = image_token_map,
                        image_block_handler = image_block_handler,
                        depth = depth + 1
                    )
                return
            raise

    def _should_split_chunk(self, exc: Exception, chunk: str, depth: int) -> bool:
        """Decide whether to split chunk and retry after descendant write failure.

        Args:
            exc: Raised exception.
            chunk: Original markdown chunk.
            depth: Current split recursion depth.
        """

        if depth >= 6:
            return False
        if len(chunk.encode("utf-8")) <= 256:
            return False

        message = str(exc).lower()
        return "1770001" in message or "invalid param" in message

    def _split_chunk_for_retry(self, chunk: str) -> List[str]:
        """Split one markdown chunk into smaller parts for retry.

        Args:
            chunk: Markdown chunk.
        """

        total_bytes = len(chunk.encode("utf-8"))
        next_max_bytes = max(1024, total_bytes // 2)
        pieces = split_markdown_by_lines(
            content = chunk,
            max_bytes = next_max_bytes
        )
        pieces = [piece for piece in pieces if piece]
        if len(pieces) >= 2:
            return pieces

        fallback = chunk_text_by_bytes(
            text = chunk,
            max_bytes = next_max_bytes
        )
        return [piece for piece in fallback if piece]

    def _dispatch_image_handlers(
        self,
        convert_image_mappings: List[dict],
        block_id_relations: List[dict],
        image_block_handler: Callable[[str, str], None]
    ) -> None:
        """Dispatch image url to final block id mapping callback.

        Args:
            convert_image_mappings: convert response block_id_to_image_urls.
            block_id_relations: descendant response block id relations.
            image_block_handler: Callback(image_url, final_block_id).
        """

        if not convert_image_mappings or not block_id_relations:
            return

        temp_to_real = {}
        for item in block_id_relations:
            if not isinstance(item, dict):
                continue
            temporary_block_id = item.get("temporary_block_id", "")
            block_id = item.get("block_id", "")
            if temporary_block_id and block_id:
                temp_to_real[temporary_block_id] = block_id

        for item in convert_image_mappings:
            if not isinstance(item, dict):
                continue
            temporary_block_id = item.get("block_id", "")
            image_url = item.get("image_url", "")
            real_block_id = temp_to_real.get(temporary_block_id, "")
            if image_url and real_block_id:
                try:
                    image_block_handler(image_url, real_block_id)
                except Exception as exc:
                    logger.warning(
                        "replace_image failed for block_id = %s, image_url = %s: %s",
                        real_block_id,
                        image_url,
                        str(exc)
                    )

    def _build_convert_image_map(self, mappings: List[dict]) -> Dict[str, str]:
        """Build map from temporary block id to original image url.

        Args:
            mappings: block_id_to_image_urls array from convert response.
        """

        result: Dict[str, str] = {}
        for item in mappings:
            if not isinstance(item, dict):
                continue
            block_id = item.get("block_id", "")
            image_url = item.get("image_url", "")
            if block_id and image_url:
                result[block_id] = image_url
        return result

    def _inject_image_tokens(
        self,
        descendants: List[dict],
        block_to_image_url: Dict[str, str],
        image_token_map: Dict[str, str]
    ) -> None:
        """Replace converted image block url references with uploaded media tokens.

        Args:
            descendants: Converted block list returned by convert API.
            block_to_image_url: Temporary block id to image url map.
            image_token_map: Image url/path to media token map.
        """

        if not descendants or not block_to_image_url or not image_token_map:
            return

        for block in descendants:
            if not isinstance(block, dict):
                continue

            block_id = block.get("block_id", "")
            if not block_id:
                continue

            image_payload = block.get("image")
            if not isinstance(image_payload, dict):
                continue

            if image_payload.get("token"):
                continue

            image_url = block_to_image_url.get(block_id, "")
            if not image_url:
                continue

            token = self._lookup_image_token(
                image_url = image_url,
                image_token_map = image_token_map
            )
            if token:
                image_payload["token"] = token

    def _lookup_image_token(self, image_url: str, image_token_map: Dict[str, str]) -> str:
        """Find matching uploaded media token for one image url.

        Args:
            image_url: Image url/path from convert response.
            image_token_map: Token map built from parsed assets.
        """

        normalized = image_url.strip()
        if not normalized:
            return ""

        parsed = urllib.parse.urlparse(normalized)
        path_only = parsed.path or normalized

        candidates = [
            normalized,
            urllib.parse.unquote(normalized),
            path_only,
            urllib.parse.unquote(path_only),
            os.path.basename(path_only),
            os.path.basename(urllib.parse.unquote(path_only))
        ]

        for key in candidates:
            if key and key in image_token_map:
                return image_token_map[key]
        return ""

    def write_markdown_with_fallback(
        self,
        document_id: str,
        content: str,
        image_token_map: Optional[Dict[str, str]] = None,
        image_block_handler: Optional[Callable[[str, str], None]] = None
    ) -> None:
        """Write markdown by semantic blocks with per-block fallback.

        Args:
            document_id: Feishu document id.
            content: Markdown content.
            image_token_map: Optional mapping from image url/path to media token.
            image_block_handler: Callback invoked with (image_url, real_block_id).
        """

        try:
            self.write_markdown_by_block_matching(
                document_id = document_id,
                content = content,
                image_token_map = image_token_map,
                image_block_handler = image_block_handler
            )
            return
        except Exception as exc:
            logger.warning(
                "block matching write failed for document_id = %s, fallback whole doc: %s",
                document_id,
                str(exc)
            )
            try:
                self.write_markdown_by_native_blocks(
                    document_id = document_id,
                    content = content
                )
            except Exception as native_exc:
                logger.warning(
                    "native block write failed for document_id = %s, fallback raw markdown: %s",
                    document_id,
                    str(native_exc)
                )
                self.append_fallback_text(document_id = document_id, content = content)

    def write_markdown_by_block_matching(
        self,
        document_id: str,
        content: str,
        image_token_map: Optional[Dict[str, str]] = None,
        image_block_handler: Optional[Callable[[str, str], None]] = None
    ) -> None:
        """Write markdown by semantic block matching and per-block convert.

        Args:
            document_id: Feishu document id.
            content: Markdown content.
            image_token_map: Optional mapping from image url/path to media token.
            image_block_handler: Callback invoked with (image_url, real_block_id).
        """

        segments = split_markdown_to_semantic_blocks(content = content)
        if not segments:
            return

        converted_chunks = 0
        fallback_chunks = 0
        for index, segment in enumerate(segments, start = 1):
            chunks = split_markdown_by_lines(
                content = segment.content,
                max_bytes = self.convert_max_bytes
            )
            for chunk in chunks:
                if not chunk.strip():
                    continue

                # 对表格块直接使用降级策略，避免飞书API参数不合法错误
                if segment.kind == "table":
                    logger.info(
                        "Direct fallback for table block: document_id = %s, segment = %d/%d",
                        document_id,
                        index,
                        len(segments)
                    )
                    self._write_segment_by_native_blocks(
                        document_id = document_id,
                        segment_kind = segment.kind,
                        segment_content = chunk
                    )
                    fallback_chunks += 1
                    continue

                try:
                    self._convert_and_append_chunk(
                        document_id = document_id,
                        chunk = chunk,
                        image_token_map = image_token_map,
                        image_block_handler = image_block_handler,
                        depth = 0
                    )
                    converted_chunks += 1
                except Exception as exc:
                    logger.warning(
                        (
                            "semantic convert failed for document_id = %s, block = %s, "
                            "segment = %d/%d, fallback chunk bytes = %d, err = %s"
                        ),
                        document_id,
                        segment.kind,
                        index,
                        len(segments),
                        len(chunk.encode("utf-8")),
                        str(exc)
                    )
                    self._write_segment_by_native_blocks(
                        document_id = document_id,
                        segment_kind = segment.kind,
                        segment_content = chunk
                    )
                    fallback_chunks += 1

        logger.info(
            (
                "markdown block matching written: document_id = %s, segments = %d, "
                "converted_chunks = %d, fallback_chunks = %d"
            ),
            document_id,
            len(segments),
            converted_chunks,
            fallback_chunks
        )

    def write_markdown_by_native_blocks(self, document_id: str, content: str) -> None:
        """Write markdown using native create-children blocks without convert API.

        Args:
            document_id: Feishu document id.
            content: Markdown content.
        """

        segments = split_markdown_to_semantic_blocks(content = content)
        if not segments:
            return

        for segment in segments:
            self._write_segment_by_native_blocks(
                document_id = document_id,
                segment_kind = segment.kind,
                segment_content = segment.content
            )

    def _write_segment_by_native_blocks(
        self,
        document_id: str,
        segment_kind: str,
        segment_content: str
    ) -> None:
        """Write one semantic segment through native create-children calls.

        Args:
            document_id: Feishu document id.
            segment_kind: Semantic segment kind.
            segment_content: Segment markdown content.
        """

        blocks = self._build_native_blocks_from_segment(
            segment_kind = segment_kind,
            segment_content = segment_content
        )
        if not blocks:
            return
        self._append_native_blocks(
            document_id = document_id,
            blocks = blocks
        )

    def _build_native_blocks_from_segment(
        self,
        segment_kind: str,
        segment_content: str
    ) -> list[dict]:
        """Build native docx blocks from one markdown segment.

        Args:
            segment_kind: Semantic segment kind.
            segment_content: Segment markdown content.
        """

        stripped = segment_content.strip("\n")
        if not stripped:
            return []

        if segment_kind == "heading":
            block = self._build_heading_native_block(line = stripped)
            return [block] if block else []

        if segment_kind == "list_or_quote":
            return self._build_list_or_quote_native_blocks(content = stripped)

        if segment_kind == "code_fence":
            code_content = self._strip_code_fence(content = stripped)
            return self._build_textual_blocks_payload(
                block_type = self.BLOCK_TYPE_CODE,
                field_name = "code",
                text = code_content,
                parse_inline = False
            )

        if segment_kind == "table":
            return self._build_table_fallback_blocks(content = stripped)

        return self._build_textual_blocks_payload(
            block_type = self.BLOCK_TYPE_TEXT,
            field_name = "text",
            text = stripped,
            parse_inline = True
        )

    def _build_heading_native_block(self, line: str) -> Optional[dict]:
        """Build one heading block from one markdown heading line.

        Args:
            line: Markdown heading line.
        """

        match = self.HEADING_LINE_PATTERN.match(line.strip())
        if not match:
            return None

        level_marks = match.group(1)
        raw_text = match.group(2).strip()
        level = min(max(len(level_marks), 1), 6)
        field_name = f"heading{level}"
        block_type = self.BLOCK_TYPE_HEADING_BASE + level
        return self._build_textual_block_payload(
            block_type = block_type,
            field_name = field_name,
            text = raw_text,
            parse_inline = True
        )

    def _build_list_or_quote_native_blocks(self, content: str) -> list[dict]:
        """Build list/quote blocks from one segment.

        Args:
            content: Segment markdown content.
        """

        blocks: list[dict] = []
        for raw_line in content.splitlines():
            line = raw_line.rstrip()
            if not line.strip():
                continue

            quote_match = self.QUOTE_LINE_PATTERN.match(line)
            if quote_match:
                blocks.append(
                    self._build_textual_block_payload(
                        block_type = self.BLOCK_TYPE_QUOTE,
                        field_name = "quote",
                        text = quote_match.group(1).strip(),
                        parse_inline = True
                    )
                )
                continue

            ordered_match = self.ORDERED_LINE_PATTERN.match(line)
            if ordered_match:
                blocks.append(
                    self._build_textual_block_payload(
                        block_type = self.BLOCK_TYPE_ORDERED,
                        field_name = "ordered",
                        text = ordered_match.group(1).strip(),
                        parse_inline = True
                    )
                )
                continue

            bullet_match = self.BULLET_LINE_PATTERN.match(line)
            if bullet_match:
                blocks.append(
                    self._build_textual_block_payload(
                        block_type = self.BLOCK_TYPE_BULLET,
                        field_name = "bullet",
                        text = bullet_match.group(1).strip(),
                        parse_inline = True
                    )
                )
                continue

            blocks.append(
                self._build_textual_block_payload(
                    block_type = self.BLOCK_TYPE_TEXT,
                    field_name = "text",
                    text = line.strip(),
                    parse_inline = True
                )
            )

        return blocks

    def _build_table_fallback_blocks(self, content: str) -> list[dict]:
        """Build fallback text blocks from markdown table rows.

        Args:
            content: Table markdown content.
        """

        rows = [line.rstrip() for line in content.splitlines() if line.strip()]
        data_rows = [
            row for row in rows
            if not self.TABLE_ALIGN_PATTERN.match(row.strip())
        ]
        if not data_rows:
            return []

        blocks: list[dict] = []
        for index, row in enumerate(data_rows):
            cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
            if not any(cells):
                continue

            if index == 0:
                normalized_cells = []
                for cell in cells:
                    if not cell:
                        continue
                    if "**" in cell:
                        normalized_cells.append(cell)
                    else:
                        normalized_cells.append(f"**{cell}**")
                row_text = " | ".join(normalized_cells)
            else:
                row_text = " | ".join(cells)

            blocks.append(
                self._build_textual_block_payload(
                    block_type = self.BLOCK_TYPE_TEXT,
                    field_name = "text",
                    text = row_text,
                    parse_inline = True
                )
            )
        return blocks

    def _strip_code_fence(self, content: str) -> str:
        """Remove fenced markdown wrapper and keep code body.

        Args:
            content: Raw fenced markdown block.
        """

        lines = content.splitlines()
        if len(lines) >= 2 and (
            lines[0].strip().startswith("```")
            or lines[0].strip().startswith("~~~")
        ):
            fence = lines[0].strip()[:3]
            code_lines = lines[1:]
            if code_lines and code_lines[-1].strip().startswith(fence):
                code_lines = code_lines[:-1]
            return "\n".join(code_lines)
        return content

    def _build_textual_blocks_payload(
        self,
        block_type: int,
        field_name: str,
        text: str,
        parse_inline: bool
    ) -> list[dict]:
        """Build one or more text-like blocks with byte-safe chunking.

        Args:
            block_type: Feishu block type.
            field_name: Text payload field name.
            text: Block text content.
            parse_inline: Whether to parse markdown inline style.
        """

        chunks = self._split_text_for_native_block(
            text = text,
            max_bytes = self.NATIVE_TEXT_BLOCK_MAX_BYTES
        )
        return [
            self._build_textual_block_payload(
                block_type = block_type,
                field_name = field_name,
                text = chunk,
                parse_inline = parse_inline
            )
            for chunk in chunks
            if chunk is not None
        ]

    def _split_text_for_native_block(self, text: str, max_bytes: int) -> list[str]:
        """Split one text body into API-safe chunks by UTF-8 bytes.

        Args:
            text: Raw text content.
            max_bytes: Maximum bytes per chunk.
        """

        if max_bytes <= 0:
            return [text]

        if len(text.encode("utf-8")) <= max_bytes:
            return [text]

        if "\n" in text:
            by_lines = split_markdown_by_lines(
                content = text,
                max_bytes = max_bytes
            )
        else:
            by_lines = [text]

        chunks: list[str] = []
        for item in by_lines:
            if len(item.encode("utf-8")) <= max_bytes:
                chunks.append(item)
                continue
            chunks.extend(chunk_text_by_bytes(text = item, max_bytes = max_bytes))

        if not chunks:
            return [text]
        return chunks

    def _build_textual_block_payload(
        self,
        block_type: int,
        field_name: str,
        text: str,
        parse_inline: bool
    ) -> dict:
        """Build one text-like block payload.

        Args:
            block_type: Feishu block type.
            field_name: Text payload field name.
            text: Block text content.
            parse_inline: Whether to parse markdown inline style.
        """

        if parse_inline:
            elements = self._build_text_elements_from_markdown(text = text)
        else:
            elements = [{"text_run": {"content": text}}]

        if not elements:
            elements = [{"text_run": {"content": ""}}]

        return {
            "block_type": block_type,
            field_name: {
                "elements": elements
            }
        }

    def _build_text_elements_from_markdown(self, text: str) -> list[dict]:
        """Build Feishu text elements from lightweight markdown inline tokens.

        Args:
            text: Inline markdown text.
        """

        if not text:
            return [{"text_run": {"content": ""}}]

        elements: list[dict] = []
        cursor = 0
        for match in self.INLINE_MARKDOWN_PATTERN.finditer(text):
            start, end = match.span()
            if start > cursor:
                plain_text = text[cursor:start]
                if plain_text:
                    elements.append({"text_run": {"content": plain_text}})

            if match.group("link_text") is not None:
                elements.append(
                    {
                        "text_run": {
                            "content": match.group("link_text"),
                            "text_element_style": {
                                "link": {
                                    "url": match.group("link_url")
                                }
                            }
                        }
                    }
                )
            elif match.group("bold") is not None:
                elements.append(self._build_styled_text_run(
                    content = match.group("bold"),
                    style = {"bold": True}
                ))
            elif match.group("bold_underline") is not None:
                elements.append(self._build_styled_text_run(
                    content = match.group("bold_underline"),
                    style = {"bold": True}
                ))
            elif match.group("inline_code") is not None:
                elements.append(self._build_styled_text_run(
                    content = match.group("inline_code"),
                    style = {"inline_code": True}
                ))
            elif match.group("strike") is not None:
                elements.append(self._build_styled_text_run(
                    content = match.group("strike"),
                    style = {"strikethrough": True}
                ))
            elif match.group("italic") is not None:
                elements.append(self._build_styled_text_run(
                    content = match.group("italic"),
                    style = {"italic": True}
                ))
            elif match.group("italic_underscore") is not None:
                elements.append(self._build_styled_text_run(
                    content = match.group("italic_underscore"),
                    style = {"italic": True}
                ))

            cursor = end

        if cursor < len(text):
            tail = text[cursor:]
            if tail:
                elements.append({"text_run": {"content": tail}})

        return elements

    def _build_styled_text_run(self, content: str, style: dict) -> dict:
        """Build one text_run element with style.

        Args:
            content: Text content.
            style: Text style payload.
        """

        return {
            "text_run": {
                "content": content,
                "text_element_style": style
            }
        }

    def _append_native_blocks(self, document_id: str, blocks: list[dict]) -> None:
        """Append native blocks to one document in small batches.

        Args:
            document_id: Feishu document id.
            blocks: Block payload list.
        """

        if not blocks:
            return

        for index in range(0, len(blocks), self.CREATE_CHILDREN_BATCH_SIZE):
            batch = blocks[index:index + self.CREATE_CHILDREN_BATCH_SIZE]
            self._request_json(
                method = "POST",
                path = f"/open-apis/docx/v1/documents/{document_id}/blocks/{document_id}/children",
                json_body = {
                    "children": batch,
                    "index": -1
                }
            )

    def replace_image(self, document_id: str, block_id: str, file_token: str) -> None:
        """Replace one image block content by uploaded file token.

        Args:
            document_id: Document id.
            block_id: Target image block id.
            file_token: Token returned by upload_all media endpoint.
        """

        self._request_json(
            method = "PATCH",
            path = f"/open-apis/docx/v1/documents/{document_id}/blocks/{block_id}",
            json_body = {
                "replace_image": {
                    "token": file_token
                }
            }
        )

    def append_fallback_text(self, document_id: str, content: str) -> None:
        """Fallback when markdown convert fails.

        Args:
            document_id: Feishu document id.
            content: Raw markdown content.
        """

        snippet = content[:4000]
        self._request_json(
            method = "POST",
            path = f"/open-apis/docx/v1/documents/{document_id}/blocks/{document_id}/children",
            json_body = {
                "children": [
                    {
                        "block_type": self.BLOCK_TYPE_TEXT,
                        "text": {
                            "elements": [
                                {
                                    "text_run": {
                                        "content": snippet
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        )


class MediaService(FeishuServiceBase):
    """Upload image assets to Feishu and return media token."""

    def fetch_asset_content(self, asset: AssetRef) -> bytes:
        """Fetch image bytes from local file or URL.

        Args:
            asset: Asset reference.
        """

        resolved_url = asset.resolved_url
        if resolved_url.startswith("http://") or resolved_url.startswith("https://"):
            response = self.http_client.request(method = "GET", url = resolved_url)
            return response.body

        if resolved_url.startswith("data:"):
            raise ApiResponseError("Data URL images are not supported in v1")

        with open(resolved_url, "rb") as fp:
            return fp.read()

    def upload_to_node(self, asset: AssetRef, parent_node: str) -> str:
        """Upload image to Feishu drive and return media token.

        Args:
            asset: Asset reference.
            parent_node: Destination node token (document or image block id).
        """

        content = self.fetch_asset_content(asset = asset)
        asset.sha256 = hashlib.sha256(content).hexdigest()

        filename = os.path.basename(asset.resolved_url) or os.path.basename(asset.original_url) or "image.bin"
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        payload = self._request_json(
            method = "POST",
            path = "/open-apis/drive/v1/medias/upload_all",
            data = {
                "file_name": filename,
                "parent_type": "docx_image",
                "parent_node": parent_node,
                "size": str(len(content))
            },
            files = {
                "file": MultipartFile(
                    filename = filename,
                    content = content,
                    content_type = mime_type
                )
            }
        )

        data = payload.get("data", {})
        token_candidates = [
            data.get("file_token"),
            data.get("media_id"),
            data.get("token")
        ]
        token = next((item for item in token_candidates if item), "")
        if not token:
            raise ApiResponseError("media upload response missing token")

        asset.media_token = token
        return token

    def upload_to_doc(self, asset: AssetRef, document_id: str) -> str:
        """Compatibility wrapper for doc-level media upload.

        Args:
            asset: Asset reference.
            document_id: Destination document id.
        """

        return self.upload_to_node(
            asset = asset,
            parent_node = document_id
        )


class WikiService(FeishuServiceBase):
    """Manage wiki space and nodes."""

    def __init__(
        self,
        auth_client: FeishuAuthClient,
        http_client: HttpClient,
        base_url: str,
        user_access_token: str = "",
        user_token_manager: Optional[FeishuUserTokenManager] = None
    ) -> None:
        super().__init__(
            auth_client = auth_client,
            http_client = http_client,
            base_url = base_url
        )
        self.node_cache: Dict[str, WikiNodeRef] = {}
        self.user_access_token = user_access_token.strip()
        self.user_token_manager = user_token_manager

    def get_or_create_space(self, space_name: str) -> str:
        """Get wiki space by name or create one.

        Args:
            space_name: Target space name.
        """

        try:
            spaces = self._list_spaces()
        except Exception as exc:
            if not self._has_user_token():
                raise
            logger.warning(
                "list wiki spaces by tenant token failed, fallback to user token: %s",
                str(exc)
            )
            spaces = self._list_spaces_by_user_token()
        for item in spaces:
            title = item.get("name") or item.get("title")
            if title == space_name:
                space_id = item.get("space_id") or item.get("id")
                if space_id:
                    return space_id

        user_token = self._get_user_access_token()
        if not user_token:
            raise ApiResponseError(
                "Create wiki space requires user_access_token. "
                "Set FEISHU_USER_ACCESS_TOKEN/FEISHU_USER_REFRESH_TOKEN "
                "or pass --space-id to reuse existing space."
            )

        payload = self._request_json_with_access_token(
            method = "POST",
            path = "/open-apis/wiki/v2/spaces",
            access_token = user_token,
            json_body = {"name": space_name}
        )

        data = payload.get("data", {})
        candidates = [
            data.get("space_id"),
            (data.get("space") or {}).get("space_id")
        ]
        for candidate in candidates:
            if candidate:
                return candidate

        raise ApiResponseError("create wiki space response missing space_id")

    def ensure_path_nodes(self, space_id: str, relative_dir: str) -> str:
        """Ensure wiki node path exists and return final parent token.

        Args:
            space_id: Wiki space id.
            relative_dir: Relative directory path.
        """

        normalized = relative_dir.strip("/")
        if not normalized:
            return ""

        current_parent = ""
        segments = [segment for segment in normalized.split("/") if segment]

        for segment in segments:
            cache_key = f"{space_id}:{current_parent}:{segment}"
            cached = self.node_cache.get(cache_key)
            if cached:
                current_parent = cached.node_token
                continue

            children = self._list_nodes(
                space_id = space_id,
                parent_node_token = current_parent
            )
            matched = None
            for child in children:
                title = child.get("title") or child.get("name")
                if title == segment:
                    matched = child
                    break

            if matched:
                node_token = matched.get("node_token") or matched.get("wiki_token")
                if not node_token:
                    raise ApiResponseError("list nodes item missing node_token")
            else:
                node_token = self._create_catalog_node(
                    space_id = space_id,
                    parent_node_token = current_parent,
                    title = segment
                )

            node_ref = WikiNodeRef(
                space_id = space_id,
                node_token = node_token,
                title = segment,
                parent_token = current_parent
            )
            self.node_cache[cache_key] = node_ref
            current_parent = node_token

        return current_parent

    def move_doc_to_wiki(
        self,
        space_id: str,
        document_id: str,
        parent_node_token: str,
        title: str
    ) -> str:
        """Move one docx document into wiki hierarchy.

        Args:
            space_id: Wiki space id.
            document_id: Source docx document id.
            parent_node_token: Parent node token.
            title: Node title in wiki.
        """

        payload = self._request_json(
            method = "POST",
            path = f"/open-apis/wiki/v2/spaces/{space_id}/nodes/move_docs_to_wiki",
            json_body = {
                "parent_wiki_token": parent_node_token,
                "obj_type": "docx",
                "obj_token": document_id,
                "apply": True
            }
        )

        data = payload.get("data", {})
        candidates = [
            data.get("node_token"),
            data.get("wiki_token"),
            (data.get("node") or {}).get("node_token")
        ]
        token = next((item for item in candidates if item), "")
        if not token:
            raise ApiResponseError("move_docs_to_wiki response missing node token")
        return token

    def _request_json_with_access_token(
        self,
        method: str,
        path: str,
        access_token: str,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
        retry_on_invalid_token: bool = True
    ) -> dict:
        """Send request with explicit access token and parse Feishu JSON payload.

        Args:
            method: HTTP method.
            path: Open API path.
            access_token: User or tenant access token.
            params: Query parameters.
            json_body: JSON request body.
            retry_on_invalid_token: Whether to retry once after token refresh.
        """

        endpoint = f"{self.base_url}{path}"
        try:
            response = self.http_client.request(
                method = method,
                url = endpoint,
                headers = {
                    "Authorization": f"Bearer {access_token}"
                },
                params = params,
                json_body = json_body
            )
        except HttpRequestError as exc:
            if retry_on_invalid_token and self._looks_like_invalid_token_error(str(exc)):
                refreshed = self._refresh_user_token()
                if refreshed and refreshed != access_token:
                    logger.warning("Retry Feishu wiki API after refreshing user token: %s", path)
                    return self._request_json_with_access_token(
                        method = method,
                        path = path,
                        access_token = refreshed,
                        params = params,
                        json_body = json_body,
                        retry_on_invalid_token = False
                    )
            raise

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise ApiResponseError(
                f"Invalid JSON from {path}: {response.text[:200]}"
            ) from exc

        code = payload.get("code")
        if code != 0:
            if retry_on_invalid_token and self._is_invalid_token_code(code):
                refreshed = self._refresh_user_token()
                if refreshed and refreshed != access_token:
                    logger.warning("Retry Feishu wiki API after token code = %s: %s", str(code), path)
                    return self._request_json_with_access_token(
                        method = method,
                        path = path,
                        access_token = refreshed,
                        params = params,
                        json_body = json_body,
                        retry_on_invalid_token = False
                    )
            raise ApiResponseError(
                f"Feishu API failed for {path}: code = {code}, "
                f"msg = {payload.get('msg', 'unknown')}"
            )

        return payload

    def _has_user_token(self) -> bool:
        """Check whether any user token source is configured.

        Args:
            self: Wiki service instance.
        """

        if self.user_token_manager and self.user_token_manager.has_any_token():
            return True
        return bool(self.user_access_token)

    def _get_user_access_token(self, force_refresh: bool = False) -> str:
        """Get user access token from manager or static config.

        Args:
            force_refresh: Whether to force refresh using refresh token.
        """

        if self.user_token_manager:
            if force_refresh:
                return self.user_token_manager.refresh_access_token()
            return self.user_token_manager.get_access_token(refresh_if_missing = True)
        return self.user_access_token

    def _refresh_user_token(self) -> str:
        """Try refreshing user access token by token manager.

        Args:
            self: Wiki service instance.
        """

        if not self.user_token_manager:
            return ""
        try:
            return self.user_token_manager.refresh_access_token()
        except Exception:
            logger.exception("Failed to refresh user access token automatically")
            return ""

    def _is_invalid_token_code(self, code: Any) -> bool:
        """Check whether Feishu response code indicates invalid token.

        Args:
            code: API payload code value.
        """

        known_invalid_codes = {
            "99991663",
            "99991661",
            "99991662",
            "99991664",
            "20026"
        }
        return str(code) in known_invalid_codes

    def _looks_like_invalid_token_error(self, message: str) -> bool:
        """Check HTTP-layer error message for invalid token signs.

        Args:
            message: Exception message text.
        """

        if not message:
            return False

        lowered = message.lower()
        if "invalid access token" in lowered:
            return True

        match = re.search(r'"code"\s*:\s*(\d+)', message)
        if match and self._is_invalid_token_code(match.group(1)):
            return True

        return False

    def _list_spaces(self) -> List[dict]:
        """List all wiki spaces with pagination.

        Args:
            self: Wiki service instance.
        """

        items: List[dict] = []
        page_token = ""

        while True:
            params = {"page_size": "50"}
            if page_token:
                params["page_token"] = page_token

            payload = self._request_json(
                method = "GET",
                path = "/open-apis/wiki/v2/spaces",
                params = params
            )
            data = payload.get("data", {})
            items.extend(data.get("items", []))

            if not data.get("has_more"):
                break
            page_token = data.get("page_token", "")
            if not page_token:
                break

        return items

    def _list_spaces_by_user_token(self) -> List[dict]:
        """List all wiki spaces with user access token.

        Args:
            self: Wiki service instance.
        """

        items: List[dict] = []
        page_token = ""
        access_token = self._get_user_access_token()
        if not access_token:
            return items

        while True:
            params = {"page_size": "50"}
            if page_token:
                params["page_token"] = page_token

            payload = self._request_json_with_access_token(
                method = "GET",
                path = "/open-apis/wiki/v2/spaces",
                access_token = access_token,
                params = params
            )
            data = payload.get("data", {})
            items.extend(data.get("items", []))

            if not data.get("has_more"):
                break
            page_token = data.get("page_token", "")
            if not page_token:
                break

        return items

    def _list_nodes(self, space_id: str, parent_node_token: str) -> List[dict]:
        """List child nodes under one parent.

        Args:
            space_id: Wiki space id.
            parent_node_token: Parent node token.
        """

        params = {
            "page_size": "200"
        }
        if parent_node_token:
            params["parent_node_token"] = parent_node_token

        payload = self._request_json(
            method = "GET",
            path = f"/open-apis/wiki/v2/spaces/{space_id}/nodes",
            params = params
        )
        data = payload.get("data", {})
        return data.get("items", [])

    def _create_catalog_node(self, space_id: str, parent_node_token: str, title: str) -> str:
        """Create a catalog-like wiki node.

        Args:
            space_id: Wiki space id.
            parent_node_token: Parent token.
            title: Node title.
        """

        payload = self._request_json(
            method = "POST",
            path = f"/open-apis/wiki/v2/spaces/{space_id}/nodes",
            json_body = {
                "title": title,
                "parent_node_token": parent_node_token,
                "obj_type": "wiki_catalog"
            }
        )

        data = payload.get("data", {})
        candidates = [
            data.get("node_token"),
            data.get("wiki_token"),
            (data.get("node") or {}).get("node_token")
        ]
        token = next((item for item in candidates if item), "")
        if not token:
            raise ApiResponseError("create wiki node response missing node token")
        return token
