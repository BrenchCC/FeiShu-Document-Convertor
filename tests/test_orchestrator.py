import unittest

from unittest import mock

from config.config import AppConfig
from data.models import CreatedDocRecord
from data.models import DocumentPlanItem
from data.models import ImportFailure
from data.models import ImportManifest
from data.models import SourceDocument
from core.orchestrator import ImportOrchestrator
from utils.markdown_processor import MarkdownProcessor


class FakeSource:
    """Fake source adapter for orchestrator tests."""

    def __init__(self) -> None:
        self.docs = {
            "ok.md": SourceDocument(
                path = "ok.md",
                title = "ok",
                markdown = "# ok\n![a](./a.png)",
                assets = [],
                relative_dir = "",
                base_ref = "/tmp",
                source_type = "local"
            ),
            "bad.md": SourceDocument(
                path = "bad.md",
                title = "bad",
                markdown = "# bad",
                assets = [],
                relative_dir = "",
                base_ref = "/tmp",
                source_type = "local"
            )
        }

    def list_markdown(self):
        """List fake markdown files.

        Args:
            self: Fake source instance.
        """

        return ["ok.md", "bad.md"]

    def read_markdown(self, relative_path: str):
        """Return fake doc by path.

        Args:
            self: Fake source instance.
            relative_path: Relative markdown path.
        """

        return self.docs[relative_path]


class FakeDocWriter:
    """Fake document writer service."""

    def __init__(self) -> None:
        self.created = []
        self.ensure_calls = []

    def create_doc(self, title: str, folder_token: str = "") -> str:
        """Return deterministic document id.

        Args:
            self: Fake writer.
            title: Document title.
            folder_token: Optional destination folder token.
        """

        self.created.append((title, folder_token))
        return f"doc_{title}"

    def ensure_folder_path(self, relative_dir: str, root_folder_token: str = "") -> str:
        """Return deterministic folder token for hierarchy mode.

        Args:
            self: Fake writer.
            relative_dir: Relative directory.
            root_folder_token: Optional root folder token override.
        """

        self.ensure_calls.append(relative_dir)
        if not relative_dir:
            return "root_folder"
        return f"folder_{relative_dir.replace('/', '_')}"

    def convert_markdown(
        self,
        document_id: str,
        content: str,
        image_token_map = None,
        image_block_handler = None
    ) -> None:
        """Raise for bad document to test fallback flow.

        Args:
            self: Fake writer.
            document_id: Document id.
            content: Markdown content.
            image_token_map: Image token map.
            image_block_handler: Image handler callback.
        """

        if document_id == "doc_bad":
            raise RuntimeError("convert failed")

    def append_fallback_text(self, document_id: str, content: str) -> None:
        """Fallback no-op.

        Args:
            self: Fake writer.
            document_id: Document id.
            content: Markdown content.
        """

    def replace_image(self, document_id: str, block_id: str, file_token: str) -> None:
        """Replace image no-op.

        Args:
            self: Fake writer.
            document_id: Document id.
            block_id: Image block id.
            file_token: Uploaded file token.
        """

    def write_markdown_with_fallback(
        self,
        document_id: str,
        content: str,
        image_token_map = None,
        image_block_handler = None
    ) -> None:
        """Write markdown with fallback simulation.

        Args:
            self: Fake writer.
            document_id: Document id.
            content: Markdown content.
            image_token_map: Image token map.
            image_block_handler: Image handler callback.
        """

        try:
            self.convert_markdown(
                document_id = document_id,
                content = content,
                image_token_map = image_token_map,
                image_block_handler = image_block_handler
            )
        except Exception:
            self.append_fallback_text(document_id = document_id, content = content)


class FakeMedia:
    """Fake media uploader service."""

    def upload_to_doc(self, asset, document_id: str) -> str:
        """Always return one token.

        Args:
            self: Fake media.
            asset: Asset reference.
            document_id: Document id.
        """

        return "token123"

    def upload_to_node(self, asset, parent_node: str) -> str:
        """Always return one token.

        Args:
            self: Fake media.
            asset: Asset reference.
            parent_node: Destination node token.
        """

        return "token123"


class FakeWiki:
    """Fake wiki service."""

    def get_or_create_space(self, space_name: str) -> str:
        """Return fixed space id.

        Args:
            self: Fake wiki.
            space_name: Space name.
        """

        return "space1"

    def ensure_path_nodes(self, space_id: str, relative_dir: str) -> str:
        """Return root token.

        Args:
            self: Fake wiki.
            space_id: Space id.
            relative_dir: Relative directory.
        """

        return ""

    def move_doc_to_wiki(self, space_id: str, document_id: str, parent_node_token: str, title: str) -> str:
        """Raise for bad doc to verify continue-on-failure.

        Args:
            self: Fake wiki.
            space_id: Space id.
            document_id: Document id.
            parent_node_token: Parent token.
            title: Node title.
        """

        if document_id == "doc_bad":
            raise RuntimeError("wiki move failed")
        return "node1"


class FakeNotify:
    """Fake notify service."""

    def __init__(self) -> None:
        self.messages = []

    def send_status(self, chat_id: str, message: str) -> None:
        """Collect status messages.

        Args:
            self: Fake notify.
            chat_id: Chat id.
            message: Message text.
        """

        self.messages.append((chat_id, message))


class SingleDocSource:
    """Fake source adapter exposing one markdown file."""

    def __init__(self, doc: SourceDocument) -> None:
        self.doc = doc

    def list_markdown(self):
        """List one markdown file.

        Args:
            self: Fake source instance.
        """

        return [self.doc.path]

    def read_markdown(self, relative_path: str):
        """Return the same markdown file.

        Args:
            self: Fake source instance.
            relative_path: Relative markdown path.
        """

        return self.doc


