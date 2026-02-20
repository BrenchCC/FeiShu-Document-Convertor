"""Source management API.

Provides local scanning and GitHub clone helpers.
"""

import os
import sys
import json
import uuid
import logging
import tempfile
import posixpath
from typing import List
from typing import Optional

from pydantic import BaseModel
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

sys.path.append(os.getcwd())

from data.source_adapters import LocalSourceAdapter, GitHubSourceAdapter
from web.utils.native_picker import PickerCancelledError, PickerUnavailableError
from web.utils.native_picker import pick_local_path

router = APIRouter()
logger = logging.getLogger(__name__)


class ScanRequest(BaseModel):
    """Local scan request."""
    path: str
    recursive: bool = True
    extensions: List[str] = ["md", "markdown", "docx"]


class ScanResult(BaseModel):
    """Local scan result."""
    total_files: int
    markdown_files: int
    other_files: int
    files: List[str]


class GitHubCloneRequest(BaseModel):
    """GitHub clone request."""
    repo: str
    branch: Optional[str] = None
    commit: Optional[str] = None
    temp_dir: Optional[str] = None


class GitHubCloneResult(BaseModel):
    """GitHub clone result."""
    repo: str
    branch: Optional[str] = None
    commit: Optional[str] = None
    path: str
    files: List[str]


class LocalPickRequest(BaseModel):
    """Local path picker request."""
    target: str = "directory"
    extensions: List[str] = ["md", "markdown", "docx"]


class LocalPickResult(BaseModel):
    """Local path picker result."""
    path: str
    target: str


class LocalUploadResult(BaseModel):
    """Local upload result."""
    path: str
    target: str
    file_count: int


@router.get("/local/scan", response_model = ScanResult)
async def scan_local_directory(
    path: str,
    recursive: bool = True,
    extensions: List[str] = ["md", "markdown", "docx"]
):
    """Scan local directory for supported import files."""
    try:
        logger.info(f"开始扫描本地目录: {path}")

        if not os.path.exists(path):
            raise HTTPException(status_code = 404, detail = "路径不存在")

        if not os.path.isdir(path):
            raise HTTPException(status_code = 400, detail = "路径必须是目录")

        adapter = LocalSourceAdapter(path)
        files = adapter.list_markdown()

        markdown_files = [f for f in files if f.lower().endswith(tuple(extensions))]
        other_files = [f for f in files if f.lower().endswith(tuple(extensions)) is False]

        logger.info(f"扫描完成: {len(markdown_files)}个可导入文件，{len(other_files)}个其他文件")

        return {
            "total_files": len(files),
            "markdown_files": len(markdown_files),
            "other_files": len(other_files),
            "files": files
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"扫描本地目录失败: {str(e)}", exc_info = True)
        raise HTTPException(status_code = 500, detail = f"扫描失败: {str(e)}")


@router.post("/local/upload", response_model = LocalUploadResult)
async def upload_local_source(
    target: str = Form(...),
    entries_json: str = Form("[]"),
    files: List[UploadFile] = File(...)
):
    """Upload browser-selected local files to one server temp path."""
    try:
        normalized_target = (target or "").strip().lower()
        if normalized_target not in {"directory", "file"}:
            raise HTTPException(status_code = 400, detail = "target must be one of: directory, file")
        if not files:
            raise HTTPException(status_code = 400, detail = "请选择至少一个文件")

        entries = json.loads(entries_json or "[]")
        if not isinstance(entries, list):
            raise HTTPException(status_code = 400, detail = "entries_json must be a JSON list")
        if len(entries) != len(files):
            raise HTTPException(status_code = 400, detail = "entries count must match files count")

        temp_root = tempfile.mkdtemp(prefix = f"local_upload_{uuid.uuid4().hex[:8]}_")
        resolved_paths = []

        for index, upload_file in enumerate(files):
            entry = entries[index] if index < len(entries) else {}
            relative_path = _normalize_upload_relative_path(
                raw_path = str(entry.get("relative_path", "")) or upload_file.filename or ""
            )
            if not relative_path:
                raise HTTPException(status_code = 400, detail = "invalid relative path in uploaded files")

            destination_path = os.path.join(temp_root, relative_path)
            os.makedirs(os.path.dirname(destination_path), exist_ok = True)
            content = await upload_file.read()
            with open(destination_path, "wb") as destination:
                destination.write(content)
            resolved_paths.append(destination_path)

        if normalized_target == "file":
            if len(resolved_paths) != 1:
                raise HTTPException(status_code = 400, detail = "单文件导入只能上传一个文件")
            source_path = resolved_paths[0]
        else:
            source_path = temp_root

        logger.info(
            "本地上传成功: target = %s, files = %d, source_path = %s",
            normalized_target,
            len(resolved_paths),
            source_path
        )
        return {
            "path": source_path,
            "target": normalized_target,
            "file_count": len(resolved_paths)
        }
    except HTTPException:
        raise
    except json.JSONDecodeError:
        raise HTTPException(status_code = 400, detail = "entries_json is not valid JSON")
    except Exception as e:
        logger.error(f"本地上传失败: {str(e)}", exc_info = True)
        raise HTTPException(status_code = 500, detail = f"本地上传失败: {str(e)}")


