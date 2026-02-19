import shutil
import subprocess
import tempfile
import unittest

from pathlib import Path

from data.source_adapters import GitHubSourceAdapter
from data.source_adapters import LocalSourceAdapter
from data.source_adapters import _build_clone_urls
from data.source_adapters import _normalize_repo_url
from data.source_adapters import _is_github_https_url
from utils.http_client import HttpClient


class TestLocalSourceAdapter(unittest.TestCase):
    """Tests for local source adapter."""

    def test_list_and_read_markdown(self) -> None:
        """Should discover markdown and extract title.

        Args:
            self: Test case instance.
        """

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a").mkdir(parents = True, exist_ok = True)
            (root / "a" / "demo.md").write_text("# Demo\ncontent", encoding = "utf-8")
            (root / "a" / "ignore.txt").write_text("x", encoding = "utf-8")

            adapter = LocalSourceAdapter(root_path = str(root))
            paths = adapter.list_markdown()

            self.assertEqual(paths, ["a/demo.md"])
            doc = adapter.read_markdown(relative_path = "a/demo.md")
            self.assertEqual(doc.title, "Demo")
            self.assertEqual(doc.relative_dir, "a")

    def test_list_and_read_markdown_single_file_mode(self) -> None:
        """Should support importing one local markdown file directly.

        Args:
            self: Test case instance.
        """

        with tempfile.TemporaryDirectory() as tmp:
            markdown_path = Path(tmp) / "single.md"
            markdown_path.write_text("# Single\ncontent", encoding = "utf-8")

            adapter = LocalSourceAdapter(root_path = str(markdown_path))
            paths = adapter.list_markdown()

            self.assertEqual(paths, ["single.md"])
            doc = adapter.read_markdown(relative_path = "single.md")
            self.assertEqual(doc.title, "Single")
            self.assertEqual(doc.relative_dir, "")

    def test_list_markdown_supports_markdown_extension(self) -> None:
        """Should include both .md and .markdown files.

        Args:
            self: Test case instance.
        """

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir(parents = True, exist_ok = True)
            (root / "docs" / "a.md").write_text("# A\n", encoding = "utf-8")
            (root / "docs" / "b.markdown").write_text("# B\n", encoding = "utf-8")

            adapter = LocalSourceAdapter(root_path = str(root))
            paths = adapter.list_markdown()
            self.assertEqual(paths, ["docs/a.md", "docs/b.markdown"])


class TestGitHubSourceAdapter(unittest.TestCase):
    """Tests for git-based GitHub source adapter."""

    def setUp(self) -> None:
        """Skip git-based tests if git is unavailable.

        Args:
            self: Test case instance.
        """

        if not shutil.which("git"):
            self.skipTest("git is required for source adapter tests")

    def test_repo_url_normalization(self) -> None:
        """Should normalize owner/name input to clone URL.

        Args:
            self: Test case instance.
        """

        url = _normalize_repo_url(repo = "owner/repo")
        self.assertEqual(url, "https://github.com/owner/repo.git")

    def test_build_clone_urls_with_github_fallback(self) -> None:
        """Should include gh-proxy fallback for github HTTPS URLs.

        Args:
            self: Test case instance.
        """

        urls = _build_clone_urls(repo_url = "https://github.com/owner/repo.git")
        self.assertEqual(
            urls,
            [
                "https://github.com/owner/repo.git",
                "https://gh-proxy.com/https://github.com/owner/repo.git"
            ]
        )

    def test_build_clone_urls_with_tokenized_github_url(self) -> None:
        """Should also fallback when github URL contains userinfo token.

        Args:
            self: Test case instance.
        """

        urls = _build_clone_urls(repo_url = "https://token123@github.com/owner/repo.git")
        self.assertEqual(
            urls,
            [
                "https://token123@github.com/owner/repo.git",
                "https://gh-proxy.com/https://token123@github.com/owner/repo.git"
            ]
        )

    def test_is_github_https_url(self) -> None:
        """Should detect github HTTPS URL accurately.

        Args:
            self: Test case instance.
        """

        self.assertEqual(_is_github_https_url("https://github.com/a/b.git"), True)
        self.assertEqual(_is_github_https_url("https://token@github.com/a/b.git"), True)
        self.assertEqual(_is_github_https_url("http://github.com/a/b.git"), False)
        self.assertEqual(_is_github_https_url("https://gitlab.com/a/b.git"), False)

    def test_clone_local_repo_and_read_markdown(self) -> None:
        """Should clone local git repo and read markdown.

        Args:
            self: Test case instance.
        """

        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo_src"
            repo_root.mkdir(parents = True, exist_ok = True)

            (repo_root / "docs").mkdir(parents = True, exist_ok = True)
            (repo_root / "docs" / "chapter.md").write_text(
                "# Chapter\nhello",
                encoding = "utf-8"
            )
            (repo_root / "README.md").write_text("# Home\ntext", encoding = "utf-8")

            self._run(["git", "init"], cwd = repo_root)
            self._run(["git", "config", "user.name", "tester"], cwd = repo_root)
            self._run(["git", "config", "user.email", "tester@example.com"], cwd = repo_root)
            self._run(["git", "add", "."], cwd = repo_root)
            self._run(["git", "commit", "-m", "init"], cwd = repo_root)

            adapter = GitHubSourceAdapter(
                repo = str(repo_root),
                ref = "HEAD",
                subdir = "docs",
                http_client = HttpClient()
            )

            paths = adapter.list_markdown()
            self.assertEqual(paths, ["docs/chapter.md"])

            doc = adapter.read_markdown(relative_path = "docs/chapter.md")
            self.assertEqual(doc.title, "Chapter")
            self.assertEqual(doc.relative_dir, "docs")
            self.assertEqual(doc.source_type, "github")
            adapter.close()

    def _run(self, cmd: list[str], cwd: Path) -> None:
        """Run command and assert it succeeds.

        Args:
            self: Test case instance.
            cmd: Command argv list.
            cwd: Command cwd path.
        """

        process = subprocess.run(
            cmd,
            cwd = str(cwd),
            stdout = subprocess.PIPE,
            stderr = subprocess.PIPE,
            text = True,
            check = False
        )
        self.assertEqual(
            process.returncode,
            0,
            msg = f"Command failed: {' '.join(cmd)}\nstdout: {process.stdout}\nstderr: {process.stderr}"
        )


if __name__ == "__main__":
    unittest.main()
