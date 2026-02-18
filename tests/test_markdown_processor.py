import unittest

from utils.markdown_processor import MarkdownProcessor


class TestMarkdownProcessor(unittest.TestCase):
    """Tests for markdown asset and formula processing."""

    def setUp(self) -> None:
        """Create processor fixture.

        Args:
            self: Test case instance.
        """

        self.processor = MarkdownProcessor()

    def test_extract_assets_and_formulas(self) -> None:
        """Should parse markdown/html images and formula count.

        Args:
            self: Test case instance.
        """

        markdown = (
            "# title\n"
            "inline math $a+b$\n"
            "block math: $$x^2$$\n"
            "![img](./images/a.png)\n"
            "<img src=\"../assets/b.jpg\" width=\"30%\" />\n"
        )
        processed = self.processor.extract_assets_and_math(
            md_text = markdown,
            base_path_or_url = "/tmp/docs/ch1"
        )

        self.assertEqual(processed.formula_count, 2)
        self.assertEqual(len(processed.assets), 2)
        self.assertTrue(processed.assets[0].resolved_url.endswith("/tmp/docs/ch1/images/a.png"))
        self.assertTrue(processed.assets[1].resolved_url.endswith("/tmp/docs/assets/b.jpg"))

    def test_replace_asset_links(self) -> None:
        """Should replace image links with token URL.

        Args:
            self: Test case instance.
        """

        markdown = "![a](./a.png)\n<img src=\"./b.png\" />"
        token_map = {
            "./a.png": "token_a",
            "./b.png": "token_b"
        }

        replaced = self.processor.replace_asset_links(
            md_text = markdown,
            token_map = token_map,
            image_url_template = "https://example.com/{token}"
        )

        self.assertIn("https://example.com/token_a", replaced)
        self.assertIn("https://example.com/token_b", replaced)


if __name__ == "__main__":
    unittest.main()