class RecordingDocWriter(FakeDocWriter):
    """Fake writer recording create_doc title calls."""

    def __init__(self) -> None:
        super().__init__()
        self.created_titles = []

    def create_doc(self, title: str, folder_token: str = "") -> str:
        """Record title and return deterministic doc id.

        Args:
            self: Fake writer.
            title: Document title.
            folder_token: Optional destination folder token.
        """

        self.created_titles.append(title)
        return f"doc_{len(self.created_titles)}"


class RetryOnceInvalidParamDocWriter(FakeDocWriter):
    """Fake writer failing once with invalid parameter message."""

    def __init__(self) -> None:
        super().__init__()
        self.created_titles = []

    def create_doc(self, title: str, folder_token: str = "") -> str:
        """Fail first call and succeed on second call.

        Args:
            self: Fake writer.
            title: Document title.
            folder_token: Optional destination folder token.
        """

        self.created_titles.append(title)
        if len(self.created_titles) == 1:
            raise RuntimeError(
                "Feishu API failed for /open-apis/docx/v1/documents: "
                "code = 1770001, msg = 请确认参数是否合法"
            )
        return "doc_retry_ok"


class OrderedSource:
    """Fake source adapter exposing unsorted markdown paths."""

    def __init__(self) -> None:
        self.docs = {
            "b/ch2.md": SourceDocument(
                path = "b/ch2.md",
                title = "Chapter 2",
                markdown = "# Chapter 2",
                assets = [],
                relative_dir = "b",
                base_ref = "/tmp",
                source_type = "local"
            ),
            "a/ch1.md": SourceDocument(
                path = "a/ch1.md",
                title = "Chapter 1",
                markdown = "# Chapter 1",
                assets = [],
                relative_dir = "a",
                base_ref = "/tmp",
                source_type = "local"
            )
        }

    def list_markdown(self):
        """Return intentionally unsorted markdown paths.

        Args:
            self: Fake source instance.
        """

        return ["b/ch2.md", "a/ch1.md"]

    def read_markdown(self, relative_path: str):
        """Return markdown by relative path.

        Args:
            self: Fake source instance.
            relative_path: Relative markdown path.
        """

        return self.docs[relative_path]


class NavDocWriter(FakeDocWriter):
    """Fake writer recording created docs and nav markdown payload."""

    def __init__(self) -> None:
        super().__init__()
        self.created_titles = []
        self.created_meta = []
        self.nav_markdown = ""
        self._doc_index = 0

    def create_doc_with_meta(self, title: str, folder_token: str = "") -> dict[str, str]:
        """Return deterministic metadata with partial URL coverage.

        Args:
            self: Fake writer.
            title: Document title.
            folder_token: Optional destination folder token.
        """

        self.created_titles.append(title)
        self.created_meta.append((title, folder_token))
        if title == "00-导航总目录":
            return {
                "document_id": "doc_nav",
                "url": "https://example.com/doc_nav"
            }

        self._doc_index += 1
        if self._doc_index == 1:
            return {
                "document_id": "doc_ch1",
                "url": "https://example.com/doc_ch1"
            }
        return {
            "document_id": "doc_ch2",
            "url": ""
        }

    def write_markdown_with_fallback(
        self,
        document_id: str,
        content: str,
        image_token_map = None,
        image_block_handler = None
    ) -> None:
        """Record nav markdown while keeping normal write behavior.

        Args:
            self: Fake writer.
            document_id: Document id.
            content: Markdown content.
            image_token_map: Unused.
            image_block_handler: Unused.
        """

        if document_id == "doc_nav":
            self.nav_markdown = content


class FakeLlmFolderNav:
    """Fake LLM nav generator returning path-based markdown links."""

    def generate_folder_nav_markdown(
        self,
        context_markdown: str,
        documents: list[dict[str, str]]
    ) -> str:
        """Return deterministic nav markdown.

        Args:
            self: Fake llm instance.
            context_markdown: Context markdown.
            documents: Document descriptors.
        """

        return (
            "# 导航\n\n"
            "- [Chapter 1](a/ch1.md)\n"
            "- [Chapter 2](b/ch2.md)\n"
        )


class ReadmePreferredSource:
    """Source adapter that includes root README and TOC context files."""

    def __init__(self) -> None:
        self.docs = {
            "README.md": SourceDocument(
                path = "README.md",
                title = "README",
                markdown = "# Root Readme Context\n\nReadme first.",
                assets = [],
                relative_dir = "",
                base_ref = "/tmp",
                source_type = "local"
            ),
            "TABLE_OF_CONTENTS.md": SourceDocument(
                path = "TABLE_OF_CONTENTS.md",
                title = "TOC",
                markdown = "# TOC Context\n\n- [Chapter 1](a/ch1.md)",
                assets = [],
                relative_dir = "",
                base_ref = "/tmp",
                source_type = "local"
            ),
            "a/ch1.md": SourceDocument(
                path = "a/ch1.md",
                title = "Chapter 1",
                markdown = "# Chapter 1",
                assets = [],
                relative_dir = "a",
                base_ref = "/tmp",
                source_type = "local"
            )
        }

    def list_markdown(self):
        """List markdown files preserving deterministic order.

        Args:
            self: Source adapter instance.
        """

        return ["README.md", "TABLE_OF_CONTENTS.md", "a/ch1.md"]

    def read_markdown(self, relative_path: str):
        """Read one markdown document by relative path.

        Args:
            self: Source adapter instance.
            relative_path: Source-relative markdown path.
        """

        return self.docs[relative_path]


