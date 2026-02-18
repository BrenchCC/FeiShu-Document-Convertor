import abc
import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse

from pathlib import Path
from typing import List

from data.models import SourceDocument
from utils.http_client import HttpClient


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
    """Source adapter for local markdown directory.

    Args:
        root_path: Local root directory path.
    """

    def __init__(self, root_path: str) -> None:
        self.root_path = os.path.abspath(root_path)

    def list_markdown(self) -> List[str]:
        """Collect markdown files from local root.

        Args:
            self: Adapter instance.
        """

        result = []
        for path in Path(self.root_path).rglob("*.md"):
            relative = str(path.relative_to(self.root_path)).replace("\\", "/")
            result.append(relative)
        return sorted(result)

    def read_markdown(self, relative_path: str) -> SourceDocument:
        """Read local markdown and return structured document.

        Args:
            self: Adapter instance.
            relative_path: Source-relative markdown path.
        """

        full_path = Path(self.root_path) / relative_path
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
            source_type = "local"
        )


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
        for path in scan_root.rglob("*.md"):
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
