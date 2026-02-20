import os
import re
import abc
import shutil
import tempfile
import subprocess
import urllib.parse

from pathlib import Path
from typing import List

from data.models import SourceDocument
from utils.http_client import HttpClient
from utils.docx_converter import convert_docx_to_markdown


LOCAL_MD_IMAGE_PATTERN = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<url>[^)]+)\)")
LOCAL_HTML_IMAGE_PATTERN = re.compile(
    r"<img\s+[^>]*src=[\"'](?P<url>[^\"']+)[\"'][^>]*>",
    flags = re.IGNORECASE
)


class SourceAdapter(abc.ABC):
    """Source adapter abstraction for markdown discovery and reading."""

    @abc.abstractmethod
    def list_markdown(self) -> List[str]:
        """List markdown paths relative to source root.

        Args:
            self: Adapter instance.
        """

    @abc.abstractmethod
    def read_markdown(self, relative_path: str) -> SourceDocument:
        """Read one markdown file.

        Args:
            self: Adapter instance.
            relative_path: Source-relative markdown path.
        """


class LocalSourceAdapter(SourceAdapter):
    """Source adapter for local markdown/docx directory or one file.

    Args:
        root_path: Local root directory path.
    """

    def __init__(self, root_path: str) -> None:
        self.root_path = os.path.abspath(root_path)
        self._root_path_obj = Path(self.root_path)
        self._file_mode = self._root_path_obj.is_file()
        self._source_root = self._root_path_obj.parent if self._file_mode else self._root_path_obj
        self._single_relative_path = self._root_path_obj.name if self._file_mode else ""
        self._docx_temp_dir = tempfile.TemporaryDirectory(prefix = "kg_docx_")
        self._docx_conversion_cache: dict[str, tuple[str, str]] = {}

    def list_markdown(self) -> List[str]:
        """Collect markdown files from local root.

        Args:
            self: Adapter instance.
        """

        if self._file_mode:
            if _is_local_supported_path(path = self._root_path_obj):
                return [self._single_relative_path]
            return []

        result = []
        for path in self._root_path_obj.rglob("*"):
            if not _is_local_supported_path(path = path):
                continue
            relative = str(path.relative_to(self._source_root)).replace("\\", "/")
            result.append(relative)
        return sorted(result)

    def read_markdown(self, relative_path: str) -> SourceDocument:
        """Read local markdown and return structured document.

        Args:
            self: Adapter instance.
            relative_path: Source-relative markdown path.
        """

        normalized_relative_path = str(Path(relative_path)).replace("\\", "/")
        if self._file_mode and normalized_relative_path != self._single_relative_path:
            raise FileNotFoundError(f"Local markdown path not found: {relative_path}")

        full_path = self._source_root / normalized_relative_path
        if full_path.suffix.lower() == ".docx":
            markdown, base_ref = self._read_docx_as_markdown(
                normalized_relative_path = normalized_relative_path,
                full_path = full_path
            )
        else:
            markdown = full_path.read_text(encoding = "utf-8", errors = "ignore")
            markdown = self._normalize_local_image_paths(
                markdown = markdown,
                base_dirs = [full_path.parent, self._source_root]
            )
            base_ref = str(full_path.parent)

        title = _extract_title(markdown = markdown, relative_path = normalized_relative_path)
        relative_dir = str(Path(normalized_relative_path).parent).replace("\\", "/")
        if relative_dir == ".":
            relative_dir = ""
        return SourceDocument(
            path = normalized_relative_path,
            title = title,
            markdown = markdown,
            assets = [],
            relative_dir = relative_dir,
            base_ref = base_ref,
            source_type = "local"
        )

    def close(self) -> None:
        """Release temporary DOCX conversion workspace.

        Args:
            self: Adapter instance.
        """

        if self._docx_temp_dir is not None:
            self._docx_temp_dir.cleanup()
            self._docx_temp_dir = None

    def __del__(self) -> None:
        """Ensure temporary workspace cleanup on object deletion.

        Args:
            self: Adapter instance.
        """

        try:
            self.close()
        except Exception:
            pass

    def _read_docx_as_markdown(
        self,
        normalized_relative_path: str,
        full_path: Path
    ) -> tuple[str, str]:
        """Convert local DOCX to markdown and return markdown/base_ref.

        Args:
            normalized_relative_path: Source-relative local path.
            full_path: Absolute DOCX path.
        """

        cached = self._docx_conversion_cache.get(normalized_relative_path)
        if cached:
            return cached

        relative_without_suffix = Path(normalized_relative_path).with_suffix("")
        output_dir = Path(self._docx_temp_dir.name) / relative_without_suffix
        try:
            conversion = convert_docx_to_markdown(
                docx_path = str(full_path),
                output_dir = str(output_dir),
                track_changes = "accept"
            )
        except Exception as exc:
            raise RuntimeError(
                f"DOCX convert failed: path = {normalized_relative_path}, error = {str(exc)}"
            ) from exc

        result = (
            self._normalize_local_image_paths(
                markdown = conversion.markdown,
                base_dirs = [
                    Path(conversion.markdown_path).parent,
                    full_path.parent,
                    self._source_root
                ]
            ),
            str(Path(conversion.markdown_path).parent)
        )
        self._docx_conversion_cache[normalized_relative_path] = result
        return result

    def _normalize_local_image_paths(
        self,
        markdown: str,
        base_dirs: list[Path]
    ) -> str:
        """Normalize local image urls in markdown.

        Args:
            markdown: Markdown text.
            base_dirs: Candidate base directories for relative image lookup.
        """

        def _replace_md(match: re.Match) -> str:
            alt = match.group("alt")
            image_url = match.group("url")
            resolved = self._resolve_local_image_url(
                image_url = image_url,
                base_dirs = base_dirs
            )
            return f"![{alt}]({resolved})"

        def _replace_html(match: re.Match) -> str:
            image_url = match.group("url")
            resolved = self._resolve_local_image_url(
                image_url = image_url,
                base_dirs = base_dirs
            )
            return match.group(0).replace(image_url, resolved)

        rewritten = LOCAL_MD_IMAGE_PATTERN.sub(_replace_md, markdown)
        rewritten = LOCAL_HTML_IMAGE_PATTERN.sub(_replace_html, rewritten)
        return rewritten

    def _resolve_local_image_url(
        self,
        image_url: str,
        base_dirs: list[Path]
    ) -> str:
        """Resolve one markdown image url into concrete local path.

        Args:
            image_url: Raw image url extracted from markdown.
            base_dirs: Candidate base directories for relative image lookup.
        """

        normalized = (image_url or "").strip().strip('"').strip("'")
        if not normalized:
            return image_url
        if normalized.startswith("http://") or normalized.startswith("https://"):
            return normalized
        if normalized.startswith("data:"):
            return normalized

        parsed = urllib.parse.urlparse(normalized)
        if parsed.scheme:
            return normalized

        # Remove query/fragment and decode path text for local filesystem probe.
        path_text = urllib.parse.unquote(parsed.path or normalized)
        if not path_text:
            return normalized

        direct_path = Path(path_text)
        if direct_path.is_absolute() and direct_path.exists():
            return str(direct_path.resolve())

        deduplicated_base_dirs: list[Path] = []
        for base_dir in base_dirs:
            if base_dir not in deduplicated_base_dirs:
                deduplicated_base_dirs.append(base_dir)

        for base_dir in deduplicated_base_dirs:
            candidate = (base_dir / path_text).resolve()
            if candidate.exists():
                return str(candidate)

        # Keep original text when no concrete path can be inferred.
        return normalized


