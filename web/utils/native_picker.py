"""Native path picker helpers for local desktop Web mode."""

import os

from typing import Sequence


class PickerUnavailableError(RuntimeError):
    """Raised when native path picker cannot be used in current environment."""


class PickerCancelledError(RuntimeError):
    """Raised when user cancels native path selection."""


def pick_local_path(target: str, extensions: Sequence[str] | None = None) -> str:
    """Pick one local directory or markdown/docx file via native system dialog.

    Args:
        target: Picker target, one of "directory" or "file".
        extensions: Optional file extension list without dots.
    """

    normalized_target = (target or "").strip().lower()
    if normalized_target not in {"directory", "file"}:
        raise ValueError("target must be one of: directory, file")

    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:
        raise PickerUnavailableError("native picker is unavailable in current environment") from exc

    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        root.update_idletasks()

        selected_path = ""
        if normalized_target == "directory":
            selected_path = filedialog.askdirectory(
                mustexist = True
            )
        else:
            normalized_extensions = _normalize_extensions(extensions = extensions)
            file_patterns = [f"*.{ext}" for ext in normalized_extensions]
            selected_path = filedialog.askopenfilename(
                filetypes = [
                    ("Document files", " ".join(file_patterns)),
                    ("All files", "*.*")
                ]
            )
    except Exception as exc:
        raise PickerUnavailableError("native picker cannot be opened in current environment") from exc
    finally:
        if root is not None:
            root.destroy()

    if not selected_path:
        raise PickerCancelledError("path selection is cancelled by user")

    return os.path.abspath(selected_path)


def _normalize_extensions(extensions: Sequence[str] | None) -> list[str]:
    """Normalize extension list for file picker usage.

    Args:
        extensions: Optional extension list with or without dot.
    """

    if not extensions:
        return ["md", "markdown", "docx"]

    result = []
    for item in extensions:
        value = str(item).strip().lstrip(".").lower()
        if not value:
            continue
        result.append(value)
    if not result:
        return ["md", "markdown", "docx"]
    return result
