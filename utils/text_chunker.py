from typing import List


def chunk_text_by_bytes(text: str, max_bytes: int) -> List[str]:
    """Split plain text into UTF-8-safe chunks by byte size.

    Args:
        text: Input text content.
        max_bytes: Maximum bytes per chunk.
    """

    if max_bytes <= 0:
        raise ValueError("max_bytes must be > 0")

    chunks: List[str] = []
    current = ""
    current_bytes = 0

    for char in text:
        char_bytes = len(char.encode("utf-8"))
        if current and current_bytes + char_bytes > max_bytes:
            chunks.append(current)
            current = char
            current_bytes = char_bytes
        else:
            current += char
            current_bytes += char_bytes

    if current:
        chunks.append(current)

    if not chunks:
        return [""]
    return chunks


def split_markdown_by_lines(content: str, max_bytes: int) -> List[str]:
    """Split markdown content by lines while respecting byte limits.

    Args:
        content: Markdown content.
        max_bytes: Maximum bytes per chunk.
    """

    if len(content.encode("utf-8")) <= max_bytes:
        return [content]

    chunks: List[str] = []
    lines = content.splitlines(keepends = True)

    current = ""
    for line in lines:
        line_bytes = len(line.encode("utf-8"))
        if line_bytes > max_bytes:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(chunk_text_by_bytes(text = line, max_bytes = max_bytes))
            continue

        candidate = current + line
        if current and len(candidate.encode("utf-8")) > max_bytes:
            chunks.append(current)
            current = line
        else:
            current = candidate

    if current:
        chunks.append(current)

    return chunks
