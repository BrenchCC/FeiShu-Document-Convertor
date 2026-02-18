import io
import json
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request

from dataclasses import dataclass
from typing import Dict, Optional

from core.exceptions import HttpRequestError


@dataclass
class MultipartFile:
    """One file payload in multipart upload.

    Args:
        filename: Uploaded filename.
        content: Binary payload.
        content_type: MIME type value.
    """

    filename: str
    content: bytes
    content_type: str


@dataclass
class HttpResponse:
    """A lightweight HTTP response wrapper.

    Args:
        status_code: HTTP response status code.
        headers: Response headers map.
        body: Raw response bytes.
    """

    status_code: int
    headers: Dict[str, str]
    body: bytes

    @property
    def text(self) -> str:
        """Decode response bytes to UTF-8 text.

        Args:
            self: Response object.
        """

        return self.body.decode("utf-8", errors = "replace")

    def json(self) -> dict:
        """Parse response body as json.

        Args:
            self: Response object.
        """

        return json.loads(self.text)


class HttpClient:
    """HTTP client with retry and JSON utilities.

    Args:
        timeout: Request timeout in seconds.
        max_retries: Number of retries for temporary failures.
        retry_backoff: Backoff multiplier used between retries.
        user_agent: User agent value sent in each request.
    """

    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_backoff: float = 1.0,
        user_agent: str = "knowledge-generator/1.0"
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.user_agent = user_agent

    def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
        json_body: Optional[dict] = None,
        data: Optional[Dict[str, str]] = None,
        files: Optional[Dict[str, MultipartFile]] = None,
        allow_status: Optional[tuple] = None
    ) -> HttpResponse:
        """Perform an HTTP request.

        Args:
            method: HTTP method.
            url: Target URL.
            headers: Optional request headers.
            params: Optional query parameters.
            json_body: Optional JSON body.
            data: Optional form fields.
            files: Optional multipart files map.
            allow_status: Optional status codes that should not raise error.
        """

        allow_status = allow_status or tuple()
        request_headers = {"User-Agent": self.user_agent}
        if headers:
            request_headers.update(headers)

        final_url = self._build_url(url = url, params = params)
        payload = None

        if files:
            payload, content_type = self._encode_multipart(data = data or {}, files = files)
            request_headers["Content-Type"] = content_type
        elif json_body is not None:
            payload = json.dumps(json_body).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        elif data is not None:
            payload = urllib.parse.urlencode(data).encode("utf-8")
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"

        attempts = 0
        while True:
            attempts += 1
            try:
                req = urllib.request.Request(
                    final_url,
                    data = payload,
                    headers = request_headers,
                    method = method.upper()
                )
                with urllib.request.urlopen(req, timeout = self.timeout) as resp:
                    response = HttpResponse(
                        status_code = resp.getcode(),
                        headers = dict(resp.headers.items()),
                        body = resp.read()
                    )
                if response.status_code >= 400 and response.status_code not in allow_status:
                    raise HttpRequestError(
                        f"HTTP {response.status_code} for {method.upper()} {final_url}: {response.text}"
                    )
                return response
            except urllib.error.HTTPError as exc:
                body = exc.read()
                status_code = int(exc.code)
                if status_code in allow_status:
                    return HttpResponse(
                        status_code = status_code,
                        headers = dict(exc.headers.items()) if exc.headers else {},
                        body = body
                    )
                if self._should_retry(status_code = status_code, attempts = attempts):
                    self._sleep(attempts = attempts)
                    continue
                raise HttpRequestError(
                    f"HTTP {status_code} for {method.upper()} {final_url}: {body.decode('utf-8', errors = 'replace')}"
                ) from exc
            except urllib.error.URLError as exc:
                if self._should_retry(status_code = 503, attempts = attempts):
                    self._sleep(attempts = attempts)
                    continue
                raise HttpRequestError(
                    f"Network error for {method.upper()} {final_url}: {exc.reason}"
                ) from exc

    def _build_url(self, url: str, params: Optional[Dict[str, str]]) -> str:
        """Build URL with query parameters.

        Args:
            url: Base url.
            params: Query map.
        """

        if not params:
            return url
        parsed = urllib.parse.urlparse(url)
        existing = urllib.parse.parse_qs(parsed.query)
        for key, value in params.items():
            existing[key] = [value]
        query = urllib.parse.urlencode(existing, doseq = True)
        return urllib.parse.urlunparse(parsed._replace(query = query))

    def _should_retry(self, status_code: int, attempts: int) -> bool:
        """Decide if request can be retried.

        Args:
            status_code: HTTP status code.
            attempts: Current attempt count.
        """

        if attempts >= self.max_retries:
            return False
        return status_code >= 500 or status_code in {408, 429}

    def _sleep(self, attempts: int) -> None:
        """Apply retry backoff sleep.

        Args:
            attempts: Current attempt count.
        """

        time.sleep(self.retry_backoff * attempts)

    def _encode_multipart(
        self,
        data: Dict[str, str],
        files: Dict[str, MultipartFile]
    ) -> tuple[bytes, str]:
        """Build multipart/form-data payload.

        Args:
            data: Form fields.
            files: File map keyed by field name.
        """

        boundary = f"----kg-boundary-{uuid.uuid4().hex}"
        buffer = io.BytesIO()

        for key, value in data.items():
            buffer.write(f"--{boundary}\r\n".encode("utf-8"))
            buffer.write(
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8")
            )
            buffer.write(str(value).encode("utf-8"))
            buffer.write(b"\r\n")

        for key, file_value in files.items():
            buffer.write(f"--{boundary}\r\n".encode("utf-8"))
            buffer.write(
                (
                    f'Content-Disposition: form-data; name="{key}"; '
                    f'filename="{file_value.filename}"\r\n'
                ).encode("utf-8")
            )
            buffer.write(f"Content-Type: {file_value.content_type}\r\n\r\n".encode("utf-8"))
            buffer.write(file_value.content)
            buffer.write(b"\r\n")

        buffer.write(f"--{boundary}--\r\n".encode("utf-8"))
        return buffer.getvalue(), f"multipart/form-data; boundary={boundary}"