class GitHubSourceAdapter(SourceAdapter):
    """Source adapter using git operations instead of GitHub API.

    Args:
        repo: Repository in owner/name form, git URL, or local git path.
        ref: Branch, tag, or commit reference.
        subdir: Optional source subdirectory.
        http_client: Unused compatibility parameter kept for stable interface.
    """

    def __init__(
        self,
        repo: str,
        ref: str,
        subdir: str,
        http_client: HttpClient
    ) -> None:
        self.repo = repo.strip()
        self.ref = ref.strip() or "main"
        self.subdir = subdir.strip("/")
        self.http_client = http_client

        self._temp_dir = tempfile.TemporaryDirectory(prefix = "kg_git_")
        self._repo_root = Path(self._temp_dir.name) / "repo"
        self._prepared = False

    def list_markdown(self) -> List[str]:
        """Collect markdown files from cloned git repository.

        Args:
            self: Adapter instance.
        """

        self._prepare_repo()

        scan_root = self._scan_root()
        result = []
        for path in scan_root.rglob("*"):
            if not _is_markdown_path(path = path):
                continue
            relative = str(path.relative_to(self._repo_root)).replace("\\", "/")
            result.append(relative)
        return sorted(result)

    def read_markdown(self, relative_path: str) -> SourceDocument:
        """Read markdown content from local cloned repository.

        Args:
            self: Adapter instance.
            relative_path: Repo-relative markdown path.
        """

        self._prepare_repo()

        full_path = self._repo_root / relative_path
        markdown = full_path.read_text(encoding = "utf-8", errors = "ignore")
        title = _extract_title(markdown = markdown, relative_path = relative_path)

        relative_dir = str(Path(relative_path).parent).replace("\\", "/")
        if relative_dir == ".":
            relative_dir = ""

        base_ref = str(full_path.parent)
        return SourceDocument(
            path = relative_path,
            title = title,
            markdown = markdown,
            assets = [],
            relative_dir = relative_dir,
            base_ref = base_ref,
            source_type = "github"
        )

    def close(self) -> None:
        """Release temporary clone workspace.

        Args:
            self: Adapter instance.
        """

        if self._temp_dir is not None:
            self._temp_dir.cleanup()
            self._temp_dir = None

    def __del__(self) -> None:
        """Ensure temp directory cleanup on object deletion.

        Args:
            self: Adapter instance.
        """

        try:
            self.close()
        except Exception:
            pass

    def _prepare_repo(self) -> None:
        """Clone and checkout repository once.

        Args:
            self: Adapter instance.
        """

        if self._prepared:
            return

        if not shutil.which("git"):
            raise RuntimeError("git is required but not found in PATH")

        repo_url = _normalize_repo_url(repo = self.repo)
        clone_urls = _build_clone_urls(repo_url = repo_url)
        clone_error = ""
        for index, clone_url in enumerate(clone_urls):
            self._reset_clone_workspace()
            clone_error = self._run_git(
                args = [
                    "clone",
                    "--depth",
                    "1",
                    "--no-single-branch",
                    clone_url,
                    str(self._repo_root)
                ],
                cwd = None,
                error_prefix = "git clone failed",
                raise_on_error = False
            ) or ""
            if not clone_error:
                break
            if index < len(clone_urls) - 1:
                # Retry with next candidate URL, e.g. gh-proxy mirror.
                continue

        if clone_error:
            raise RuntimeError(f"git clone failed: {clone_error}")

        checkout_result = self._run_git(
            args = ["checkout", self.ref],
            cwd = self._repo_root,
            error_prefix = "git checkout failed",
            raise_on_error = False
        )

        if checkout_result is not None:
            self._run_git(
                args = ["fetch", "--depth", "1", "origin", self.ref],
                cwd = self._repo_root,
                error_prefix = "git fetch ref failed"
            )
            self._run_git(
                args = ["checkout", "FETCH_HEAD"],
                cwd = self._repo_root,
                error_prefix = "git checkout FETCH_HEAD failed"
            )

        scan_root = self._scan_root()
        if not scan_root.exists() or not scan_root.is_dir():
            raise RuntimeError(f"subdir not found in repo: {self.subdir}")

        self._prepared = True

    def _scan_root(self) -> Path:
        """Return scan root path for markdown discovery.

        Args:
            self: Adapter instance.
        """

        if not self.subdir:
            return self._repo_root
        return self._repo_root / self.subdir

    def _reset_clone_workspace(self) -> None:
        """Ensure clone destination directory is clean before one clone attempt.

        Args:
            self: Adapter instance.
        """

        if self._repo_root.exists():
            shutil.rmtree(self._repo_root, ignore_errors = True)

    def _run_git(
        self,
        args: List[str],
        cwd: Path | None,
        error_prefix: str,
        raise_on_error: bool = True
    ) -> str | None:
        """Run one git command.

        Args:
            args: Git args without executable name.
            cwd: Working directory.
            error_prefix: Error message prefix.
            raise_on_error: Whether to raise on non-zero exit.
        """

        cmd = ["git"] + args
        process = subprocess.run(
            cmd,
            cwd = str(cwd) if cwd else None,
            stdout = subprocess.PIPE,
            stderr = subprocess.PIPE,
            text = True,
            check = False
        )

        if process.returncode == 0:
            return None

        if not raise_on_error:
            return process.stderr.strip() or process.stdout.strip() or "unknown git error"

        error_message = process.stderr.strip() or process.stdout.strip() or "unknown git error"
        raise RuntimeError(f"{error_prefix}: {error_message}")


