import shutil
import subprocess

from dataclasses import dataclass
from pathlib import Path


@dataclass
class DocxConversionResult:
    """DOCX conversion output.

    Args:
        markdown: Converted markdown text.
        markdown_path: Absolute markdown output path.
        media_dir: Absolute extracted media directory.
    """

    markdown: str
    markdown_path: str
    media_dir: str


def convert_docx_to_markdown(
    docx_path: str,
    output_dir: str,
    track_changes: str = "accept"
) -> DocxConversionResult:
    """Convert one DOCX file to markdown via pandoc.

    Args:
        docx_path: Input DOCX path.
        output_dir: Output workspace directory.
        track_changes: Tracked changes mode, one of accept/reject/all.
    """

    normalized_mode = (track_changes or "").strip().lower()
    if normalized_mode not in {"accept", "reject", "all"}:
        raise ValueError("track_changes must be one of: accept, reject, all")

    input_path = Path(docx_path).resolve()
    if not input_path.exists() or not input_path.is_file():
        raise FileNotFoundError(f"DOCX path not found: {docx_path}")

    pandoc_bin = shutil.which("pandoc")
    if not pandoc_bin:
        raise RuntimeError(
            "pandoc is required for DOCX import but was not found in PATH. "
            "Please install pandoc first."
        )

    output_root = Path(output_dir).resolve()
    output_root.mkdir(parents = True, exist_ok = True)
    markdown_path = output_root / "converted.md"
    media_dir = output_root / "media"

    cmd = [
        pandoc_bin,
        "--from",
        "docx",
        "--to",
        "gfm",
        f"--track-changes={normalized_mode}",
        "--extract-media",
        str(media_dir),
        str(input_path),
        "-o",
        str(markdown_path)
    ]
    process = subprocess.run(
        cmd,
        stdout = subprocess.PIPE,
        stderr = subprocess.PIPE,
        text = True,
        check = False
    )

    if process.returncode != 0:
        error_detail = process.stderr.strip() or process.stdout.strip() or "unknown pandoc error"
        raise RuntimeError(f"pandoc conversion failed: {error_detail}")

    if not markdown_path.exists():
        raise RuntimeError("pandoc conversion failed: markdown output was not generated")

    markdown = markdown_path.read_text(encoding = "utf-8", errors = "ignore")
    return DocxConversionResult(
        markdown = markdown,
        markdown_path = str(markdown_path),
        media_dir = str(media_dir)
    )
