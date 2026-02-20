import os
import re
import sys
import logging
import datetime
import posixpath
import dataclasses
import urllib.parse
import multiprocessing
from typing import Any
from typing import Optional
from concurrent.futures import as_completed
from concurrent.futures import ProcessPoolExecutor

sys.path.append(os.getcwd())

from config.config import AppConfig
from core.orchestration_planner import OrchestrationPlanner
from data.models import AssetRef
from data.models import CreatedDocRecord
from data.models import ImportFailure
from data.models import ImportManifest
from data.models import ImportResult
from data.models import SourceDocument
from data.source_adapters import SourceAdapter
from integrations.feishu_api import DocWriterService
from integrations.feishu_api import FeishuAuthClient
from integrations.feishu_api import MediaService
from integrations.feishu_api import WikiService
from utils.http_client import HttpClient
from utils.logging_setup import ensure_worker_log_handler
from utils.markdown_processor import MarkdownProcessor


logger = logging.getLogger(__name__)


class InMemorySourceAdapter(SourceAdapter):
    """In-memory source adapter for worker-side grouped import."""

    def __init__(
        self,
        docs_by_path: dict[str, SourceDocument],
        ordered_paths: list[str]
    ) -> None:
        self.docs_by_path = docs_by_path
        self.ordered_paths = ordered_paths

    def list_markdown(self) -> list[str]:
        """List markdown paths preserving given order.

        Args:
            self: Adapter instance.
        """

        return list(self.ordered_paths)

    def read_markdown(self, relative_path: str) -> SourceDocument:
        """Read one markdown document from memory map.

        Args:
            self: Adapter instance.
            relative_path: Source-relative markdown path.
        """

        if relative_path not in self.docs_by_path:
            raise FileNotFoundError(f"Missing in-memory markdown path: {relative_path}")
        doc = self.docs_by_path[relative_path]
        return SourceDocument(
            path = doc.path,
            title = doc.title,
            markdown = doc.markdown,
            assets = list(doc.assets),
            relative_dir = doc.relative_dir,
            base_ref = doc.base_ref,
            source_type = doc.source_type
        )