def _normalize_repo_url(repo: str) -> str:
    """Normalize repository input into git clone URL/path.

    Args:
        repo: Repository string.
    """

    value = repo.strip()
    if not value:
        raise ValueError("repo is required")

    # Local git path.
    if os.path.exists(value):
        return os.path.abspath(value)

    # owner/name style.
    if "/" in value and not value.startswith("http://") and not value.startswith("https://") and not value.endswith(".git"):
        value = f"https://github.com/{value}.git"

    # URL style.
    if value.startswith("https://") or value.startswith("http://"):
        if not value.endswith(".git"):
            value = f"{value}.git"
        return value

    # scp-like git style, keep as-is.
    return value


def _build_clone_urls(repo_url: str) -> List[str]:
    """Build clone URL candidates with optional mirror fallback.

    Args:
        repo_url: Normalized git clone URL.
    """

    candidates = [repo_url]
    if _is_github_https_url(repo_url = repo_url):
        fallback = f"https://gh-proxy.com/{repo_url}"
        if fallback not in candidates:
            candidates.append(fallback)
    return candidates


def _is_github_https_url(repo_url: str) -> bool:
    """Check whether one URL points to github.com over HTTPS.

    Args:
        repo_url: Repository clone URL.
    """

    parsed = urllib.parse.urlparse(repo_url)
    if parsed.scheme != "https":
        return False
    return (parsed.hostname or "").lower() == "github.com"


def _extract_title(markdown: str, relative_path: str) -> str:
    """Extract title from first heading or fallback filename.

    Args:
        markdown: Markdown content.
        relative_path: Source-relative markdown path.
    """

    match = re.search(r"^#\s+(.+?)\s*$", markdown, flags = re.MULTILINE)
    if match:
        return match.group(1).strip()
    return Path(relative_path).stem


def _is_markdown_path(path: Path) -> bool:
    """Check whether path is one markdown file supported by importer.

    Args:
        path: Local filesystem path.
    """

    if not path.is_file():
        return False
    return path.suffix.lower() in {".md", ".markdown"}


def _is_local_supported_path(path: Path) -> bool:
    """Check whether one local path is supported by local source adapter.

    Args:
        path: Local filesystem path.
    """

    if not path.is_file():
        return False
    return path.suffix.lower() in {".md", ".markdown", ".docx"}
