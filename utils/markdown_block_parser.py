import re

from dataclasses import dataclass


TABLE_ALIGN_PATTERN = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$"
)
HEADING_PATTERN = re.compile(r"^\s{0,3}#{1,6}\s+.+$")
LIST_PATTERN = re.compile(r"^\s{0,3}([-*+]|\d+\.)\s+.+$")
BLOCKQUOTE_PATTERN = re.compile(r"^\s{0,3}>\s*.+$")
FENCE_PATTERN = re.compile(r"^\s{0,3}(```|~~~)")


@dataclass
class MarkdownBlockSegment:
    """One semantic markdown segment for block-wise writing.

    Args:
        kind: Semantic block kind.
        content: Original markdown content of this segment.
    """

    kind: str
    content: str


def split_markdown_to_semantic_blocks(content: str) -> list[MarkdownBlockSegment]:
    """Split markdown into semantic blocks by lightweight rules.

    Args:
        content: Full markdown content.
    """

    if not content or not content.strip():
        return []

    lines = content.splitlines()
    segments: list[MarkdownBlockSegment] = []
    index = 0

    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue

        line = lines[index]

        if _is_fence_start(line = line):
            segment_text, next_index = _collect_fence_block(
                lines = lines,
                start_index = index
            )
            segments.append(
                MarkdownBlockSegment(
                    kind = "code_fence",
                    content = segment_text
                )
            )
            index = next_index
            continue

        if _is_heading(line = line):
            segments.append(
                MarkdownBlockSegment(
                    kind = "heading",
                    content = line
                )
            )
            index += 1
            continue

        if _is_table_start(lines = lines, start_index = index):
            segment_text, next_index = _collect_table_block(
                lines = lines,
                start_index = index
            )
            segments.append(
                MarkdownBlockSegment(
                    kind = "table",
                    content = segment_text
                )
            )
            index = next_index
            continue

        if _is_list_or_quote(line = line):
            segment_text, next_index = _collect_list_or_quote_block(
                lines = lines,
                start_index = index
            )
            segments.append(
                MarkdownBlockSegment(
                    kind = "list_or_quote",
                    content = segment_text
                )
            )
            index = next_index
            continue

        segment_text, next_index = _collect_paragraph_block(
            lines = lines,
            start_index = index
        )
        segments.append(
            MarkdownBlockSegment(
                kind = "paragraph",
                content = segment_text
            )
        )
        index = next_index

    return segments


def _collect_fence_block(lines: list[str], start_index: int) -> tuple[str, int]:
    """Collect fenced code block.

    Args:
        lines: Markdown lines.
        start_index: Start line index.
    """

    start_line = lines[start_index]
    marker_match = FENCE_PATTERN.match(start_line)
    marker = "```"
    if marker_match:
        marker = marker_match.group(1)

    collected = [start_line]
    index = start_index + 1
    while index < len(lines):
        collected.append(lines[index])
        if lines[index].strip().startswith(marker):
            index += 1
            break
        index += 1
    return "\n".join(collected), index


def _collect_table_block(lines: list[str], start_index: int) -> tuple[str, int]:
    """Collect markdown table block.

    Args:
        lines: Markdown lines.
        start_index: Start line index.
    """

    collected = []
    index = start_index
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            break
        if "|" not in line:
            break
        collected.append(line)
        index += 1
    return "\n".join(collected), index


def _collect_list_or_quote_block(lines: list[str], start_index: int) -> tuple[str, int]:
    """Collect list or blockquote block.

    Args:
        lines: Markdown lines.
        start_index: Start line index.
    """

    collected = []
    index = start_index
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            break
        if _is_list_or_quote(line = line) or line.startswith("    ") or line.startswith("\t"):
            collected.append(line)
            index += 1
            continue
        break
    return "\n".join(collected), index


def _collect_paragraph_block(lines: list[str], start_index: int) -> tuple[str, int]:
    """Collect plain paragraph block until next semantic block boundary.

    Args:
        lines: Markdown lines.
        start_index: Start line index.
    """

    collected = []
    index = start_index
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            break
        if index > start_index and (
            _is_heading(line = line)
            or _is_fence_start(line = line)
            or _is_table_start(lines = lines, start_index = index)
            or _is_list_or_quote(line = line)
        ):
            break
        collected.append(line)
        index += 1
    return "\n".join(collected), index


def _is_heading(line: str) -> bool:
    """Check whether one line is markdown heading.

    Args:
        line: Markdown line.
    """

    return bool(HEADING_PATTERN.match(line))


def _is_list_or_quote(line: str) -> bool:
    """Check whether one line is list item or blockquote.

    Args:
        line: Markdown line.
    """

    return bool(LIST_PATTERN.match(line) or BLOCKQUOTE_PATTERN.match(line))


def _is_fence_start(line: str) -> bool:
    """Check whether one line starts fenced code block.

    Args:
        line: Markdown line.
    """

    return bool(FENCE_PATTERN.match(line))


def _is_table_start(lines: list[str], start_index: int) -> bool:
    """Check whether current position looks like table start.

    Args:
        lines: Markdown lines.
        start_index: Current line index.
    """

    if start_index + 1 >= len(lines):
        return False
    header = lines[start_index]
    align = lines[start_index + 1]
    if "|" not in header:
        return False
    return bool(TABLE_ALIGN_PATTERN.match(align))