def _process_group_worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Process one top-level folder group in a subprocess.

    Args:
        payload: Serializable worker payload.
    """

    ensure_worker_log_handler()

    group_key = str(payload.get("group_key", "__unknown__"))
    config = AppConfig(**payload["config"])
    docs_by_path: dict[str, SourceDocument] = {}
    for raw_doc in payload.get("docs", []):
        path = str(raw_doc.get("path", "")).strip()
        if not path:
            continue
        docs_by_path[path] = SourceDocument(
            path = path,
            title = str(raw_doc.get("title", "")).strip() or posixpath.basename(path),
            markdown = str(raw_doc.get("markdown", "")),
            assets = [],
            relative_dir = str(raw_doc.get("relative_dir", "")).strip(),
            base_ref = str(raw_doc.get("base_ref", "")).strip(),
            source_type = str(raw_doc.get("source_type", "")).strip() or "local"
        )

    ordered_paths = [path for path in payload.get("ordered_paths", []) if path in docs_by_path]
    logger.info(
        "worker group start: key = %s, docs = %d",
        group_key,
        len(ordered_paths)
    )
    source_adapter = InMemorySourceAdapter(
        docs_by_path = docs_by_path,
        ordered_paths = ordered_paths
    )
    markdown_processor = MarkdownProcessor()

    http_client = HttpClient(
        timeout = config.request_timeout,
        max_retries = config.max_retries,
        retry_backoff = config.retry_backoff
    )
    app_auth = FeishuAuthClient(
        app_id = config.feishu_app_id,
        app_secret = config.feishu_app_secret,
        base_url = config.feishu_base_url,
        http_client = http_client
    )
    doc_writer = DocWriterService(
        auth_client = app_auth,
        http_client = http_client,
        base_url = config.feishu_base_url,
        folder_token = config.feishu_folder_token if payload.get("write_mode") in {"folder", "both"} else "",
        convert_max_bytes = config.feishu_convert_max_bytes,
        chunk_workers = int(payload.get("chunk_workers", 2))
    )
    media_service = MediaService(
        auth_client = app_auth,
        http_client = http_client,
        base_url = config.feishu_base_url
    )

    wiki_service = None
    if payload.get("write_mode") in {"wiki", "both"}:
        wiki_service = WikiService(
            auth_client = app_auth,
            http_client = http_client,
            base_url = config.feishu_base_url,
            user_access_token = config.feishu_user_access_token
        )

    orchestrator = ImportOrchestrator(
        source_adapter = source_adapter,
        markdown_processor = markdown_processor,
        config = config,
        doc_writer = doc_writer,
        media_service = media_service,
        wiki_service = wiki_service,
        notify_service = None,
        llm_client = None
    )

    success = 0
    failures: list[dict[str, str]] = []
    created_docs: list[dict[str, str]] = []
    folder_token_by_path = payload.get("folder_token_by_path", {})
    wiki_parent_by_path = payload.get("wiki_parent_by_path", {})
    write_mode = str(payload.get("write_mode", "folder"))
    space_id = str(payload.get("space_id", ""))

    for index, path in enumerate(ordered_paths, start = 1):
        try:
            logger.info(
                "worker processing: group = %s, progress = %d/%d, path = %s",
                group_key,
                index,
                len(ordered_paths),
                path
            )
            doc = source_adapter.read_markdown(relative_path = path)
            processed = markdown_processor.extract_assets_and_math(
                md_text = doc.markdown,
                base_path_or_url = doc.base_ref
            )
            doc.assets = processed.assets
            target_folder_token = str(folder_token_by_path.get(path, ""))
            document_id, resolved_title, doc_url = orchestrator._create_doc_with_title_strategy(
                doc = doc,
                folder_token = target_folder_token
            )
            asset_lookup = orchestrator._build_asset_lookup(assets = doc.assets)

            def _image_block_handler(image_url: str, block_id: str) -> None:
                asset = orchestrator._find_asset_by_image_url(
                    image_url = image_url,
                    asset_lookup = asset_lookup
                )
                if not asset:
                    return
                file_token = media_service.upload_to_node(
                    asset = asset,
                    parent_node = block_id
                )
                doc_writer.replace_image(
                    document_id = document_id,
                    block_id = block_id,
                    file_token = file_token
                )

            doc_writer.write_markdown_with_fallback(
                document_id = document_id,
                content = processed.markdown,
                image_block_handler = _image_block_handler
            )

            wiki_node_token = ""
            if write_mode in {"wiki", "both"} and wiki_service is not None:
                parent_node_token = str(wiki_parent_by_path.get(path, ""))
                wiki_node_token = wiki_service.move_doc_to_wiki(
                    space_id = space_id,
                    document_id = document_id,
                    parent_node_token = parent_node_token,
                    title = resolved_title
                )

            created_docs.append(
                {
                    "path": doc.path,
                    "title": resolved_title,
                    "document_id": document_id,
                    "doc_url": doc_url,
                    "wiki_node_token": wiki_node_token
                }
            )
            success += 1
            logger.info(
                "worker done: group = %s, progress = %d/%d, path = %s, document_id = %s",
                group_key,
                index,
                len(ordered_paths),
                path,
                document_id
            )
        except Exception as exc:
            logger.warning(
                "worker failed: group = %s, progress = %d/%d, path = %s, err = %s",
                group_key,
                index,
                len(ordered_paths),
                path,
                str(exc)
            )
            failures.append(
                {
                    "path": path,
                    "reason": str(exc)
                }
            )

    logger.info(
        "worker group finish: key = %s, success = %d, failed = %d",
        group_key,
        success,
        len(failures)
    )
    return {
        "success": success,
        "failures": failures,
        "created_docs": created_docs
    }


class ImportOrchestrator:
    """End-to-end orchestrator for markdown to Feishu import.

    Args:
        source_adapter: Source adapter implementation.
        markdown_processor: Markdown parser and replacement helper.
        config: Runtime config values.
        doc_writer: Feishu doc writer service.
        media_service: Feishu media upload service.
        wiki_service: Feishu wiki service.
        notify_service: Feishu notification service.
    """

    def __init__(
        self,
        source_adapter: SourceAdapter,
        markdown_processor: MarkdownProcessor,
        config: AppConfig,
        doc_writer: Optional[DocWriterService] = None,
        media_service: Optional[MediaService] = None,
        wiki_service: Optional[WikiService] = None,
        notify_service: Optional[object] = None,
        llm_client: Optional[object] = None
    ) -> None:
        self.source_adapter = source_adapter
        self.markdown_processor = markdown_processor
        self.config = config

        self.doc_writer = doc_writer
        self.media_service = media_service
        self.wiki_service = wiki_service
        self.notify_service = notify_service
        self.llm_client = llm_client

        self._title_max_bytes = 180
        self._title_invalid_chars_pattern = re.compile(r"[\\/:*?\"<>|]+")
        self._control_chars_pattern = re.compile(r"[\x00-\x1f\x7f]+")

    def run(
        self,
        space_name: str,
        space_id: str,
        chat_id: str,
        dry_run: bool,
        notify_level: str,
        write_mode: str,
        folder_subdirs: bool = False,
        folder_root_subdir: bool = True,
        folder_root_subdir_name: str = "",
        structure_order: str = "toc_first",
        toc_file: str = "TABLE_OF_CONTENTS.md",
        folder_nav_doc: bool = True,
        folder_nav_title: str = "00-导航总目录",
        llm_fallback: str = "toc_ambiguity",
        llm_max_calls: int = 3,
        skip_root_readme: bool = False,
        max_workers: int = 1,
        chunk_workers: int = 2
    ) -> ImportResult:
        """Run import pipeline.

        Args:
            space_name: Destination wiki space name.
            space_id: Existing destination wiki space id.
            chat_id: Group chat id used by notification bot.
            dry_run: Whether to skip Feishu write operations.
            notify_level: Notification verbosity level.
            write_mode: Write mode, one of folder/wiki/both.
            folder_subdirs: Whether to auto-create folder hierarchy in folder mode.
            folder_root_subdir: Whether to create one task root subfolder first.
            folder_root_subdir_name: Optional task root subfolder name.
            structure_order: Ordering strategy, one of toc_first/path.
            toc_file: TOC markdown path relative to source root.
            folder_nav_doc: Whether to write folder navigation document.
            folder_nav_title: Folder navigation document title.
            llm_fallback: LLM fallback strategy for TOC ambiguity.
            llm_max_calls: Maximum number of LLM calls in one run.
            skip_root_readme: Whether to skip only root README.md/readme.md.
            max_workers: Process worker count for grouped import.
            chunk_workers: Thread worker count for per-document chunk planning.
        """

        paths = self.source_adapter.list_markdown()
        manifest = self._build_manifest(
            paths = paths,
            structure_order = structure_order,
            toc_file = toc_file,
            llm_fallback = llm_fallback,
            llm_max_calls = llm_max_calls,
            skip_root_readme = skip_root_readme
        )
        result = ImportResult(total = len(manifest.items))
        if manifest.skipped_items:
            result.skipped_items.extend(manifest.skipped_items)
        result.skipped = len(result.skipped_items)

        logger.info("=" * 80)
        logger.info("Import task started")
        logger.info("=" * 80)
        logger.info("Discovered markdown files: %d", len(paths))
        logger.info(
            (
                "orchestration summary: strategy = %s, toc_links = %d, matched = %d, "
                "ambiguous = %d, llm_used = %s, llm_calls = %d, fallback = %d"
            ),
            structure_order,
            manifest.toc_links,
            manifest.matched_links,
            manifest.ambiguous_links,
            str(manifest.llm_used),
            manifest.llm_calls,
            manifest.fallback_count
        )
        self._log_robot_push(
            stage = "start",
            detail = (
                f"source_files = {len(paths)}, planned_files = {len(manifest.items)}, "
                f"mode = {write_mode}, strategy = {structure_order}"
            )
        )
        if manifest.unresolved_links:
            logger.warning("unresolved toc links: %d", len(manifest.unresolved_links))
            for unresolved in manifest.unresolved_links[:20]:
                logger.warning("toc unresolved: %s", unresolved)
        if manifest.skipped_items:
            logger.info("manifest skipped items: %d", len(manifest.skipped_items))
            for skipped in manifest.skipped_items[:20]:
                logger.info("manifest skipped: path = %s, reason = %s", skipped.path, skipped.reason)

        self._notify(
            chat_id = chat_id,
            level = notify_level,
            message = (
                f"知识导入任务开始：source_files = {len(paths)}, "
                f"space = {space_name or space_id}, mode = {write_mode}, dry_run = {dry_run}"
            ),
            force = True
        )

        if not dry_run:
            self._assert_services_ready(write_mode = write_mode)
            if hasattr(self.doc_writer, "chunk_workers"):
                self.doc_writer.chunk_workers = max(1, int(chunk_workers))
            if write_mode in {"wiki", "both"}:
                if space_id:
                    logger.info("Reuse existing wiki space_id = %s", space_id)
                else:
                    space_id = self.wiki_service.get_or_create_space(space_name = space_name)
            else:
                space_id = ""
        else:
            space_id = "dry-run"

        created_docs: list[CreatedDocRecord] = []
        folder_root_token = ""
        folder_root_relative_dir = ""
        if (
            not dry_run
            and write_mode in {"folder", "both"}
            and folder_root_subdir
        ):
            folder_root_relative_dir = self._resolve_folder_root_subdir_name(
                explicit_name = folder_root_subdir_name
            )
            folder_root_token = self.doc_writer.ensure_folder_path(
                relative_dir = folder_root_relative_dir
            )
            self._log_robot_push(
                stage = "folder_root_ready",
                detail = (
                    f"name = {folder_root_relative_dir}, folder_token = {folder_root_token}"
                )
            )
            logger.info(
                "folder root ready: name = %s, token = %s",
                folder_root_relative_dir,
                folder_root_token
            )

        if max_workers > 1 and not dry_run and manifest.items:
            parallel_outcome = self._run_grouped_multiprocess_import(
                manifest = manifest,
                write_mode = write_mode,
                space_id = space_id,
                folder_subdirs = folder_subdirs,
                folder_root_relative_dir = folder_root_relative_dir,
                folder_root_token = folder_root_token,
                max_workers = max_workers,
                chunk_workers = chunk_workers,
                chat_id = chat_id,
                notify_level = notify_level
            )
            created_docs.extend(parallel_outcome["created_docs"])
            result.success += parallel_outcome["success"]
            result.failures.extend(parallel_outcome["failures"])
        else:
            for index, plan_item in enumerate(manifest.items, start = 1):
                path = plan_item.path
                try:
                    doc = self.source_adapter.read_markdown(relative_path = path)
                    processed = self.markdown_processor.extract_assets_and_math(
                        md_text = doc.markdown,
                        base_path_or_url = doc.base_ref
                    )
                    doc.assets = processed.assets

                    logger.info("-" * 60)
                    logger.info("[%d/%d] Processing: %s", index, len(manifest.items), doc.path)
                    logger.info("assets = %d, formulas = %d", len(doc.assets), processed.formula_count)
                    logger.info("-" * 60)

                    self._notify(
                        chat_id = chat_id,
                        level = notify_level,
                        message = f"正在写入：{doc.path} ({index}/{len(manifest.items)})",
                        force = notify_level == "normal"
                    )
                    self._log_robot_push(
                        stage = "processing",
                        detail = f"path = {doc.path}, progress = {index}/{len(manifest.items)}"
                    )

                    if dry_run:
                        result.success += 1
                        continue

                    target_folder_token = folder_root_token
                    if write_mode in {"folder", "both"} and folder_subdirs:
                        effective_relative_dir = doc.relative_dir
                        if folder_root_relative_dir:
                            if effective_relative_dir:
                                effective_relative_dir = (
                                    f"{folder_root_relative_dir}/{effective_relative_dir}"
                                )
                            else:
                                effective_relative_dir = folder_root_relative_dir
                        target_folder_token = self.doc_writer.ensure_folder_path(
                            relative_dir = effective_relative_dir
                        )

                    document_id, resolved_title, doc_url = self._create_doc_with_title_strategy(
                        doc = doc,
                        folder_token = target_folder_token
                    )
                    logger.info(
                        "created document_id = %s, title = %s, folder_token = %s, url = %s",
                        document_id,
                        resolved_title,
                        target_folder_token or getattr(self.doc_writer, "folder_token", ""),
                        doc_url
                    )
                    self._log_robot_push(
                        stage = "doc_created",
                        detail = (
                            f"path = {doc.path}, title = {resolved_title}, document_id = {document_id}, "
                            f"folder_token = {target_folder_token or getattr(self.doc_writer, 'folder_token', '')}"
                        )
                    )
                    asset_lookup = self._build_asset_lookup(assets = doc.assets)

                    def _image_block_handler(image_url: str, block_id: str) -> None:
                        asset = self._find_asset_by_image_url(
                            image_url = image_url,
                            asset_lookup = asset_lookup
                        )
                        if not asset:
                            logger.warning(
                                "No local asset mapping for image url = %s in document = %s",
                                image_url,
                                doc.path
                            )
                            return

                        file_token = self.media_service.upload_to_node(
                            asset = asset,
                            parent_node = block_id
                        )
                        self.doc_writer.replace_image(
                            document_id = document_id,
                            block_id = block_id,
                            file_token = file_token
                        )

                    self.doc_writer.write_markdown_with_fallback(
                        document_id = document_id,
                        content = processed.markdown,
                        image_block_handler = _image_block_handler
                    )

                    wiki_node_token = ""
                    if write_mode in {"wiki", "both"}:
                        parent_node_token = self.wiki_service.ensure_path_nodes(
                            space_id = space_id,
                            relative_dir = doc.relative_dir
                        )
                        wiki_node_token = self.wiki_service.move_doc_to_wiki(
                            space_id = space_id,
                            document_id = document_id,
                            parent_node_token = parent_node_token,
                            title = resolved_title
                        )
                        self._log_robot_push(
                            stage = "wiki_moved",
                            detail = (
                                f"path = {doc.path}, document_id = {document_id}, "
                                f"wiki_node_token = {wiki_node_token}"
                            )
                        )

                    created_docs.append(
                        CreatedDocRecord(
                            path = doc.path,
                            title = resolved_title,
                            document_id = document_id,
                            doc_url = doc_url,
                            wiki_node_token = wiki_node_token
                        )
                    )

                    result.success += 1
                    self._notify(
                        chat_id = chat_id,
                        level = notify_level,
                        message = f"写入完成：{doc.path}",
                        force = notify_level == "normal"
                    )
                except Exception as exc:
                    logger.exception("Failed to process %s", path)
                    self._log_robot_push(
                        stage = "failed",
                        detail = f"path = {path}, error = {str(exc)[:240]}"
                    )
                    result.failures.append(
                        ImportFailure(
                            path = path,
                            reason = str(exc)
                        )
                    )
                    self._notify(
                        chat_id = chat_id,
                        level = notify_level,
                        message = f"写入失败：{path}，原因：{str(exc)[:300]}",
                        force = True
                    )

        order_map = {item.path: index for index, item in enumerate(manifest.items)}
        created_docs = sorted(
            created_docs,
            key = lambda item: order_map.get(item.path, 10 ** 9)
        )
        result.created_docs = list(created_docs)
        result.failed = len(result.failures)
        result.skipped = len(result.skipped_items)

        if (
            not dry_run
            and folder_nav_doc
            and write_mode in {"folder", "both"}
            and created_docs
        ):
            if folder_subdirs:
                nav_created = self._write_folder_navigation_doc_with_llm(
                    folder_nav_title = folder_nav_title,
                    manifest = manifest,
                    created_docs = created_docs,
                    folder_token = folder_root_token,
                    source_paths = paths,
                    toc_file = toc_file
                )
                if not nav_created:
                    logger.warning(
                        "Skip folder navigation doc: LLM generation unavailable or invalid output"
                    )
            else:
                self._write_folder_navigation_doc(
                    folder_nav_title = folder_nav_title,
                    manifest = manifest,
                    created_docs = created_docs,
                    folder_token = folder_root_token
                )

        logger.info("*" * 50)
        logger.info(
            "Import finished: total = %d, success = %d, failed = %d, skipped = %d",
            result.total,
            result.success,
            result.failed,
            result.skipped
        )
        logger.info("*" * 50)
        self._log_robot_push(
            stage = "finished",
            detail = (
                f"total = {result.total}, success = {result.success}, failed = {result.failed}, "
                f"skipped = {result.skipped}, llm_calls = {manifest.llm_calls}, "
                f"unresolved = {len(manifest.unresolved_links)}"
            )
        )

        summary_lines = [
            "知识导入任务完成",
            f"total = {result.total}",
            f"success = {result.success}",
            f"failed = {result.failed}",
            f"skipped = {result.skipped}",
            (
                "编排统计："
                f"toc_links = {manifest.toc_links}, "
                f"matched = {manifest.matched_links}, "
                f"ambiguous = {manifest.ambiguous_links}, "
                f"llm_calls = {manifest.llm_calls}, "
                f"fallback = {manifest.fallback_count}"
            )
        ]
        if manifest.unresolved_links:
            summary_lines.append("TOC 歧义/未匹配：")
            for unresolved in manifest.unresolved_links[:20]:
                summary_lines.append(f"- {unresolved}")
        if result.failures:
            summary_lines.append("失败清单：")
            for failure in result.failures[:20]:
                summary_lines.append(f"- {failure.path}: {failure.reason[:120]}")
        if result.skipped_items:
            summary_lines.append("跳过清单：")
            for skipped in result.skipped_items[:20]:
                summary_lines.append(f"- {skipped.path}: {skipped.reason[:120]}")

        self._notify(
            chat_id = chat_id,
            level = notify_level,
            message = "\n".join(summary_lines),
            force = True
        )

        return result

    def _build_manifest(
        self,
        paths: list[str],
        structure_order: str,
        toc_file: str,
        llm_fallback: str,
        llm_max_calls: int,
        skip_root_readme: bool
    ) -> ImportManifest:
        """Build import manifest with optional TOC-aware ordering.

        Args:
            paths: Source markdown paths.
            structure_order: Ordering strategy.
            toc_file: TOC file path.
            llm_fallback: LLM fallback strategy.
            llm_max_calls: LLM call cap.
            skip_root_readme: Whether to skip root README markdown file.
        """

        planner = OrchestrationPlanner(
            source_adapter = self.source_adapter,
            llm_resolver = self.llm_client if llm_fallback == "toc_ambiguity" else None,
            skip_root_readme = skip_root_readme
        )
        manifest = planner.build_manifest(
            markdown_paths = paths,
            structure_order = structure_order,
            toc_file = toc_file,
            llm_fallback = llm_fallback,
            llm_max_calls = llm_max_calls
        )
        return manifest

    def _run_grouped_multiprocess_import(
        self,
        manifest: ImportManifest,
        write_mode: str,
        space_id: str,
        folder_subdirs: bool,
        folder_root_relative_dir: str,
        folder_root_token: str,
        max_workers: int,
        chunk_workers: int,
        chat_id: str,
        notify_level: str
    ) -> dict[str, Any]:
        """Run grouped multiprocessing import by top-level folder key.

        Args:
            manifest: Ordered import manifest.
            write_mode: Write mode, one of folder/wiki/both.
            space_id: Resolved wiki space id.
            folder_subdirs: Whether folder hierarchy mode is enabled.
            folder_root_relative_dir: Optional task root folder name.
            folder_root_token: Optional task root folder token.
            max_workers: Process pool size.
            chunk_workers: Per-document chunk planning thread count.
            chat_id: Notification target chat id.
            notify_level: Notification verbosity.
        """

        logger.info(
            "grouped import start: workers = %d, chunk_workers = %d, planned_docs = %d",
            max_workers,
            chunk_workers,
            len(manifest.items)
        )
        self._log_robot_push(
            stage = "grouped_start",
            detail = (
                f"workers = {max_workers}, chunk_workers = {chunk_workers}, "
                f"planned_docs = {len(manifest.items)}"
            )
        )
        self._notify(
            chat_id = chat_id,
            level = notify_level,
            message = (
                f"并发导入启动：workers = {max_workers}，chunk_workers = {chunk_workers}，"
                f"planned_docs = {len(manifest.items)}"
            ),
            force = notify_level == "normal"
        )

        snapshots, snapshot_failures = self._build_doc_snapshots(manifest = manifest)
        usable_items = [item for item in manifest.items if item.path in snapshots]
        logger.info(
            "grouped snapshot ready: loaded = %d, failed = %d",
            len(usable_items),
            len(snapshot_failures)
        )
        self._log_robot_push(
            stage = "grouped_snapshot_ready",
            detail = f"loaded = {len(usable_items)}, failed = {len(snapshot_failures)}"
        )
        if not usable_items:
            return {
                "success": 0,
                "failures": snapshot_failures,
                "created_docs": []
            }

        folder_token_by_path = self._build_folder_token_by_path(
            items = usable_items,
            snapshots = snapshots,
            write_mode = write_mode,
            folder_subdirs = folder_subdirs,
            folder_root_relative_dir = folder_root_relative_dir,
            folder_root_token = folder_root_token
        )
        wiki_parent_by_path = self._build_wiki_parent_by_path(
            items = usable_items,
            snapshots = snapshots,
            write_mode = write_mode,
            space_id = space_id
        )

        grouped = self._group_items_by_top_dir(items = usable_items)
        payloads = []
        group_doc_counts: dict[str, int] = {}
        config_payload = dataclasses.asdict(self.config)
        for group_key, group_items in grouped:
            ordered_paths = [item.path for item in group_items]
            group_doc_counts[group_key] = len(ordered_paths)
            logger.info(
                "group dispatch prepared: key = %s, docs = %d",
                group_key,
                len(ordered_paths)
            )
            docs_payload = []
            for path in ordered_paths:
                doc = snapshots[path]
                docs_payload.append(
                    {
                        "path": doc.path,
                        "title": doc.title,
                        "markdown": doc.markdown,
                        "relative_dir": doc.relative_dir,
                        "base_ref": doc.base_ref,
                        "source_type": doc.source_type
                    }
                )
            payloads.append(
                {
                    "group_key": group_key,
                    "config": config_payload,
                    "docs": docs_payload,
                    "ordered_paths": ordered_paths,
                    "write_mode": write_mode,
                    "space_id": space_id,
                    "folder_token_by_path": {
                        path: folder_token_by_path.get(path, "")
                        for path in ordered_paths
                    },
                    "wiki_parent_by_path": {
                        path: wiki_parent_by_path.get(path, "")
                        for path in ordered_paths
                    },
                    "chunk_workers": max(1, int(chunk_workers))
                }
            )

        successes = 0
        failures: list[ImportFailure] = list(snapshot_failures)
        created_docs: list[CreatedDocRecord] = []
        future_group_map = {}
        total_groups = len(payloads)
        finished_groups = 0
        total_docs = len(usable_items)
        finished_docs = 0

        logger.info(
            "grouped dispatch start: groups = %d, docs = %d, workers = %d",
            total_groups,
            total_docs,
            max_workers
        )
        self._log_robot_push(
            stage = "grouped_dispatch_start",
            detail = f"groups = {total_groups}, docs = {total_docs}, workers = {max_workers}"
        )

        executor = ProcessPoolExecutor(
            max_workers = max_workers,
            mp_context = multiprocessing.get_context("spawn")
        )
        try:
            for payload in payloads:
                future = executor.submit(_process_group_worker, payload)
                future_group_map[future] = payload["group_key"]
                logger.info(
                    "group submitted: key = %s, docs = %d",
                    payload["group_key"],
                    len(payload.get("ordered_paths", []))
                )
                self._log_robot_push(
                    stage = "group_submitted",
                    detail = (
                        f"group = {payload['group_key']}, docs = {len(payload.get('ordered_paths', []))}"
                    )
                )
                self._notify(
                    chat_id = chat_id,
                    level = notify_level,
                    message = (
                        f"分组已提交：{payload['group_key']}，"
                        f"docs = {len(payload.get('ordered_paths', []))}"
                    ),
                    force = notify_level == "normal"
                )

            for future in as_completed(future_group_map):
                group_key = str(future_group_map[future])
                group_doc_total = int(group_doc_counts.get(group_key, 0))
                try:
                    worker_result = future.result()
                except Exception as exc:
                    finished_groups += 1
                    finished_docs += group_doc_total
                    logger.exception(
                        "group failed: key = %s, docs = %d, progress = %d/%d groups, %d/%d docs",
                        group_key,
                        group_doc_total,
                        finished_groups,
                        total_groups,
                        finished_docs,
                        total_docs
                    )
                    self._log_robot_push(
                        stage = "group_failed",
                        detail = (
                            f"group = {group_key}, docs = {group_doc_total}, error = {str(exc)[:240]}, "
                            f"group_progress = {finished_groups}/{total_groups}, "
                            f"doc_progress = {finished_docs}/{total_docs}"
                        )
                    )
                    self._notify(
                        chat_id = chat_id,
                        level = notify_level,
                        message = (
                            f"分组失败：{group_key}，docs = {group_doc_total}，error = {str(exc)[:180]}，"
                            f"进度：groups {finished_groups}/{total_groups}，docs {finished_docs}/{total_docs}"
                        ),
                        force = True
                    )
                    failures.append(
                        ImportFailure(
                            path = f"group:{group_key}",
                            reason = str(exc)
                        )
                    )
                    continue

                group_success = int(worker_result.get("success", 0))
                group_failures = worker_result.get("failures", [])
                finished_groups += 1
                finished_docs += max(group_doc_total, group_success + len(group_failures))
                successes += group_success

                logger.info(
                    (
                        "group finished: key = %s, success = %d, failed = %d, "
                        "progress = %d/%d groups, %d/%d docs"
                    ),
                    group_key,
                    group_success,
                    len(group_failures),
                    finished_groups,
                    total_groups,
                    finished_docs,
                    total_docs
                )
                self._log_robot_push(
                    stage = "group_finished",
                    detail = (
                        f"group = {group_key}, success = {group_success}, failed = {len(group_failures)}, "
                        f"group_progress = {finished_groups}/{total_groups}, "
                        f"doc_progress = {finished_docs}/{total_docs}"
                    )
                )
                self._notify(
                    chat_id = chat_id,
                    level = notify_level,
                    message = (
                        f"分组完成：{group_key}，success = {group_success}，failed = {len(group_failures)}，"
                        f"进度：groups {finished_groups}/{total_groups}，docs {finished_docs}/{total_docs}"
                    ),
                    force = notify_level == "normal"
                )

                for raw_failure in worker_result.get("failures", []):
                    failure_path = str(raw_failure.get("path", ""))
                    failure_reason = str(raw_failure.get("reason", ""))
                    logger.warning(
                        "group doc failed: group = %s, path = %s, error = %s",
                        group_key,
                        failure_path,
                        failure_reason
                    )
                    self._log_robot_push(
                        stage = "failed",
                        detail = f"path = {failure_path}, error = {failure_reason[:240]}"
                    )
                    self._notify(
                        chat_id = chat_id,
                        level = notify_level,
                        message = f"写入失败：{failure_path}，原因：{failure_reason[:300]}",
                        force = True
                    )
                    failures.append(
                        ImportFailure(
                            path = failure_path,
                            reason = failure_reason
                        )
                    )
                for raw_created in worker_result.get("created_docs", []):
                    created_path = str(raw_created.get("path", ""))
                    created_document_id = str(raw_created.get("document_id", ""))
                    logger.info(
                        "group doc created: group = %s, path = %s, document_id = %s",
                        group_key,
                        created_path,
                        created_document_id
                    )
                    self._log_robot_push(
                        stage = "doc_created",
                        detail = (
                            f"path = {created_path}, document_id = {created_document_id}, "
                            f"group = {group_key}"
                        )
                    )
                    self._notify(
                        chat_id = chat_id,
                        level = notify_level,
                        message = f"写入完成：{created_path}",
                        force = notify_level == "normal"
                    )
                    created_docs.append(
                        CreatedDocRecord(
                            path = created_path,
                            title = str(raw_created.get("title", "")),
                            document_id = created_document_id,
                            doc_url = str(raw_created.get("doc_url", "")),
                            wiki_node_token = str(raw_created.get("wiki_node_token", ""))
                        )
                    )
        except KeyboardInterrupt:
            self._terminate_process_pool(executor = executor)
            raise
        finally:
            try:
                executor.shutdown(wait = False, cancel_futures = True)
            except Exception:
                pass

        logger.info(
            "grouped import finished: success = %d, failed = %d",
            successes,
            len(failures)
        )
        self._log_robot_push(
            stage = "grouped_finished",
            detail = f"success = {successes}, failed = {len(failures)}"
        )

        return {
            "success": successes,
            "failures": failures,
            "created_docs": created_docs
        }

    def _build_doc_snapshots(
        self,
        manifest: ImportManifest
    ) -> tuple[dict[str, SourceDocument], list[ImportFailure]]:
        """Read markdown docs into serializable snapshot map.

        Args:
            manifest: Ordered import manifest.
        """

        snapshots: dict[str, SourceDocument] = {}
        failures: list[ImportFailure] = []
        for item in manifest.items:
            try:
                doc = self.source_adapter.read_markdown(relative_path = item.path)
                snapshots[item.path] = SourceDocument(
                    path = doc.path,
                    title = doc.title,
                    markdown = doc.markdown,
                    assets = [],
                    relative_dir = doc.relative_dir,
                    base_ref = doc.base_ref,
                    source_type = doc.source_type
                )
            except Exception as exc:
                failures.append(
                    ImportFailure(
                        path = item.path,
                        reason = str(exc)
                    )
                )
        return snapshots, failures

    def _build_folder_token_by_path(
        self,
        items: list,
        snapshots: dict[str, SourceDocument],
        write_mode: str,
        folder_subdirs: bool,
        folder_root_relative_dir: str,
        folder_root_token: str
    ) -> dict[str, str]:
        """Build destination folder token map for each document path.

        Args:
            items: Manifest items.
            snapshots: Path-to-document snapshot map.
            write_mode: Write mode.
            folder_subdirs: Whether to build hierarchy by source dirs.
            folder_root_relative_dir: Optional task root folder path.
            folder_root_token: Optional task root folder token.
        """

        result: dict[str, str] = {}
        if write_mode not in {"folder", "both"}:
            return result

        relative_dir_cache: dict[str, str] = {}
        for item in items:
            path = item.path
            doc = snapshots.get(path)
            if not doc:
                continue

            target_folder_token = folder_root_token
            if folder_subdirs:
                effective_relative_dir = doc.relative_dir
                if folder_root_relative_dir:
                    if effective_relative_dir:
                        effective_relative_dir = (
                            f"{folder_root_relative_dir}/{effective_relative_dir}"
                        )
                    else:
                        effective_relative_dir = folder_root_relative_dir
                if effective_relative_dir not in relative_dir_cache:
                    relative_dir_cache[effective_relative_dir] = self.doc_writer.ensure_folder_path(
                        relative_dir = effective_relative_dir
                    )
                target_folder_token = relative_dir_cache[effective_relative_dir]
            result[path] = target_folder_token

        if folder_subdirs:
            logger.info(
                "folder token map ready: docs = %d, unique_dirs = %d",
                len(result),
                len(relative_dir_cache)
            )
        return result

    def _build_wiki_parent_by_path(
        self,
        items: list,
        snapshots: dict[str, SourceDocument],
        write_mode: str,
        space_id: str
    ) -> dict[str, str]:
        """Build wiki parent node token map for each document path.

        Args:
            items: Manifest items.
            snapshots: Path-to-document snapshot map.
            write_mode: Write mode.
            space_id: Wiki space id.
        """

        result: dict[str, str] = {}
        if write_mode not in {"wiki", "both"} or not self.wiki_service:
            return result

        relative_dir_cache: dict[str, str] = {}
        for item in items:
            path = item.path
            doc = snapshots.get(path)
            if not doc:
                continue

            relative_dir = doc.relative_dir
            if relative_dir not in relative_dir_cache:
                relative_dir_cache[relative_dir] = self.wiki_service.ensure_path_nodes(
                    space_id = space_id,
                    relative_dir = relative_dir
                )
            result[path] = relative_dir_cache[relative_dir]

        logger.info(
            "wiki parent map ready: docs = %d, unique_dirs = %d",
            len(result),
            len(relative_dir_cache)
        )
        return result

    def _group_items_by_top_dir(self, items: list) -> list[tuple[str, list]]:
        """Group manifest items by first source subdirectory segment.

        Args:
            items: Manifest items.
        """

        grouped: dict[str, list] = {}
        order: list[str] = []
        for item in items:
            group_key = self._top_dir_group_key(relative_dir = getattr(item, "relative_dir", ""))
            if group_key not in grouped:
                grouped[group_key] = []
                order.append(group_key)
            grouped[group_key].append(item)
        return [(group_key, grouped[group_key]) for group_key in order]

    def _top_dir_group_key(self, relative_dir: str) -> str:
        """Return top-level directory grouping key for one relative dir.

        Args:
            relative_dir: Source relative directory.
        """

        normalized = (relative_dir or "").strip().replace("\\", "/").strip("/")
        if not normalized:
            return "__root__"
        return normalized.split("/", 1)[0]

    def _terminate_process_pool(self, executor: ProcessPoolExecutor) -> None:
        """Terminate all process pool workers immediately.

        Args:
            executor: Process pool executor.
        """

        try:
            processes = list((getattr(executor, "_processes", {}) or {}).values())
        except Exception:
            processes = []

        for process in processes:
            try:
                if process.is_alive():
                    process.terminate()
            except Exception:
                continue

        for process in processes:
            try:
                process.join(timeout = 0.2)
            except Exception:
                continue

        for process in processes:
            try:
                if process.is_alive() and hasattr(process, "kill"):
                    process.kill()
            except Exception:
                continue

        try:
            executor.shutdown(wait = False, cancel_futures = True)
        except Exception:
            pass

    def _write_folder_navigation_doc_with_llm(
        self,
        folder_nav_title: str,
        manifest: ImportManifest,
        created_docs: list[CreatedDocRecord],
        folder_token: str,
        source_paths: list[str],
        toc_file: str
    ) -> bool:
        """Generate and write folder navigation doc by LLM output.

        Args:
            folder_nav_title: Navigation document title.
            manifest: Import manifest.
            created_docs: Created docs.
            folder_token: Destination folder token.
            source_paths: Source markdown paths from adapter.
            toc_file: TOC filename.
        """

        if not self.llm_client:
            return False

        llm_generate = getattr(self.llm_client, "generate_folder_nav_markdown", None)
        if not callable(llm_generate):
            return False

        record_by_path = {item.path: item for item in created_docs}
        llm_documents = []
        for item in manifest.items:
            record = record_by_path.get(item.path)
            if not record:
                continue
            llm_documents.append(
                {
                    "path": item.path,
                    "title": record.title,
                    "relative_dir": item.relative_dir,
                    "toc_label": item.toc_label
                }
            )

        context_markdown = self._load_llm_nav_context_markdown(
            source_paths = source_paths,
            toc_file = toc_file
        )

        try:
            llm_markdown = llm_generate(
                context_markdown = context_markdown,
                documents = llm_documents
            )
        except Exception:
            logger.exception("LLM folder nav generation failed")
            return False

        if not llm_markdown or not llm_markdown.strip():
            return False

        rewritten_markdown, rewritten_links = self._replace_source_links_in_nav_markdown(
            markdown = llm_markdown,
            created_docs = created_docs
        )
        if rewritten_links <= 0:
            return False
        if len(rewritten_markdown.strip()) < 20:
            return False

        try:
            nav_create = self._create_doc_with_meta(
                title = self._normalize_doc_title(title = folder_nav_title) or "00-导航总目录",
                folder_token = folder_token
            )
            self.doc_writer.write_markdown_with_fallback(
                document_id = nav_create["document_id"],
                content = rewritten_markdown
            )
            self._log_robot_push(
                stage = "folder_nav_created",
                detail = (
                    f"title = {folder_nav_title}, document_id = {nav_create['document_id']}, "
                    f"entries = {len(created_docs)}, mode = llm"
                )
            )
        except Exception:
            logger.exception("LLM folder nav write failed")
            return False
        return True

    def _load_llm_nav_context_markdown(self, source_paths: list[str], toc_file: str) -> str:
        """Load root README first, fallback to TOC markdown for LLM context.

        Args:
            source_paths: Source markdown paths.
            toc_file: TOC file path.
        """

        path_lookup: dict[str, str] = {}
        for path in source_paths:
            normalized = self._normalize_source_relative_path(path = path)
            if not normalized:
                continue
            path_lookup[normalized.lower()] = normalized

        root_candidates = [
            "README.md",
            "readme.md"
        ]
        for candidate in root_candidates:
            selected = path_lookup.get(candidate.lower(), "")
            if not selected:
                continue
            try:
                return self.source_adapter.read_markdown(relative_path = selected).markdown
            except Exception:
                continue

        normalized_toc = self._normalize_source_relative_path(path = toc_file)
        if normalized_toc:
            selected_toc = path_lookup.get(normalized_toc.lower(), "")
            if selected_toc:
                try:
                    return self.source_adapter.read_markdown(relative_path = selected_toc).markdown
                except Exception:
                    return ""
        return ""

    def _replace_source_links_in_nav_markdown(
        self,
        markdown: str,
        created_docs: list[CreatedDocRecord]
    ) -> tuple[str, int]:
        """Replace source-path markdown links with final Feishu doc links.

        Args:
            markdown: LLM-generated markdown.
            created_docs: Created document records.
        """

        link_pattern = re.compile(r"\[(?P<label>[^\]]+)\]\((?P<target>[^)]+)\)")
        record_lookup: dict[str, CreatedDocRecord] = {}
        for item in created_docs:
            normalized = self._normalize_source_relative_path(path = item.path)
            if normalized:
                record_lookup[normalized.lower()] = item

        replaced_count_ref = [0]

        def _replace(match: re.Match) -> str:
            label = (match.group("label") or "").strip()
            target = (match.group("target") or "").strip()
            normalized_target = self._normalize_source_relative_path(path = target)
            if not normalized_target:
                return match.group(0)

            record = record_lookup.get(normalized_target.lower())
            if not record:
                return match.group(0)

            replaced_count_ref[0] += 1
            if record.doc_url:
                return f"[{label}]({record.doc_url})"
            return (
                f"{label} · `{record.path}` "
                f"(document_id: `{record.document_id}`)"
            )

        rewritten = link_pattern.sub(_replace, markdown)
        return rewritten, replaced_count_ref[0]

    def _normalize_source_relative_path(self, path: str) -> str:
        """Normalize path text into source-relative path format.

        Args:
            path: Raw path text.
        """

        value = urllib.parse.unquote((path or "").strip())
        if not value:
            return ""

        parsed = urllib.parse.urlparse(value)
        if parsed.scheme:
            return ""

        value = value.replace("\\", "/")
        value = value.split("#", 1)[0]
        value = value.split("?", 1)[0]
        if not value:
            return ""

        normalized = posixpath.normpath(value).lstrip("/")
        if normalized in {"", "."}:
            return ""
        if normalized.startswith("../"):
            return ""
        return normalized

    def _resolve_folder_root_subdir_name(self, explicit_name: str) -> str:
        """Resolve task root folder name for one import run.

        Args:
            explicit_name: Optional CLI-provided folder name.
        """

        normalized_explicit = self._normalize_doc_title(title = explicit_name)
        if normalized_explicit:
            return normalized_explicit

        source_name = self._detect_source_name_for_folder_root()
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
        return self._normalize_doc_title(title = f"{source_name}-{timestamp}") or f"import-{timestamp}"

    def _detect_source_name_for_folder_root(self) -> str:
        """Build source label used by task root folder auto naming.

        Args:
            self: Orchestrator instance.
        """

        if hasattr(self.source_adapter, "root_path"):
            root_path = str(getattr(self.source_adapter, "root_path", "")).strip()
            name = os.path.basename(root_path.rstrip("/")) if root_path else ""
            if name:
                return name

        if hasattr(self.source_adapter, "subdir"):
            subdir = str(getattr(self.source_adapter, "subdir", "")).strip().strip("/")
            if subdir:
                return subdir.split("/")[-1]

        if hasattr(self.source_adapter, "repo"):
            repo = str(getattr(self.source_adapter, "repo", "")).strip()
            if repo:
                parsed = urllib.parse.urlparse(repo)
                if parsed.path:
                    repo_path = parsed.path.rstrip("/").split("/")[-1]
                else:
                    repo_path = repo.rstrip("/").split("/")[-1]
                if repo_path.endswith(".git"):
                    repo_path = repo_path[:-4]
                if repo_path:
                    return repo_path

        return "import"

    def _write_folder_navigation_doc(
        self,
        folder_nav_title: str,
        manifest: ImportManifest,
        created_docs: list[CreatedDocRecord],
        folder_token: str = ""
    ) -> None:
        """Create one folder navigation doc linking all imported markdown docs.

        Args:
            folder_nav_title: Navigation document title.
            manifest: Import manifest.
            created_docs: Created document records.
            folder_token: Optional destination folder token.
        """

        record_by_path = {item.path: item for item in created_docs}
        nav_markdown = self._build_folder_nav_markdown(
            manifest = manifest,
            record_by_path = record_by_path
        )
        if not nav_markdown.strip():
            return

        try:
            nav_create = self._create_doc_with_meta(
                title = self._normalize_doc_title(title = folder_nav_title) or "00-导航总目录",
                folder_token = folder_token
            )
            self.doc_writer.write_markdown_with_fallback(
                document_id = nav_create["document_id"],
                content = nav_markdown
            )
            logger.info(
                "folder navigation doc created: document_id = %s, title = %s",
                nav_create["document_id"],
                folder_nav_title
            )
            self._log_robot_push(
                stage = "folder_nav_created",
                detail = (
                    f"title = {folder_nav_title}, document_id = {nav_create['document_id']}, "
                    f"entries = {len(created_docs)}"
                )
            )
        except Exception:
            logger.exception("Failed to create folder navigation document")
            self._log_robot_push(
                stage = "folder_nav_failed",
                detail = f"title = {folder_nav_title}"
            )

    def _build_folder_nav_markdown(
        self,
        manifest: ImportManifest,
        record_by_path: dict[str, CreatedDocRecord]
    ) -> str:
        """Build markdown body for folder navigation document.

        Args:
            manifest: Import manifest.
            record_by_path: Path to created document record map.
        """

        lines = [
            "# 导航总目录",
            "",
            "> 本文档由导入器自动生成，用于在 folder 模式下提供目录编排导航。",
            ""
        ]

        for item in manifest.items:
            record = record_by_path.get(item.path)
            if not record:
                continue

            level = 0
            if item.relative_dir:
                level = len([segment for segment in item.relative_dir.split("/") if segment])
            indent = "  " * max(level, 0)

            display_title = record.title
            if item.toc_label:
                display_title = item.toc_label

            if record.doc_url:
                lines.append(
                    f"{indent}- [{display_title}]({record.doc_url}) · `{item.path}`"
                )
            else:
                lines.append(
                    (
                        f"{indent}- {display_title} · `{item.path}` "
                        f"(document_id: `{record.document_id}`)"
                    )
                )

        return "\n".join(lines)

    def _build_asset_lookup(self, assets: list[AssetRef]) -> dict[str, AssetRef]:
        """Build lookup map for image url/path to asset object.

        Args:
            assets: Parsed asset list.
        """

        lookup: dict[str, AssetRef] = {}
        for asset in assets:
            candidates = [
                asset.original_url,
                urllib.parse.unquote(asset.original_url),
                asset.resolved_url,
                urllib.parse.unquote(asset.resolved_url),
                os.path.basename(asset.original_url),
                os.path.basename(urllib.parse.unquote(asset.original_url)),
                os.path.basename(asset.resolved_url),
                os.path.basename(urllib.parse.unquote(asset.resolved_url))
            ]
            for key in candidates:
                if key:
                    lookup[key] = asset
        return lookup

    def _find_asset_by_image_url(self, image_url: str, asset_lookup: dict[str, AssetRef]) -> Optional[AssetRef]:
        """Match convert image url to parsed local/remote asset reference.

        Args:
            image_url: Image url from convert response.
            asset_lookup: Prebuilt lookup map.
        """

        normalized = image_url.strip()
        if not normalized:
            return None

        parsed = urllib.parse.urlparse(normalized)
        path_only = parsed.path or normalized
        candidates = [
            normalized,
            urllib.parse.unquote(normalized),
            path_only,
            urllib.parse.unquote(path_only),
            os.path.basename(path_only),
            os.path.basename(urllib.parse.unquote(path_only))
        ]

        for key in candidates:
            if key and key in asset_lookup:
                return asset_lookup[key]
        return None

    def _create_doc_with_title_strategy(
        self,
        doc: SourceDocument,
        folder_token: str = ""
    ) -> tuple[str, str, str]:
        """Create Feishu doc with path-aware title fallback strategy.

        Args:
            doc: Source markdown document.
            folder_token: Optional destination folder token override.
        """

        title_candidates = self._build_doc_title_candidates(doc = doc)
        errors: list[Exception] = []

        for index, title in enumerate(title_candidates):
            try:
                create_result = self._create_doc_with_meta(
                    title = title,
                    folder_token = folder_token
                )
                return create_result["document_id"], title, create_result.get("url", "")
            except Exception as exc:
                errors.append(exc)
                is_last = index >= len(title_candidates) - 1
                if is_last or not self._looks_like_invalid_param_error(exc = exc):
                    raise
                logger.warning(
                    "create_doc invalid param, retry with fallback title: path = %s, title = %s, error = %s",
                    doc.path,
                    title,
                    str(exc)
                )

        # Defensive branch; loop should have returned or raised above.
        if errors:
            raise errors[-1]
        raise RuntimeError("create_doc failed without explicit exception")

    def _create_doc_with_meta(self, title: str, folder_token: str = "") -> dict[str, str]:
        """Create one document and return document_id + url.

        Args:
            title: Document title.
            folder_token: Optional folder token override.
        """

        if hasattr(self.doc_writer, "create_doc_with_meta"):
            payload = self.doc_writer.create_doc_with_meta(
                title = title,
                folder_token = folder_token
            )
            return {
                "document_id": str(payload.get("document_id", "")),
                "url": str(payload.get("url", ""))
            }

        document_id = self.doc_writer.create_doc(
            title = title,
            folder_token = folder_token
        )
        return {
            "document_id": document_id,
            "url": ""
        }

    def _build_doc_title_candidates(self, doc: SourceDocument) -> list[str]:
        """Build ordered title candidates for one markdown document.

        Args:
            doc: Source markdown document.
        """

        candidates: list[str] = []

        if self._is_directory_index(path = doc.path):
            directory_title = self._last_path_segment(path = doc.relative_dir)
            if directory_title:
                candidates.append(directory_title)

        candidates.append(doc.title)
        candidates.append(self._path_based_title(path = doc.path))

        deduplicated: list[str] = []
        seen = set()
        for raw_title in candidates:
            normalized = self._normalize_doc_title(title = raw_title)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduplicated.append(normalized)

        if not deduplicated:
            return ["Untitled"]
        return deduplicated

    def _normalize_doc_title(self, title: str) -> str:
        """Normalize title to avoid Feishu invalid parameter errors.

        Args:
            title: Raw title text.
        """

        value = self._control_chars_pattern.sub(" ", title or "")
        value = self._title_invalid_chars_pattern.sub(" ", value)
        value = re.sub(r"\s+", " ", value).strip()
        if not value:
            return ""
        return self._truncate_utf8_bytes(text = value, max_bytes = self._title_max_bytes)

    def _truncate_utf8_bytes(self, text: str, max_bytes: int) -> str:
        """Truncate one string by UTF-8 bytes while keeping valid chars.

        Args:
            text: Input text.
            max_bytes: Max UTF-8 bytes.
        """

        if max_bytes <= 0:
            return ""

        result = ""
        used = 0
        for char in text:
            char_bytes = len(char.encode("utf-8"))
            if result and used + char_bytes > max_bytes:
                break
            if not result and char_bytes > max_bytes:
                return ""
            result += char
            used += char_bytes
        return result

    def _path_based_title(self, path: str) -> str:
        """Create a title derived from source-relative path.

        Args:
            path: Source-relative markdown path.
        """

        normalized = path.strip().replace("\\", "/")
        if not normalized:
            return ""

        normalized_lower = normalized.lower()
        if normalized_lower.endswith(".markdown"):
            normalized = normalized[:-9]
        elif normalized_lower.endswith(".docx"):
            normalized = normalized[:-5]
        elif normalized_lower.endswith(".md"):
            normalized = normalized[:-3]

        segments = [item for item in normalized.split("/") if item]
        if segments and segments[-1].lower() in {"readme", "index"}:
            segments = segments[:-1]

        if not segments:
            stem = os.path.splitext(os.path.basename(path))[0]
            return stem

        return " - ".join(segments)

    def _last_path_segment(self, path: str) -> str:
        """Get last non-empty path segment.

        Args:
            path: Relative path text.
        """

        normalized = path.strip().replace("\\", "/").strip("/")
        if not normalized:
            return ""
        return normalized.split("/")[-1]

    def _is_directory_index(self, path: str) -> bool:
        """Check whether markdown file is README/INDEX style index document.

        Args:
            path: Source-relative markdown path.
        """

        filename = os.path.basename(path or "")
        stem = os.path.splitext(filename)[0].lower()
        return stem in {"readme", "index", "table_of_contents", "toc"}

    def _looks_like_invalid_param_error(self, exc: Exception) -> bool:
        """Check whether exception looks like Feishu invalid parameter error.

        Args:
            exc: Raised exception.
        """

        message = str(exc).lower()
        if "1770001" in message:
            return True
        if "invalid param" in message:
            return True
        if "确认参数是否合法" in message:
            return True
        if "参数" in message and "合法" in message:
            return True
        return False

    def _assert_services_ready(self, write_mode: str) -> None:
        """Validate required Feishu services are available.

        Args:
            self: Orchestrator instance.
            write_mode: Write mode, one of folder/wiki/both.
        """

        if not self.doc_writer or not self.media_service:
            raise RuntimeError("Doc writer and media services are required when dry_run = False")
        if write_mode in {"wiki", "both"} and not self.wiki_service:
            raise RuntimeError("Wiki service is required for wiki/both modes")

    def _notify(self, chat_id: str, level: str, message: str, force: bool) -> None:
        """Send notification message according to level.

        Args:
            chat_id: Target chat id.
            level: Verbosity level.
            message: Message text.
            force: Whether to ignore level filter.
        """

        if not self.notify_service:
            return

        if level == "none" and not force:
            return
        if level == "minimal" and not force:
            return

        try:
            self.notify_service.send_status(chat_id = chat_id, message = message)
        except Exception:
            logger.exception("Failed to send notify message")

    def _log_robot_push(self, stage: str, detail: str) -> None:
        """Write structured robot push logs for delivery traceability.

        Args:
            stage: Robot delivery stage.
            detail: Stage detail text.
        """

        logger.info("robot_push | stage = %s | %s", stage, detail)
