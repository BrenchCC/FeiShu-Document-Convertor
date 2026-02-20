import shutil
import subprocess
import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch

from data.source_adapters import GitHubSourceAdapter
from data.source_adapters import LocalSourceAdapter
from data.source_adapters import _build_clone_urls
from data.source_adapters import _normalize_repo_url
from data.source_adapters import _is_github_https_url
from utils.http_client import HttpClient
from utils.docx_converter import DocxConversionResult


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

    def test_list_markdown_supports_docx_extension(self) -> None:
        """Should include .docx files for local source adapter.

        Args:
            self: Test case instance.
        """

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir(parents = True, exist_ok = True)
            (root / "docs" / "a.docx").write_bytes(b"fake-docx")

            adapter = LocalSourceAdapter(root_path = str(root))
            paths = adapter.list_markdown()
            self.assertEqual(paths, ["docs/a.docx"])

    def test_read_markdown_infers_image_path_from_local_source_root(self) -> None:
        """Should infer image path for markdown via source root fallback.

        Args:
            self: Test case instance.
        """

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs_dir = root / "docs"
            assets_dir = root / "assets"
            docs_dir.mkdir(parents = True, exist_ok = True)
            assets_dir.mkdir(parents = True, exist_ok = True)

            markdown_path = docs_dir / "guide.md"
            markdown_path.write_text(
                "# Guide\n![Logo](assets/logo.png)\n",
                encoding = "utf-8"
            )
            image_path = assets_dir / "logo.png"
            image_path.write_bytes(b"png")

            adapter = LocalSourceAdapter(root_path = str(root))
            doc = adapter.read_markdown(relative_path = "docs/guide.md")

            self.assertIn(str(image_path.resolve()), doc.markdown)

    @patch("data.source_adapters.convert_docx_to_markdown")
    def test_read_docx_single_file_mode(self, mock_convert) -> None:
        """Should convert and read one local DOCX file.

        Args:
            self: Test case instance.
            mock_convert: Mocked DOCX converter.
        """

        with tempfile.TemporaryDirectory() as tmp:
            docx_path = Path(tmp) / "single.docx"
            docx_path.write_bytes(b"fake-docx")

            converted_dir = Path(tmp) / "converted"
            converted_dir.mkdir(parents = True, exist_ok = True)
            converted_md_path = converted_dir / "converted.md"
            converted_md_path.write_text("# Converted\ncontent", encoding = "utf-8")
            mock_convert.return_value = DocxConversionResult(
                markdown = "# Converted\ncontent",
                markdown_path = str(converted_md_path),
                media_dir = str(converted_dir / "media")
            )

            adapter = LocalSourceAdapter(root_path = str(docx_path))
            paths = adapter.list_markdown()
            self.assertEqual(paths, ["single.docx"])

            doc = adapter.read_markdown(relative_path = "single.docx")
            self.assertEqual(doc.title, "Converted")
            self.assertEqual(doc.base_ref, str(converted_md_path.parent))
            self.assertEqual(doc.source_type, "local")
            mock_convert.assert_called_once()

    @patch("data.source_adapters.convert_docx_to_markdown")
    def test_read_docx_conversion_failure(self, mock_convert) -> None:
        """Should raise readable error when DOCX conversion fails.

        Args:
            self: Test case instance.
            mock_convert: Mocked DOCX converter.
        """

        with tempfile.TemporaryDirectory() as tmp:
            docx_path = Path(tmp) / "single.docx"
            docx_path.write_bytes(b"fake-docx")
            mock_convert.side_effect = RuntimeError("pandoc missing")

            adapter = LocalSourceAdapter(root_path = str(docx_path))
            with self.assertRaises(RuntimeError) as err:
                adapter.read_markdown(relative_path = "single.docx")

            self.assertIn("DOCX convert failed", str(err.exception))

    @patch("data.source_adapters.convert_docx_to_markdown")
    def test_read_docx_infers_image_path_from_docx_absolute_parent(self, mock_convert) -> None:
        """Should infer concrete image path based on absolute DOCX parent path.

        Args:
            self: Test case instance.
            mock_convert: Mocked DOCX converter.
        """

        with tempfile.TemporaryDirectory() as tmp:
            docs_dir = Path(tmp) / "docs"
            images_dir = docs_dir / "images"
            docs_dir.mkdir(parents = True, exist_ok = True)
            images_dir.mkdir(parents = True, exist_ok = True)

            docx_path = docs_dir / "guide.docx"
            docx_path.write_bytes(b"fake-docx")
            image_path = images_dir / "diagram.png"
            image_path.write_bytes(b"png")

            converted_dir = Path(tmp) / "converted"
            converted_dir.mkdir(parents = True, exist_ok = True)
            converted_md_path = converted_dir / "converted.md"
            converted_md_path.write_text(
                "# Converted\n![Diagram](images/diagram.png)\n",
                encoding = "utf-8"
            )
            mock_convert.return_value = DocxConversionResult(
                markdown = "# Converted\n![Diagram](images/diagram.png)\n",
                markdown_path = str(converted_md_path),
                media_dir = str(converted_dir / "media")
            )

            adapter = LocalSourceAdapter(root_path = str(docx_path))
            doc = adapter.read_markdown(relative_path = "guide.docx")

            self.assertIn(str(image_path.resolve()), doc.markdown)


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
