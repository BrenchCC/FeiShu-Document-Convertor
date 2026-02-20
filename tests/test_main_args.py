import unittest

from unittest import mock

from main import parse_args


class TestMainArgs(unittest.TestCase):
    """Tests for CLI argument parser."""

    def test_parse_local(self) -> None:
        """Should parse local source arguments.

        Args:
            self: Test case instance.
        """

        argv = [
            "prog",
            "--source",
            "local",
            "--path",
            "./docs",
            "--space-name",
            "demo"
        ]
        with mock.patch("sys.argv", argv):
            args = parse_args()

        self.assertEqual(args.source, "local")
        self.assertEqual(args.path, "./docs")
        self.assertEqual(args.space_name, "demo")
        self.assertEqual(args.space_id, "")
        self.assertEqual(args.write_mode, "folder")
        self.assertEqual(args.structure_order, "toc_first")
        self.assertEqual(args.toc_file, "TABLE_OF_CONTENTS.md")
        self.assertEqual(args.folder_nav_doc, True)
        self.assertEqual(args.folder_nav_title, "00-导航总目录")
        self.assertEqual(args.llm_fallback, "toc_ambiguity")
        self.assertEqual(args.llm_max_calls, 3)
        self.assertEqual(args.skip_root_readme, False)
        self.assertEqual(args.folder_subdirs, False)
        self.assertEqual(args.folder_root_subdir, True)
        self.assertEqual(args.folder_root_subdir_name, "")
        self.assertEqual(args.max_workers, 1)
        self.assertEqual(args.chunk_workers, 2)

    def test_parse_github(self) -> None:
        """Should parse github source arguments.

        Args:
            self: Test case instance.
        """

        argv = [
            "prog",
            "--source",
            "github",
            "--repo",
            "owner/repo",
            "--space-name",
            "demo",
            "--ref",
            "main"
        ]
        with mock.patch("sys.argv", argv):
            args = parse_args()

        self.assertEqual(args.source, "github")
        self.assertEqual(args.repo, "owner/repo")
        self.assertEqual(args.ref, "main")
        self.assertEqual(args.space_id, "")
        self.assertEqual(args.write_mode, "folder")
        self.assertEqual(args.structure_order, "toc_first")
        self.assertEqual(args.folder_subdirs, False)
        self.assertEqual(args.folder_root_subdir, True)
        self.assertEqual(args.folder_root_subdir_name, "")
        self.assertEqual(args.max_workers, 1)
        self.assertEqual(args.chunk_workers, 2)

    def test_parse_wiki_with_space_id(self) -> None:
        """Should parse wiki mode with existing space id.

        Args:
            self: Test case instance.
        """

        argv = [
            "prog",
            "--source",
            "github",
            "--repo",
            "owner/repo",
            "--write-mode",
            "wiki",
            "--space-id",
            "space_123"
        ]
        with mock.patch("sys.argv", argv):
            args = parse_args()

        self.assertEqual(args.write_mode, "wiki")
        self.assertEqual(args.space_id, "space_123")

    def test_parse_auth_code(self) -> None:
        """Should parse OAuth bootstrap arguments.

        Args:
            self: Test case instance.
        """

        argv = [
            "prog",
            "--source",
            "github",
            "--repo",
            "owner/repo",
            "--write-mode",
            "wiki",
            "--space-name",
            "demo",
            "--auth-code",
            "code_abc",
            "--oauth-redirect-uri",
            "https://callback.example.com/auth"
        ]
        with mock.patch("sys.argv", argv):
            args = parse_args()

        self.assertEqual(args.auth_code, "code_abc")
        self.assertEqual(args.oauth_redirect_uri, "https://callback.example.com/auth")

    def test_parse_print_auth_url(self) -> None:
        """Should parse OAuth authorize URL options.

        Args:
            self: Test case instance.
        """

        argv = [
            "prog",
            "--source",
            "local",
            "--path",
            "./docs",
            "--write-mode",
            "wiki",
            "--space-name",
            "demo",
            "--print-auth-url",
            "--oauth-redirect-uri",
            "https://callback.example.com/auth",
            "--oauth-scope",
            "wiki:wiki offline_access",
            "--oauth-state",
            "state_1"
        ]
        with mock.patch("sys.argv", argv):
            args = parse_args()

        self.assertEqual(args.print_auth_url, True)
        self.assertEqual(args.oauth_scope, "wiki:wiki offline_access")
        self.assertEqual(args.oauth_state, "state_1")

    def test_parse_structure_and_llm_options(self) -> None:
        """Should parse structure planning and LLM fallback options.

        Args:
            self: Test case instance.
        """

        argv = [
            "prog",
            "--source",
            "local",
            "--path",
            "./docs",
            "--write-mode",
            "both",
            "--structure-order",
            "path",
            "--toc-file",
            "docs/toc.md",
            "--no-folder-nav-doc",
            "--folder-nav-title",
            "Directory Overview",
            "--llm-fallback",
            "off",
            "--llm-max-calls",
            "0"
        ]
        with mock.patch("sys.argv", argv):
            args = parse_args()

        self.assertEqual(args.structure_order, "path")
        self.assertEqual(args.toc_file, "docs/toc.md")
        self.assertEqual(args.folder_nav_doc, False)
        self.assertEqual(args.folder_nav_title, "Directory Overview")
        self.assertEqual(args.llm_fallback, "off")
        self.assertEqual(args.llm_max_calls, 0)

    def test_parse_folder_subdirs_flag(self) -> None:
        """Should parse folder hierarchy flag for folder mode.

        Args:
            self: Test case instance.
        """

        argv = [
            "prog",
            "--source",
            "local",
            "--path",
            "./docs",
            "--write-mode",
            "folder",
            "--folder-subdirs"
        ]
        with mock.patch("sys.argv", argv):
            args = parse_args()

        self.assertEqual(args.folder_subdirs, True)

    def test_parse_folder_root_subdir_options(self) -> None:
        """Should parse folder root subdir options.

        Args:
            self: Test case instance.
        """

        argv = [
            "prog",
            "--source",
            "local",
            "--path",
            "./docs",
            "--write-mode",
            "folder",
            "--no-folder-root-subdir",
            "--folder-root-subdir-name",
            "batch_demo"
        ]
        with mock.patch("sys.argv", argv):
            args = parse_args()

        self.assertEqual(args.folder_root_subdir, False)
        self.assertEqual(args.folder_root_subdir_name, "batch_demo")

    def test_parse_chunk_workers_option(self) -> None:
        """Should parse chunk worker option.

        Args:
            self: Test case instance.
        """

        argv = [
            "prog",
            "--source",
            "local",
            "--path",
            "./docs",
            "--chunk-workers",
            "4"
        ]
        with mock.patch("sys.argv", argv):
            args = parse_args()

        self.assertEqual(args.chunk_workers, 4)

    def test_parse_max_workers_option(self) -> None:
        """Should parse max worker option.

        Args:
            self: Test case instance.
        """

        argv = [
            "prog",
            "--source",
            "local",
            "--path",
            "./docs",
            "--max-workers",
            "3"
        ]
        with mock.patch("sys.argv", argv):
            args = parse_args()

        self.assertEqual(args.max_workers, 3)

    def test_parse_skip_root_readme_option(self) -> None:
        """Should parse skip root README option.

        Args:
            self: Test case instance.
        """

        argv = [
            "prog",
            "--source",
            "local",
            "--path",
            "./docs",
            "--skip-root-readme"
        ]
        with mock.patch("sys.argv", argv):
            args = parse_args()

        self.assertEqual(args.skip_root_readme, True)


if __name__ == "__main__":
    unittest.main()