@router.post("/local/pick", response_model = LocalPickResult)
async def pick_local_source_path(request: LocalPickRequest):
    """Pick local directory or file via native picker."""
    try:
        target = request.target.strip().lower()
        selected_path = pick_local_path(
            target = target,
            extensions = request.extensions
        )
        logger.info("本地路径选择成功: target = %s, path = %s", target, selected_path)
        return {
            "path": selected_path,
            "target": target
        }
    except ValueError as e:
        raise HTTPException(status_code = 400, detail = str(e))
    except PickerCancelledError:
        raise HTTPException(status_code = 400, detail = "未选择任何路径")
    except PickerUnavailableError as e:
        raise HTTPException(
            status_code = 409,
            detail = f"当前环境无法打开系统选择器，请手动输入路径: {str(e)}"
        )
    except Exception as e:
        logger.error(f"本地路径选择失败: {str(e)}", exc_info = True)
        raise HTTPException(status_code = 500, detail = f"路径选择失败: {str(e)}")


@router.post("/github/clone", response_model = GitHubCloneResult)
async def clone_github_repo(request: GitHubCloneRequest):
    """Clone a GitHub repository."""
    try:
        logger.info(f"开始克隆GitHub仓库: {request.repo}")

        temp_dir = request.temp_dir
        if not temp_dir:
            temp_dir = tempfile.mkdtemp(prefix = "github_")

        # Create HTTP client
        from utils.http_client import HttpClient
        http_client = HttpClient()

        # Clone via GitHubSourceAdapter
        adapter = GitHubSourceAdapter(
            repo = request.repo,
            ref = request.branch or "main",
            subdir = "",
            http_client = http_client
        )

        # Trigger clone and prepare
        adapter.list_markdown()

        # Resolve repo path
        repo_path = str(adapter._repo_root)

        # Scan cloned repo
        files = []
        for root, _, filenames in os.walk(repo_path):
            for filename in filenames:
                file_path = os.path.relpath(os.path.join(root, filename), repo_path)
                files.append(file_path)

        logger.info(f"克隆完成: {len(files)}个文件")

        return {
            "repo": request.repo,
            "branch": request.branch,
            "commit": request.commit,
            "path": repo_path,
            "files": files
        }

    except Exception as e:
        logger.error(f"克隆GitHub仓库失败: {str(e)}", exc_info = True)
        raise HTTPException(status_code = 500, detail = f"克隆失败: {str(e)}")


@router.post("/github/validate")
async def validate_github_repo(request: dict):
    """Validate GitHub repository access."""
    try:
        repo = request.get("repo")
        logger.info(f"开始验证GitHub仓库: {repo}")

        # Basic validation: owner/repo format
        if not repo or "/" not in repo or len(repo.split("/")) != 2:
            raise HTTPException(status_code = 400, detail = "仓库格式不正确，应为 owner/repo")

        # Try to fetch repo metadata (public access)
        import requests
        url = f"https://github.com/{repo}"
        response = requests.get(url, allow_redirects = True)

        if response.status_code != 200:
            raise HTTPException(status_code = 404, detail = "仓库不存在或无法访问")

        logger.info(f"仓库验证成功: {repo}")
        return {"message": "仓库验证成功"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"验证GitHub仓库失败: {str(e)}", exc_info = True)
        raise HTTPException(status_code = 500, detail = f"验证失败: {str(e)}")


def _normalize_upload_relative_path(raw_path: str) -> str:
    """Normalize uploaded relative file path for safe local write.

    Args:
        raw_path: Browser-provided relative file path.
    """

    value = (raw_path or "").replace("\\", "/").strip().strip("/")
    if not value:
        return ""
    normalized = posixpath.normpath(value)
    if normalized in {"", "."}:
        return ""
    if normalized.startswith("../") or normalized.startswith("/") or "/../" in f"{normalized}/":
        return ""
    return normalized