class CaptureContextLlmFolderNav:
    """Fake LLM that captures provided context markdown and returns one link."""

    def __init__(self) -> None:
        self.context_markdown = ""

    def generate_folder_nav_markdown(
        self,
        context_markdown: str,
        documents: list[dict[str, str]]
    ) -> str:
        """Capture context and return one valid source-path link markdown.

        Args:
            self: Fake llm instance.
            context_markdown: Context markdown.
            documents: Document descriptors.
        """

        self.context_markdown = context_markdown
        target_path = ""
        if documents:
            target_path = str(documents[0].get("path", "")).strip()
        if not target_path:
            return ""
        return f"# 导航\n\n- [First]({target_path})\n"


class EmptyLlmFolderNav:
    """Fake LLM that returns empty nav output to trigger skip behavior."""

    def generate_folder_nav_markdown(
        self,
        context_markdown: str,
        documents: list[dict[str, str]]
    ) -> str:
        """Return empty markdown content.

        Args:
            self: Fake llm instance.
            context_markdown: Context markdown.
            documents: Document descriptors.
        """

        return ""


class TestImportOrchestrator(unittest.TestCase):
    """Tests for import orchestrator behavior."""

    def test_continue_on_failure(self) -> None:
        """Should continue task when one file fails.

        Args:
            self: Test case instance.
        """

        config = AppConfig(
            feishu_base_url = "https://open.feishu.cn",
            feishu_webhook_url = "https://example.com/webhook",
            feishu_app_id = "w",
            feishu_app_secret = "w",
            feishu_user_access_token = "",
            feishu_user_refresh_token = "",
            feishu_user_token_cache_path = "cache/user_token.json",
            feishu_folder_token = "",
            request_timeout = 30,
            max_retries = 1,
            retry_backoff = 0.1,
            image_url_template = "https://example.com/{token}",
            feishu_message_max_bytes = 18000,
            feishu_convert_max_bytes = 45000,
            notify_level = "normal"
        )

        notify = FakeNotify()
        orchestrator = ImportOrchestrator(
            source_adapter = FakeSource(),
            markdown_processor = MarkdownProcessor(),
            config = config,
            doc_writer = FakeDocWriter(),
            media_service = FakeMedia(),
            wiki_service = FakeWiki(),
            notify_service = notify
        )

        result = orchestrator.run(
            space_name = "demo",
            space_id = "",
            chat_id = "chat1",
            dry_run = False,
            notify_level = "normal",
            write_mode = "both",
            folder_nav_doc = False
        )

        self.assertEqual(result.total, 2)
        self.assertEqual(result.success, 1)
        self.assertEqual(result.failed, 1)
        self.assertEqual(result.failures[0].path, "bad.md")
        self.assertTrue(len(notify.messages) >= 2)

    def test_folder_subdirs_create_docs_in_relative_folders(self) -> None:
        """Folder hierarchy mode should route docs into created subfolders.

        Args:
            self: Test case instance.
        """

        config = AppConfig(
            feishu_base_url = "https://open.feishu.cn",
            feishu_webhook_url = "",
            feishu_app_id = "w",
            feishu_app_secret = "w",
            feishu_user_access_token = "",
            feishu_user_refresh_token = "",
            feishu_user_token_cache_path = "cache/user_token.json",
            feishu_folder_token = "fld_x",
            request_timeout = 30,
            max_retries = 1,
            retry_backoff = 0.1,
            image_url_template = "https://example.com/{token}",
            feishu_message_max_bytes = 18000,
            feishu_convert_max_bytes = 45000,
            notify_level = "none"
        )
        writer = FakeDocWriter()
        doc = SourceDocument(
            path = "part-a/chapter-1.md",
            title = "chapter-1",
            markdown = "# chapter-1",
            assets = [],
            relative_dir = "part-a",
            base_ref = "/tmp",
            source_type = "local"
        )
        orchestrator = ImportOrchestrator(
            source_adapter = SingleDocSource(doc = doc),
            markdown_processor = MarkdownProcessor(),
            config = config,
            doc_writer = writer,
            media_service = FakeMedia(),
            wiki_service = None,
            notify_service = None
        )

        result = orchestrator.run(
            space_name = "",
            space_id = "",
            chat_id = "",
            dry_run = False,
            notify_level = "none",
            write_mode = "folder",
            folder_subdirs = True,
            folder_root_subdir = False,
            folder_nav_doc = False
        )

        self.assertEqual(result.success, 1)
        self.assertEqual(result.failed, 0)
        self.assertEqual(len(writer.created), 1)
        self.assertEqual(writer.created[0][1], "folder_part-a")

    def test_folder_root_subdir_with_subdirs(self) -> None:
        """Folder root subdir should prefix directory hierarchy when enabled.

        Args:
            self: Test case instance.
        """

        config = AppConfig(
            feishu_base_url = "https://open.feishu.cn",
            feishu_webhook_url = "",
            feishu_app_id = "w",
            feishu_app_secret = "w",
            feishu_user_access_token = "",
            feishu_user_refresh_token = "",
            feishu_user_token_cache_path = "cache/user_token.json",
            feishu_folder_token = "fld_x",
            request_timeout = 30,
            max_retries = 1,
            retry_backoff = 0.1,
            image_url_template = "https://example.com/{token}",
            feishu_message_max_bytes = 18000,
            feishu_convert_max_bytes = 45000,
            notify_level = "none"
        )
        writer = FakeDocWriter()
        doc = SourceDocument(
            path = "part-a/chapter-1.md",
            title = "chapter-1",
            markdown = "# chapter-1",
            assets = [],
            relative_dir = "part-a",
            base_ref = "/tmp",
            source_type = "local"
        )
        orchestrator = ImportOrchestrator(
            source_adapter = SingleDocSource(doc = doc),
            markdown_processor = MarkdownProcessor(),
            config = config,
            doc_writer = writer,
            media_service = FakeMedia(),
            wiki_service = None,
            notify_service = None
        )

        result = orchestrator.run(
            space_name = "",
            space_id = "",
            chat_id = "",
            dry_run = False,
            notify_level = "none",
            write_mode = "folder",
            folder_subdirs = True,
            folder_root_subdir = True,
            folder_root_subdir_name = "batch_001",
            folder_nav_doc = False
        )

        self.assertEqual(result.success, 1)
        self.assertEqual(result.failed, 0)
        self.assertEqual(writer.created[0][1], "folder_batch_001_part-a")
        self.assertEqual(
            writer.ensure_calls,
            ["batch_001", "batch_001/part-a"]
        )

    def test_folder_root_subdir_without_subdirs(self) -> None:
        """Folder root subdir should hold all docs when subdirs are disabled.

        Args:
            self: Test case instance.
        """

        config = AppConfig(
            feishu_base_url = "https://open.feishu.cn",
            feishu_webhook_url = "",
            feishu_app_id = "w",
            feishu_app_secret = "w",
            feishu_user_access_token = "",
            feishu_user_refresh_token = "",
            feishu_user_token_cache_path = "cache/user_token.json",
            feishu_folder_token = "fld_x",
            request_timeout = 30,
            max_retries = 1,
            retry_backoff = 0.1,
            image_url_template = "https://example.com/{token}",
            feishu_message_max_bytes = 18000,
            feishu_convert_max_bytes = 45000,
            notify_level = "none"
        )
        writer = FakeDocWriter()
        doc = SourceDocument(
            path = "chapter-1.md",
            title = "chapter-1",
            markdown = "# chapter-1",
            assets = [],
            relative_dir = "",
            base_ref = "/tmp",
            source_type = "local"
        )
        orchestrator = ImportOrchestrator(
            source_adapter = SingleDocSource(doc = doc),
            markdown_processor = MarkdownProcessor(),
            config = config,
            doc_writer = writer,
            media_service = FakeMedia(),
            wiki_service = None,
            notify_service = None
        )

        result = orchestrator.run(
            space_name = "",
            space_id = "",
            chat_id = "",
            dry_run = False,
            notify_level = "none",
            write_mode = "folder",
            folder_subdirs = False,
            folder_root_subdir = True,
            folder_root_subdir_name = "batch_002",
            folder_nav_doc = False
        )

        self.assertEqual(result.success, 1)
        self.assertEqual(result.failed, 0)
        self.assertEqual(writer.created[0][1], "folder_batch_002")
        self.assertEqual(writer.ensure_calls, ["batch_002"])

    def test_directory_index_title_mode_uses_folder_name(self) -> None:
        """Directory index markdown should prefer folder-name title.

        Args:
            self: Test case instance.
        """

        config = AppConfig(
            feishu_base_url = "https://open.feishu.cn",
            feishu_webhook_url = "",
            feishu_app_id = "w",
            feishu_app_secret = "w",
            feishu_user_access_token = "",
            feishu_user_refresh_token = "",
            feishu_user_token_cache_path = "cache/user_token.json",
            feishu_folder_token = "fld_x",
            request_timeout = 30,
            max_retries = 1,
            retry_backoff = 0.1,
            image_url_template = "https://example.com/{token}",
            feishu_message_max_bytes = 18000,
            feishu_convert_max_bytes = 45000,
            notify_level = "none"
        )
        doc = SourceDocument(
            path = "Part7-生产架构/README.md",
            title = "《AI Agent 架构：从单体到企业级多智能体》",
            markdown = "# overview",
            assets = [],
            relative_dir = "Part7-生产架构",
            base_ref = "/tmp",
            source_type = "local"
        )
        writer = RecordingDocWriter()
        orchestrator = ImportOrchestrator(
            source_adapter = SingleDocSource(doc = doc),
            markdown_processor = MarkdownProcessor(),
            config = config,
            doc_writer = writer,
            media_service = FakeMedia(),
            wiki_service = None,
            notify_service = None
        )

        result = orchestrator.run(
            space_name = "",
            space_id = "",
            chat_id = "",
            dry_run = False,
            notify_level = "none",
            write_mode = "folder",
            folder_nav_doc = False
        )

        self.assertEqual(result.success, 1)
        self.assertEqual(result.failed, 0)
        self.assertEqual(writer.created_titles[0], "Part7-生产架构")

    def test_retry_create_doc_with_path_based_title_on_invalid_param(self) -> None:
        """Title fallback should retry with path-based title when invalid.

        Args:
            self: Test case instance.
        """

        config = AppConfig(
            feishu_base_url = "https://open.feishu.cn",
            feishu_webhook_url = "",
            feishu_app_id = "w",
            feishu_app_secret = "w",
            feishu_user_access_token = "",
            feishu_user_refresh_token = "",
            feishu_user_token_cache_path = "cache/user_token.json",
            feishu_folder_token = "fld_x",
            request_timeout = 30,
            max_retries = 1,
            retry_backoff = 0.1,
            image_url_template = "https://example.com/{token}",
            feishu_message_max_bytes = 18000,
            feishu_convert_max_bytes = 45000,
            notify_level = "none"
        )
        doc = SourceDocument(
            path = "Part2-工具与扩展/第03章：工具调用基础.md",
            title = "第 3 章：工具调用基础",
            markdown = "# chapter",
            assets = [],
            relative_dir = "Part2-工具与扩展",
            base_ref = "/tmp",
            source_type = "local"
        )
        writer = RetryOnceInvalidParamDocWriter()
        orchestrator = ImportOrchestrator(
            source_adapter = SingleDocSource(doc = doc),
            markdown_processor = MarkdownProcessor(),
            config = config,
            doc_writer = writer,
            media_service = FakeMedia(),
            wiki_service = None,
            notify_service = None
        )

        result = orchestrator.run(
            space_name = "",
            space_id = "",
            chat_id = "",
            dry_run = False,
            notify_level = "none",
            write_mode = "folder",
            folder_nav_doc = False
        )

        self.assertEqual(result.success, 1)
        self.assertEqual(result.failed, 0)
        self.assertEqual(len(writer.created_titles), 2)
        self.assertEqual(writer.created_titles[0], "第 3 章：工具调用基础")
        self.assertEqual(writer.created_titles[1], "Part2-工具与扩展 - 第03章：工具调用基础")

    def test_root_readme_kept_from_import_by_default(self) -> None:
        """Root README should be imported when skip flag is disabled.

        Args:
            self: Test case instance.
        """

        config = AppConfig(
            feishu_base_url = "https://open.feishu.cn",
            feishu_webhook_url = "",
            feishu_app_id = "w",
            feishu_app_secret = "w",
            feishu_user_access_token = "",
            feishu_user_refresh_token = "",
            feishu_user_token_cache_path = "cache/user_token.json",
            feishu_folder_token = "fld_x",
            request_timeout = 30,
            max_retries = 1,
            retry_backoff = 0.1,
            image_url_template = "https://example.com/{token}",
            feishu_message_max_bytes = 18000,
            feishu_convert_max_bytes = 45000,
            notify_level = "none"
        )
        doc = SourceDocument(
            path = "README.md",
            title = "《AI Agent 架构：从单体到企业级多智能体》",
            markdown = "# root",
            assets = [],
            relative_dir = "",
            base_ref = "/tmp",
            source_type = "local"
        )
        writer = RetryOnceInvalidParamDocWriter()
        orchestrator = ImportOrchestrator(
            source_adapter = SingleDocSource(doc = doc),
            markdown_processor = MarkdownProcessor(),
            config = config,
            doc_writer = writer,
            media_service = FakeMedia(),
            wiki_service = None,
            notify_service = None
        )

        result = orchestrator.run(
            space_name = "",
            space_id = "",
            chat_id = "",
            dry_run = False,
            notify_level = "none",
            write_mode = "folder",
            folder_nav_doc = False
        )

        self.assertEqual(result.success, 1)
        self.assertEqual(result.failed, 0)
        self.assertEqual(result.skipped, 0)
        self.assertEqual(len(result.skipped_items), 0)
        self.assertEqual(len(writer.created_titles), 2)

    def test_root_readme_filtered_from_import_when_enabled(self) -> None:
        """Root README should be skipped when skip flag is enabled.

        Args:
            self: Test case instance.
        """

        config = AppConfig(
            feishu_base_url = "https://open.feishu.cn",
            feishu_webhook_url = "",
            feishu_app_id = "w",
            feishu_app_secret = "w",
            feishu_user_access_token = "",
            feishu_user_refresh_token = "",
            feishu_user_token_cache_path = "cache/user_token.json",
            feishu_folder_token = "fld_x",
            request_timeout = 30,
            max_retries = 1,
            retry_backoff = 0.1,
            image_url_template = "https://example.com/{token}",
            feishu_message_max_bytes = 18000,
            feishu_convert_max_bytes = 45000,
            notify_level = "none"
        )
        doc = SourceDocument(
            path = "README.md",
            title = "《AI Agent 架构：从单体到企业级多智能体》",
            markdown = "# root",
            assets = [],
            relative_dir = "",
            base_ref = "/tmp",
            source_type = "local"
        )
        writer = RetryOnceInvalidParamDocWriter()
        orchestrator = ImportOrchestrator(
            source_adapter = SingleDocSource(doc = doc),
            markdown_processor = MarkdownProcessor(),
            config = config,
            doc_writer = writer,
            media_service = FakeMedia(),
            wiki_service = None,
            notify_service = None
        )

        result = orchestrator.run(
            space_name = "",
            space_id = "",
            chat_id = "",
            dry_run = False,
            notify_level = "none",
            write_mode = "folder",
            folder_nav_doc = False,
            skip_root_readme = True
        )

        self.assertEqual(result.success, 0)
        self.assertEqual(result.failed, 0)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(len(result.skipped_items), 1)
        self.assertEqual(result.skipped_items[0].path, "README.md")
        self.assertEqual(writer.created_titles, [])

    def test_both_mode_respects_path_order_manifest(self) -> None:
        """Write-mode both should follow planned order before writing docs.

        Args:
            self: Test case instance.
        """

        config = AppConfig(
            feishu_base_url = "https://open.feishu.cn",
            feishu_webhook_url = "",
            feishu_app_id = "w",
            feishu_app_secret = "w",
            feishu_user_access_token = "",
            feishu_user_refresh_token = "",
            feishu_user_token_cache_path = "cache/user_token.json",
            feishu_folder_token = "fld_x",
            request_timeout = 30,
            max_retries = 1,
            retry_backoff = 0.1,
            image_url_template = "https://example.com/{token}",
            feishu_message_max_bytes = 18000,
            feishu_convert_max_bytes = 45000,
            notify_level = "none"
        )
        writer = RecordingDocWriter()
        orchestrator = ImportOrchestrator(
            source_adapter = OrderedSource(),
            markdown_processor = MarkdownProcessor(),
            config = config,
            doc_writer = writer,
            media_service = FakeMedia(),
            wiki_service = FakeWiki(),
            notify_service = None
        )

        result = orchestrator.run(
            space_name = "demo",
            space_id = "",
            chat_id = "",
            dry_run = False,
            notify_level = "none",
            write_mode = "both",
            structure_order = "path",
            folder_nav_doc = False
        )

        self.assertEqual(result.success, 2)
        self.assertEqual(result.failed, 0)
        self.assertEqual(
            writer.created_titles,
            ["Chapter 1", "Chapter 2"]
        )

    def test_folder_navigation_doc_contains_link_or_doc_id(self) -> None:
        """Folder navigation doc should prefer URL and fallback to document_id.

        Args:
            self: Test case instance.
        """

        config = AppConfig(
            feishu_base_url = "https://open.feishu.cn",
            feishu_webhook_url = "",
            feishu_app_id = "w",
            feishu_app_secret = "w",
            feishu_user_access_token = "",
            feishu_user_refresh_token = "",
            feishu_user_token_cache_path = "cache/user_token.json",
            feishu_folder_token = "fld_x",
            request_timeout = 30,
            max_retries = 1,
            retry_backoff = 0.1,
            image_url_template = "https://example.com/{token}",
            feishu_message_max_bytes = 18000,
            feishu_convert_max_bytes = 45000,
            notify_level = "none"
        )
        writer = NavDocWriter()
        orchestrator = ImportOrchestrator(
            source_adapter = OrderedSource(),
            markdown_processor = MarkdownProcessor(),
            config = config,
            doc_writer = writer,
            media_service = FakeMedia(),
            wiki_service = None,
            notify_service = None
        )

        result = orchestrator.run(
            space_name = "",
            space_id = "",
            chat_id = "",
            dry_run = False,
            notify_level = "none",
            write_mode = "folder",
            structure_order = "path",
            folder_nav_doc = True
        )

        self.assertEqual(result.success, 2)
        self.assertEqual(result.failed, 0)
        self.assertIn("[Chapter 1](https://example.com/doc_ch1)", writer.nav_markdown)
        self.assertIn("document_id: `doc_ch2`", writer.nav_markdown)

    def test_folder_navigation_doc_generated_by_llm_in_subdir_mode(self) -> None:
        """Subdir mode should use LLM nav markdown and replace source links.

        Args:
            self: Test case instance.
        """

        config = AppConfig(
            feishu_base_url = "https://open.feishu.cn",
            feishu_webhook_url = "",
            feishu_app_id = "w",
            feishu_app_secret = "w",
            feishu_user_access_token = "",
            feishu_user_refresh_token = "",
            feishu_user_token_cache_path = "cache/user_token.json",
            feishu_folder_token = "fld_x",
            request_timeout = 30,
            max_retries = 1,
            retry_backoff = 0.1,
            image_url_template = "https://example.com/{token}",
            feishu_message_max_bytes = 18000,
            feishu_convert_max_bytes = 45000,
            notify_level = "none"
        )
        writer = NavDocWriter()
        orchestrator = ImportOrchestrator(
            source_adapter = OrderedSource(),
            markdown_processor = MarkdownProcessor(),
            config = config,
            doc_writer = writer,
            media_service = FakeMedia(),
            wiki_service = None,
            notify_service = None,
            llm_client = FakeLlmFolderNav()
        )

        result = orchestrator.run(
            space_name = "",
            space_id = "",
            chat_id = "",
            dry_run = False,
            notify_level = "none",
            write_mode = "folder",
            structure_order = "path",
            folder_subdirs = True,
            folder_nav_doc = True
        )

        self.assertEqual(result.success, 2)
        self.assertEqual(result.failed, 0)
        self.assertIn("[Chapter 1](https://example.com/doc_ch1)", writer.nav_markdown)
        self.assertIn("document_id: `doc_ch2`", writer.nav_markdown)

    def test_folder_navigation_llm_prefers_root_readme_context(self) -> None:
        """LLM folder nav should use root README context before TOC content.

        Args:
            self: Test case instance.
        """

        config = AppConfig(
            feishu_base_url = "https://open.feishu.cn",
            feishu_webhook_url = "",
            feishu_app_id = "w",
            feishu_app_secret = "w",
            feishu_user_access_token = "",
            feishu_user_refresh_token = "",
            feishu_user_token_cache_path = "cache/user_token.json",
            feishu_folder_token = "fld_x",
            request_timeout = 30,
            max_retries = 1,
            retry_backoff = 0.1,
            image_url_template = "https://example.com/{token}",
            feishu_message_max_bytes = 18000,
            feishu_convert_max_bytes = 45000,
            notify_level = "none"
        )
        llm = CaptureContextLlmFolderNav()
        writer = NavDocWriter()
        orchestrator = ImportOrchestrator(
            source_adapter = ReadmePreferredSource(),
            markdown_processor = MarkdownProcessor(),
            config = config,
            doc_writer = writer,
            media_service = FakeMedia(),
            wiki_service = None,
            notify_service = None,
            llm_client = llm
        )

        result = orchestrator.run(
            space_name = "",
            space_id = "",
            chat_id = "",
            dry_run = False,
            notify_level = "none",
            write_mode = "folder",
            structure_order = "path",
            folder_subdirs = True,
            folder_nav_doc = True
        )

        self.assertEqual(result.failed, 0)
        self.assertIn("Root Readme Context", llm.context_markdown)
        self.assertNotIn("TOC Context", llm.context_markdown)

    def test_folder_navigation_llm_empty_output_skips_navigation_doc(self) -> None:
        """Empty LLM output should skip creating folder navigation doc.

        Args:
            self: Test case instance.
        """

        config = AppConfig(
            feishu_base_url = "https://open.feishu.cn",
            feishu_webhook_url = "",
            feishu_app_id = "w",
            feishu_app_secret = "w",
            feishu_user_access_token = "",
            feishu_user_refresh_token = "",
            feishu_user_token_cache_path = "cache/user_token.json",
            feishu_folder_token = "fld_x",
            request_timeout = 30,
            max_retries = 1,
            retry_backoff = 0.1,
            image_url_template = "https://example.com/{token}",
            feishu_message_max_bytes = 18000,
            feishu_convert_max_bytes = 45000,
            notify_level = "none"
        )
        writer = NavDocWriter()
        orchestrator = ImportOrchestrator(
            source_adapter = OrderedSource(),
            markdown_processor = MarkdownProcessor(),
            config = config,
            doc_writer = writer,
            media_service = FakeMedia(),
            wiki_service = None,
            notify_service = None,
            llm_client = EmptyLlmFolderNav()
        )

        result = orchestrator.run(
            space_name = "",
            space_id = "",
            chat_id = "",
            dry_run = False,
            notify_level = "none",
            write_mode = "folder",
            structure_order = "path",
            folder_subdirs = True,
            folder_nav_doc = True
        )

        self.assertEqual(result.success, 2)
        self.assertEqual(result.failed, 0)
        self.assertEqual(writer.nav_markdown, "")
        self.assertNotIn("00-导航总目录", writer.created_titles)

    def test_run_uses_grouped_multiprocess_when_max_workers_gt_one(self) -> None:
        """Run should route into grouped multiprocess branch when max_workers > 1.

        Args:
            self: Test case instance.
        """

        config = AppConfig(
            feishu_base_url = "https://open.feishu.cn",
            feishu_webhook_url = "",
            feishu_app_id = "w",
            feishu_app_secret = "w",
            feishu_user_access_token = "",
            feishu_user_refresh_token = "",
            feishu_user_token_cache_path = "cache/user_token.json",
            feishu_folder_token = "fld_x",
            request_timeout = 30,
            max_retries = 1,
            retry_backoff = 0.1,
            image_url_template = "https://example.com/{token}",
            feishu_message_max_bytes = 18000,
            feishu_convert_max_bytes = 45000,
            notify_level = "none"
        )
        orchestrator = ImportOrchestrator(
            source_adapter = OrderedSource(),
            markdown_processor = MarkdownProcessor(),
            config = config,
            doc_writer = FakeDocWriter(),
            media_service = FakeMedia(),
            wiki_service = None,
            notify_service = None
        )
        mocked_outcome = {
            "success": 1,
            "failures": [ImportFailure(path = "b/ch2.md", reason = "simulated")],
            "created_docs": [
                CreatedDocRecord(
                    path = "a/ch1.md",
                    title = "Chapter 1",
                    document_id = "doc_ch1",
                    doc_url = "https://example.com/doc_ch1",
                    wiki_node_token = ""
                )
            ]
        }

        with mock.patch.object(
            orchestrator,
            "_run_grouped_multiprocess_import",
            return_value = mocked_outcome
        ) as mocked_run:
            result = orchestrator.run(
                space_name = "",
                space_id = "",
                chat_id = "",
                dry_run = False,
                notify_level = "none",
                write_mode = "folder",
                structure_order = "path",
                folder_nav_doc = False,
                max_workers = 2
            )

        mocked_run.assert_called_once()
        self.assertEqual(result.success, 1)
        self.assertEqual(result.failed, 1)
        self.assertEqual(result.failures[0].path, "b/ch2.md")

    def test_grouped_multiprocess_keyboard_interrupt_terminates_pool(self) -> None:
        """KeyboardInterrupt in grouped import should terminate process pool immediately.

        Args:
            self: Test case instance.
        """

        config = AppConfig(
            feishu_base_url = "https://open.feishu.cn",
            feishu_webhook_url = "",
            feishu_app_id = "w",
            feishu_app_secret = "w",
            feishu_user_access_token = "",
            feishu_user_refresh_token = "",
            feishu_user_token_cache_path = "cache/user_token.json",
            feishu_folder_token = "fld_x",
            request_timeout = 30,
            max_retries = 1,
            retry_backoff = 0.1,
            image_url_template = "https://example.com/{token}",
            feishu_message_max_bytes = 18000,
            feishu_convert_max_bytes = 45000,
            notify_level = "none"
        )
        orchestrator = ImportOrchestrator(
            source_adapter = OrderedSource(),
            markdown_processor = MarkdownProcessor(),
            config = config,
            doc_writer = FakeDocWriter(),
            media_service = FakeMedia(),
            wiki_service = None,
            notify_service = None
        )

        manifest = ImportManifest(
            items = [
                DocumentPlanItem(
                    path = "a/ch1.md",
                    order = 0,
                    is_index = False,
                    relative_dir = "a",
                    toc_label = ""
                )
            ]
        )
        snapshots = {
            "a/ch1.md": SourceDocument(
                path = "a/ch1.md",
                title = "Chapter 1",
                markdown = "# Chapter 1",
                assets = [],
                relative_dir = "a",
                base_ref = "/tmp",
                source_type = "local"
            )
        }

        fake_executor = mock.Mock()
        fake_executor.submit.side_effect = lambda *args, **kwargs: mock.Mock()

        with mock.patch.object(
            orchestrator,
            "_build_doc_snapshots",
            return_value = (snapshots, [])
        ), mock.patch.object(
            orchestrator,
            "_build_folder_token_by_path",
            return_value = {"a/ch1.md": "folder_a"}
        ), mock.patch.object(
            orchestrator,
            "_build_wiki_parent_by_path",
            return_value = {}
        ), mock.patch(
            "core.orchestrator.ProcessPoolExecutor",
            return_value = fake_executor
        ), mock.patch(
            "core.orchestrator.as_completed",
            side_effect = KeyboardInterrupt()
        ), mock.patch.object(
            orchestrator,
            "_terminate_process_pool"
        ) as terminate_mock:
            with self.assertRaises(KeyboardInterrupt):
                orchestrator._run_grouped_multiprocess_import(
                    manifest = manifest,
                    write_mode = "folder",
                    space_id = "",
                    folder_subdirs = True,
                    folder_root_relative_dir = "",
                    folder_root_token = "",
                    max_workers = 2,
                    chunk_workers = 2,
                    chat_id = "",
                    notify_level = "none"
                )

        terminate_mock.assert_called_once_with(executor = fake_executor)

    def test_grouped_multiprocess_collects_success_and_failure(self) -> None:
        """Grouped multiprocess should isolate one group failure from others.

        Args:
            self: Test case instance.
        """

        config = AppConfig(
            feishu_base_url = "https://open.feishu.cn",
            feishu_webhook_url = "",
            feishu_app_id = "w",
            feishu_app_secret = "w",
            feishu_user_access_token = "",
            feishu_user_refresh_token = "",
            feishu_user_token_cache_path = "cache/user_token.json",
            feishu_folder_token = "fld_x",
            request_timeout = 30,
            max_retries = 1,
            retry_backoff = 0.1,
            image_url_template = "https://example.com/{token}",
            feishu_message_max_bytes = 18000,
            feishu_convert_max_bytes = 45000,
            notify_level = "none"
        )
        orchestrator = ImportOrchestrator(
            source_adapter = OrderedSource(),
            markdown_processor = MarkdownProcessor(),
            config = config,
            doc_writer = FakeDocWriter(),
            media_service = FakeMedia(),
            wiki_service = None,
            notify_service = None
        )
        manifest = ImportManifest(
            items = [
                DocumentPlanItem(
                    path = "a/ch1.md",
                    order = 0,
                    is_index = False,
                    relative_dir = "a",
                    toc_label = ""
                ),
                DocumentPlanItem(
                    path = "b/ch2.md",
                    order = 1,
                    is_index = False,
                    relative_dir = "b",
                    toc_label = ""
                )
            ]
        )
        snapshots = {
            "a/ch1.md": SourceDocument(
                path = "a/ch1.md",
                title = "Chapter 1",
                markdown = "# Chapter 1",
                assets = [],
                relative_dir = "a",
                base_ref = "/tmp",
                source_type = "local"
            ),
            "b/ch2.md": SourceDocument(
                path = "b/ch2.md",
                title = "Chapter 2",
                markdown = "# Chapter 2",
                assets = [],
                relative_dir = "b",
                base_ref = "/tmp",
                source_type = "local"
            )
        }

        future_success = mock.Mock()
        future_failure = mock.Mock()
        future_success.result.return_value = {
            "success": 1,
            "failures": [],
            "created_docs": [
                {
                    "path": "a/ch1.md",
                    "title": "Chapter 1",
                    "document_id": "doc_ch1",
                    "doc_url": "https://example.com/doc_ch1",
                    "wiki_node_token": ""
                }
            ]
        }
        future_failure.result.side_effect = RuntimeError("group failed")

        fake_executor = mock.Mock()
        fake_executor.submit.side_effect = [future_success, future_failure]

        with mock.patch.object(
            orchestrator,
            "_build_doc_snapshots",
            return_value = (snapshots, [])
        ), mock.patch.object(
            orchestrator,
            "_build_folder_token_by_path",
            return_value = {
                "a/ch1.md": "folder_a",
                "b/ch2.md": "folder_b"
            }
        ), mock.patch.object(
            orchestrator,
            "_build_wiki_parent_by_path",
            return_value = {}
        ), mock.patch(
            "core.orchestrator.ProcessPoolExecutor",
            return_value = fake_executor
        ), mock.patch(
            "core.orchestrator.as_completed",
            return_value = [future_success, future_failure]
        ):
            outcome = orchestrator._run_grouped_multiprocess_import(
                manifest = manifest,
                write_mode = "folder",
                space_id = "",
                folder_subdirs = True,
                folder_root_relative_dir = "",
                folder_root_token = "",
                max_workers = 2,
                chunk_workers = 2,
                chat_id = "",
                notify_level = "none"
            )

        self.assertEqual(outcome["success"], 1)
        self.assertEqual(len(outcome["created_docs"]), 1)
        self.assertEqual(len(outcome["failures"]), 1)
        self.assertEqual(outcome["failures"][0].path, "group:b")

    def test_group_items_by_top_dir(self) -> None:
        """Top directory grouping should keep first-seen group order.

        Args:
            self: Test case instance.
        """

        config = AppConfig(
            feishu_base_url = "https://open.feishu.cn",
            feishu_webhook_url = "",
            feishu_app_id = "w",
            feishu_app_secret = "w",
            feishu_user_access_token = "",
            feishu_user_refresh_token = "",
            feishu_user_token_cache_path = "cache/user_token.json",
            feishu_folder_token = "fld_x",
            request_timeout = 30,
            max_retries = 1,
            retry_backoff = 0.1,
            image_url_template = "https://example.com/{token}",
            feishu_message_max_bytes = 18000,
            feishu_convert_max_bytes = 45000,
            notify_level = "none"
        )
        orchestrator = ImportOrchestrator(
            source_adapter = OrderedSource(),
            markdown_processor = MarkdownProcessor(),
            config = config,
            doc_writer = FakeDocWriter(),
            media_service = FakeMedia(),
            wiki_service = None,
            notify_service = None
        )
        items = [
            DocumentPlanItem(
                path = "a/ch1.md",
                order = 0,
                is_index = False,
                relative_dir = "a"
            ),
            DocumentPlanItem(
                path = "b/ch2.md",
                order = 1,
                is_index = False,
                relative_dir = "b"
            ),
            DocumentPlanItem(
                path = "README.md",
                order = 2,
                is_index = True,
                relative_dir = ""
            )
        ]

        grouped = orchestrator._group_items_by_top_dir(items = items)
        self.assertEqual([key for key, _ in grouped], ["a", "b", "__root__"])


if __name__ == "__main__":
    unittest.main()
