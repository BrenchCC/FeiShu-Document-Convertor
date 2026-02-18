import unittest

from utils.markdown_block_parser import split_markdown_to_semantic_blocks


class TestMarkdownBlockParser(unittest.TestCase):
    """Tests for markdown semantic block splitting."""

    def test_split_heading_paragraph_table_code(self) -> None:
        """Should split markdown into expected semantic blocks.

        Args:
            self: Test case instance.
        """

        content = (
            "# Title\n"
            "\n"
            "This is one paragraph with **bold** text.\n"
            "\n"
            "| A | B |\n"
            "| --- | --- |\n"
            "| 1 | 2 |\n"
            "\n"
            "```python\n"
            "print('hello')\n"
            "```\n"
        )

        segments = split_markdown_to_semantic_blocks(content = content)
        kinds = [item.kind for item in segments]
        self.assertEqual(
            kinds,
            ["heading", "paragraph", "table", "code_fence"]
        )
        self.assertIn("**bold**", segments[1].content)
        self.assertIn("| --- | --- |", segments[2].content)
        self.assertIn("print('hello')", segments[3].content)

    def test_split_list_block(self) -> None:
        """Should group continuous list items as one block.

        Args:
            self: Test case instance.
        """

        content = (
            "- item 1\n"
            "- item 2\n"
            "  - sub item\n"
            "\n"
            "after list\n"
        )
        segments = split_markdown_to_semantic_blocks(content = content)
        self.assertEqual(segments[0].kind, "list_or_quote")
        self.assertTrue(segments[0].content.startswith("- item 1"))
        self.assertEqual(segments[1].kind, "paragraph")


if __name__ == "__main__":
    unittest.main()
