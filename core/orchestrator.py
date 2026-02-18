import logging
import os
import re
import urllib.parse

from typing import Optional

from config.config import AppConfig
from core.orchestration_planner import OrchestrationPlanner
from integrations.feishu_api import DocWriterService
from integrations.feishu_api import MediaService
from integrations.feishu_api import WikiService
from data.models import AssetRef
from data.models import CreatedDocRecord
from data.models import DocumentPlanItem
from data.models import ImportFailure
from data.models import ImportManifest
from data.models import ImportResult
from data.models import SourceDocument
from data.source_adapters import SourceAdapter
from utils.markdown_processor import MarkdownProcessor


logger = logging.getLogger(__name__)


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
        structure_order: str = "toc_first",
        toc_file: str = "TABLE_OF_CONTENTS.md",
        folder_nav_doc: bool = True,
        folder_nav_title: str = "00-导航总目录",
        llm_fallback: str = "toc_ambiguity",
        llm_max_calls: int = 3
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
            structure_order: Ordering strategy, one of toc_first/path.
            toc_file: TOC markdown path relative to source root.
            folder_nav_doc: Whether to write folder navigation document.
            folder_nav_title: Folder navigation document title.
            llm_fallback: LLM fallback strategy for TOC ambiguity.
            llm_max_calls: Maximum number of LLM calls in one run.
        """

        paths = self.source_adapter.list_markdown()
        manifest = self._build_manifest(
            paths = paths,
            structure_order = structure_order,
            toc_file = toc_file,
            llm_fallback = llm_fallback,
            llm_max_calls = llm_max_calls
        )
        result = ImportResult(total = len(manifest.items))

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
        if manifest.unresolved_links:
            logger.warning("unresolved toc links: %d", len(manifest.unresolved_links))
            for unresolved in manifest.unresolved_links[:20]:
                logger.warning("toc unresolved: %s", unresolved)

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

                if dry_run:
                    result.success += 1
                    continue

                target_folder_token = ""
                if folder_subdirs and write_mode in {"folder", "both"}:
                    target_folder_token = self.doc_writer.ensure_folder_path(
                        relative_dir = doc.relative_dir
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

        result.failed = len(result.failures)

        if (
            not dry_run
            and folder_nav_doc
            and write_mode in {"folder", "both"}
            and created_docs
        ):
            self._write_folder_navigation_doc(
                folder_nav_title = folder_nav_title,
                manifest = manifest,
                created_docs = created_docs
            )

        logger.info("*" * 50)
        logger.info(
            "Import finished: total = %d, success = %d, failed = %d",
            result.total,
            result.success,
            result.failed
        )
        logger.info("*" * 50)

        summary_lines = [
            "知识导入任务完成",
            f"total = {result.total}",
            f"success = {result.success}",
            f"failed = {result.failed}",
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
        llm_max_calls: int
    ) -> ImportManifest:
        """Build import manifest with optional TOC-aware ordering.

        Args:
            paths: Source markdown paths.
            structure_order: Ordering strategy.
            toc_file: TOC file path.
            llm_fallback: LLM fallback strategy.
            llm_max_calls: LLM call cap.
        """

        planner = OrchestrationPlanner(
            source_adapter = self.source_adapter,
            llm_resolver = self.llm_client if llm_fallback == "toc_ambiguity" else None
        )
        manifest = planner.build_manifest(
            markdown_paths = paths,
            structure_order = structure_order,
            toc_file = toc_file,
            llm_fallback = llm_fallback,
            llm_max_calls = llm_max_calls
        )

        if not manifest.items:
            manifest.items = [
                DocumentPlanItem(
                    path = path,
                    order = index,
                    is_index = self._is_directory_index(path = path),
                    relative_dir = (
                        ""
                        if os.path.dirname(path).replace("\\", "/") == "."
                        else os.path.dirname(path).replace("\\", "/")
                    ),
                    toc_label = ""
                )
                for index, path in enumerate(sorted(paths))
            ]
        return manifest

    def _write_folder_navigation_doc(
        self,
        folder_nav_title: str,
        manifest: ImportManifest,
        created_docs: list[CreatedDocRecord]
    ) -> None:
        """Create one folder navigation doc linking all imported markdown docs.

        Args:
            folder_nav_title: Navigation document title.
            manifest: Import manifest.
            created_docs: Created document records.
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
                folder_token = ""
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
        except Exception:
            logger.exception("Failed to create folder navigation document")

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

        if normalized.lower().endswith(".md"):
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
        return stem in {"readme", "index"}

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
