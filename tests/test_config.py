import os
import tempfile
import unittest

from config.config import AppConfig


class TestConfig(unittest.TestCase):
    """Tests for config loading behavior."""

    def test_load_from_dotenv(self) -> None:
        """Should read env values from local .env file.

        Args:
            self: Test case instance.
        """

        original_cwd = os.getcwd()
        original_env = dict(os.environ)

        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.chdir(tmp)
                with open(".env", "w", encoding = "utf-8") as fp:
                    fp.write("FEISHU_APP_ID=app_1\n")
                    fp.write("FEISHU_APP_SECRET=sec_1\n")
                    fp.write("FEISHU_USER_ACCESS_TOKEN=u_1\n")
                    fp.write("FEISHU_USER_REFRESH_TOKEN=r_1\n")
                    fp.write("FEISHU_USER_TOKEN_CACHE_PATH=.cache/token.json\n")
                    fp.write("FEISHU_WEBHOOK_URL=https://example.com/hook\n")
                    fp.write("LLM_BASE_URL=https://example.com/v1\n")
                    fp.write("LLM_API_KEY=sk_test\n")
                    fp.write("LLM_MODEL=gpt-4.1-mini\n")

                for key in [
                    "FEISHU_APP_ID",
                    "FEISHU_APP_SECRET",
                    "FEISHU_USER_ACCESS_TOKEN",
                    "FEISHU_USER_REFRESH_TOKEN",
                    "FEISHU_USER_TOKEN_CACHE_PATH",
                    "FEISHU_WEBHOOK_URL",
                    "LLM_BASE_URL",
                    "LLM_API_KEY",
                    "LLM_MODEL"
                ]:
                    os.environ.pop(key, None)

                config = AppConfig.from_env()
                self.assertEqual(config.feishu_app_id, "app_1")
                self.assertEqual(config.feishu_app_secret, "sec_1")
                self.assertEqual(config.feishu_user_access_token, "u_1")
                self.assertEqual(config.feishu_user_refresh_token, "r_1")
                self.assertEqual(config.feishu_user_token_cache_path, ".cache/token.json")
                self.assertEqual(config.feishu_webhook_url, "https://example.com/hook")
                self.assertEqual(config.llm_base_url, "https://example.com/v1")
                self.assertEqual(config.llm_api_key, "sk_test")
                self.assertEqual(config.llm_model, "gpt-4.1-mini")
        finally:
            os.chdir(original_cwd)
            os.environ.clear()
            os.environ.update(original_env)


if __name__ == "__main__":
    unittest.main()
