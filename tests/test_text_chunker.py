import unittest

from utils.text_chunker import chunk_text_by_bytes
from utils.text_chunker import split_markdown_by_lines


class TestTextChunker(unittest.TestCase):
    """Tests for text and markdown chunking helpers."""

    def test_chunk_text_by_bytes(self) -> None:
        """Should split text into byte-limited chunks.

        Args:
            self: Test case instance.
        """

        chunks = chunk_text_by_bytes(text = "abcdefghijk", max_bytes = 5)
        self.assertEqual(chunks, ["abcde", "fghij", "k"])

    def test_split_markdown_by_lines(self) -> None:
        """Should split markdown by lines with byte limit.

        Args:
            self: Test case instance.
        """

        content = "line1\nline2\nline3\n"
        chunks = split_markdown_by_lines(content = content, max_bytes = 10)
        self.assertGreaterEqual(len(chunks), 2)
        for chunk in chunks:
            self.assertLessEqual(len(chunk.encode("utf-8")), 10)


if __name__ == "__main__":
    unittest.main()
