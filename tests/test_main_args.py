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
        self.assertEqual(args.folder_subdirs, False)

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
        self.assertEqual(args.folder_subdirs, False)

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


if __name__ == "__main__":
    unittest.main()
