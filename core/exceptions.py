class AppError(Exception):
    """Base application error."""


class ValidationError(AppError):
    """Raised when CLI arguments or configuration are invalid."""


class HttpRequestError(AppError):
    """Raised when an HTTP request fails."""


class ApiResponseError(AppError):
    """Raised when Feishu/GitHub API returns an invalid payload."""
