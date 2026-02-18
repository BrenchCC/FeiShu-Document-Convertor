import os
import tempfile
import unittest

from utils.oauth_local_auth import capture_oauth_code_by_local_server
from utils.oauth_local_auth import persist_user_tokens_to_env


class TestOauthLocalAuth(unittest.TestCase):
    """Tests for local OAuth auth helper module."""

    def test_persist_user_tokens_to_env(self) -> None:
        """Should write or update token keys in dotenv file.

        Args:
            self: Test case instance.
        """

        with tempfile.TemporaryDirectory() as tmp:
            dotenv_path = os.path.join(tmp, ".env")
            with open(dotenv_path, "w", encoding = "utf-8") as fp:
                fp.write("A=1\n")
                fp.write("FEISHU_USER_ACCESS_TOKEN=old\n")

            persist_user_tokens_to_env(
                access_token = "access_new",
                refresh_token = "refresh_new",
                token_cache_path = ".cache/token.json",
                dotenv_path = dotenv_path
            )

            with open(dotenv_path, "r", encoding = "utf-8") as fp:
                content = fp.read()

            self.assertIn("A=1\n", content)
            self.assertIn("FEISHU_USER_ACCESS_TOKEN=access_new\n", content)
            self.assertIn("FEISHU_USER_REFRESH_TOKEN=refresh_new\n", content)
            self.assertIn("FEISHU_USER_TOKEN_CACHE_PATH=.cache/token.json\n", content)

    def test_capture_oauth_reject_non_http_redirect(self) -> None:
        """Should reject redirect URI not using http for local server mode.

        Args:
            self: Test case instance.
        """

        with self.assertRaises(ValueError):
            capture_oauth_code_by_local_server(
                authorize_url = "https://accounts.feishu.cn/open-apis/authen/v1/authorize",
                redirect_uri = "https://example.com/callback",
                timeout_seconds = 5,
                open_browser = False
            )

    def test_capture_oauth_reject_non_localhost_redirect(self) -> None:
        """Should reject redirect URI not bound to localhost.

        Args:
            self: Test case instance.
        """

        with self.assertRaises(ValueError):
            capture_oauth_code_by_local_server(
                authorize_url = "https://accounts.feishu.cn/open-apis/authen/v1/authorize",
                redirect_uri = "http://example.com/callback",
                timeout_seconds = 5,
                open_browser = False
            )


if __name__ == "__main__":
    unittest.main()
