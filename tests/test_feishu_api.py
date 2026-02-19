import json
import tempfile
import unittest

from integrations.feishu_api import DocWriterService
from integrations.feishu_api import FeishuServiceBase
from integrations.feishu_api import FeishuUserTokenManager
from integrations.feishu_api import WikiService
from integrations.feishu_api import WebhookNotifyService
from core.exceptions import ApiResponseError
from core.exceptions import HttpRequestError


class FakeAuthClient:
    """Fake auth client returning static token."""

    def get_tenant_access_token(self) -> str:
        """Return fake token.

        Args:
            self: Fake auth instance.
        """

        return "token_x"


class FakeResponse:
    """Fake HTTP response with json payload."""

    def __init__(self, payload: dict):
        self._payload = payload

    def json(self) -> dict:
        """Return payload.

        Args:
            self: Fake response instance.
        """

        return self._payload

    @property
    def text(self) -> str:
        """Return payload text.

        Args:
            self: Fake response instance.
        """

        return str(self._payload)


class FakeHttpClient:
    """Fake HTTP client recording request calls."""

    def __init__(self):
        self.calls = []
        self.fail_once_invalid_token = False
        self.fail_once_folder_contention = False
        self.fail_convert = False
        self.fail_once_schema_mismatch_children = False
        self.fail_once_schema_mismatch_descendant = False
        self.folder_children = {
            "fld_root": [
                {
                    "name": "existing",
                    "token": "fld_existing",
                    "type": "folder"
                },
                {
                    "name": "doc_a",
                    "token": "doc_foo",
                    "type": "docx"
                }
            ],
            "fld_existing": []
        }

    def request(self, **kwargs):
        """Capture request args and return fake payload.

        Args:
            self: Fake client instance.
            kwargs: Request fields.
        """

        self.calls.append(kwargs)
        url = kwargs.get("url", "")
        headers = kwargs.get("headers", {})
        auth_header = headers.get("Authorization", "")
        if self.fail_once_invalid_token and url.endswith("/open-apis/wiki/v2/spaces") and kwargs.get("method") == "POST":
            if auth_header == "Bearer expired_token":
                self.fail_once_invalid_token = False
                raise HttpRequestError(
                    "HTTP 400 for POST /open-apis/wiki/v2/spaces: "
                    "{\"code\":99991663,\"msg\":\"Invalid access token\"}"
                )
        if url.endswith("/open-apis/authen/v2/oauth/token"):
            body = kwargs.get("json_body", {})
            if body.get("grant_type") == "refresh_token":
                if body.get("refresh_token") == "refresh_ok":
                    return FakeResponse(
                        {
                            "access_token": "access_new",
                            "refresh_token": "refresh_new",
                            "expires_in": 7200
                        }
                    )
                return FakeResponse(
                    {
                        "error": "invalid_grant",
                        "error_description": "The refresh token provided is invalid."
                    }
                )
            if body.get("grant_type") == "authorization_code":
                return FakeResponse(
                    {
                        "access_token": "access_from_code",
                        "refresh_token": "refresh_from_code",
                        "expires_in": 7200
                    }
                )
        if "/open-apis/docx/v1/documents/blocks/convert" in url:
            if self.fail_convert:
                return FakeResponse(
                    {
                        "code": 99990001,
                        "msg": "convert disabled"
                    }
                )
            return FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "first_level_block_ids": [
                            "tmp_txt",
                            "tmp_img"
                        ],
                        "blocks": [
                            {
                                "block_id": "tmp_txt",
                                "block_type": 2,
                                "text": {
                                    "elements": [
                                        {
                                            "text_run": {
                                                "content": "demo"
                                            }
                                        }
                                    ]
                                }
                            },
                            {
                                "block_id": "tmp_img",
                                "block_type": 27,
                                "image": {
                                    "width": 640,
                                    "height": 360
                                }
                            }
                        ],
                        "block_id_to_image_urls": [
                            {
                                "block_id": "tmp_img",
                                "image_url": "./a.png"
                            }
                        ]
                    }
                }
            )
        if "/open-apis/docx/v1/documents/" in url and "/descendant" in url:
            if self.fail_once_schema_mismatch_descendant:
                self.fail_once_schema_mismatch_descendant = False
                return FakeResponse(
                    {
                        "code": 1770006,
                        "msg": "schema mismatch"
                    }
                )
            return FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "children": [],
                        "block_id_relations": [
                            {
                                "temporary_block_id": "tmp_txt",
                                "block_id": "blk_txt_1"
                            },
                            {
                                "temporary_block_id": "tmp_img",
                                "block_id": "blk_img_1"
                            }
                        ]
                    }
                }
            )
        if "/open-apis/docx/v1/documents/" in url and "/children" in url:
            if self.fail_once_schema_mismatch_children:
                self.fail_once_schema_mismatch_children = False
                return FakeResponse(
                    {
                        "code": 1770006,
                        "msg": "schema mismatch"
                    }
                )
            return FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "children": []
                    }
                }
            )
        if url.endswith("/open-apis/drive/v1/files") and kwargs.get("method") == "GET":
            params = kwargs.get("params", {}) or {}
            folder_token = params.get("folder_token", "")
            files = self.folder_children.get(folder_token, [])
            return FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "files": files,
                        "has_more": False
                    }
                }
            )
        if url.endswith("/open-apis/drive/v1/files/create_folder") and kwargs.get("method") == "POST":
            body = kwargs.get("json_body", {}) or {}
            name = body.get("name", "")
            parent_token = body.get("folder_token", "")
            if self.fail_once_folder_contention:
                self.fail_once_folder_contention = False
                return FakeResponse(
                    {
                        "code": 1061045,
                        "msg": "resource contention occurred, please retry."
                    }
                )
            token = f"fld_{name}"
            self.folder_children.setdefault(parent_token, []).append(
                {
                    "name": name,
                    "token": token,
                    "type": "folder"
                }
            )
            self.folder_children.setdefault(token, [])
            return FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "token": token
                    }
                }
            )
        if url.endswith("/open-apis/wiki/v2/spaces") and kwargs.get("method") == "GET":
            return FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "items": [],
                        "has_more": False
                    }
                }
            )
        if url.endswith("/open-apis/wiki/v2/spaces") and kwargs.get("method") == "POST":
            return FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "space": {
                            "space_id": "space_created"
                        }
                    }
                }
            )
        if "/open-apis/wiki/v2/spaces/" in url and "/move_docs_to_wiki" in url:
            return FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "wiki_token": "wiki_node_1"
                    }
                }
            )
        return FakeResponse({"code": 0, "data": {"document_id": "doc_1"}})


class DemoService(FeishuServiceBase):
    """Concrete helper to test base request behavior."""

    def ping(self) -> dict:
        """Call one fake endpoint.

        Args:
            self: Service instance.
        """

        return self._request_json(method = "GET", path = "/open-apis/demo")


class TestFeishuApiOptimizations(unittest.TestCase):
    """Tests for Feishu integration optimizations."""

    def test_authorization_header_injected(self) -> None:
        """Base request should include Bearer token header.

        Args:
            self: Test case instance.
        """

        http_client = FakeHttpClient()
        service = DemoService(
            auth_client = FakeAuthClient(),
            http_client = http_client,
            base_url = "https://open.feishu.cn"
        )

        service.ping()
        self.assertEqual(len(http_client.calls), 1)
        headers = http_client.calls[0].get("headers", {})
        self.assertEqual(headers.get("Authorization"), "Bearer token_x")

    def test_doc_convert_chunked_by_bytes(self) -> None:
        """Doc conversion should split large markdown into multiple calls.

        Args:
            self: Test case instance.
        """

        http_client = FakeHttpClient()
        doc_writer = DocWriterService(
            auth_client = FakeAuthClient(),
            http_client = http_client,
            base_url = "https://open.feishu.cn",
            folder_token = "fld_x",
            convert_max_bytes = 20
        )

        markdown = "line1\n![a](./a.png)\nline2\nline3\nline4\n"
        handled_images = []
        doc_writer.convert_markdown(
            document_id = "doc_x",
            content = markdown,
            image_token_map = {"./a.png": "token_a"},
            image_block_handler = lambda image_url, block_id: handled_images.append((image_url, block_id))
        )

        convert_calls = [
            call for call in http_client.calls
            if "/open-apis/docx/v1/documents/blocks/convert" in call.get("url", "")
        ]
        descendant_calls = [
            call for call in http_client.calls
            if "/open-apis/docx/v1/documents/" in call.get("url", "") and "/descendant" in call.get("url", "")
        ]

        self.assertGreaterEqual(len(convert_calls), 2)
        self.assertEqual(len(convert_calls), len(descendant_calls))

        for call in convert_calls:
            body = call.get("json_body", {})
            self.assertLessEqual(len(body.get("content", "").encode("utf-8")), 20)

        for call in descendant_calls:
            body = call.get("json_body", {})
            descendants = body.get("descendants", [])
            image_blocks = [
                block for block in descendants
                if isinstance(block, dict) and isinstance(block.get("image"), dict)
            ]
            self.assertTrue(image_blocks)

        self.assertEqual(len(handled_images), len(descendant_calls))
        for image_url, block_id in handled_images:
            self.assertEqual(image_url, "./a.png")
            self.assertTrue(block_id)

    def test_write_markdown_by_semantic_blocks(self) -> None:
        """Markdown write should convert by semantic blocks.

        Args:
            self: Test case instance.
        """

        http_client = FakeHttpClient()
        doc_writer = DocWriterService(
            auth_client = FakeAuthClient(),
            http_client = http_client,
            base_url = "https://open.feishu.cn",
            folder_token = "fld_x",
            convert_max_bytes = 4000
        )

        markdown = (
            "# Title\n\n"
            "Paragraph with **bold**.\n\n"
            "| A | B |\n"
            "| --- | --- |\n"
            "| 1 | 2 |\n\n"
            "```python\n"
            "print('x')\n"
            "```\n"
        )
        doc_writer.write_markdown_with_fallback(
            document_id = "doc_x",
            content = markdown
        )

        convert_calls = [
            call for call in http_client.calls
            if "/open-apis/docx/v1/documents/blocks/convert" in call.get("url", "")
        ]
        self.assertGreaterEqual(len(convert_calls), 3)

    def test_write_markdown_by_semantic_blocks_with_chunk_workers(self) -> None:
        """Chunk worker option should keep stable semantic block write behavior.

        Args:
            self: Test case instance.
        """

        http_client = FakeHttpClient()
        doc_writer = DocWriterService(
            auth_client = FakeAuthClient(),
            http_client = http_client,
            base_url = "https://open.feishu.cn",
            folder_token = "fld_x",
            convert_max_bytes = 4000,
            chunk_workers = 4
        )
        self.assertEqual(doc_writer.chunk_workers, 4)

        markdown = (
            "# Title\n\n"
            "Paragraph with **bold**.\n\n"
            "```python\n"
            "print('x')\n"
            "```\n"
        )
        doc_writer.write_markdown_with_fallback(
            document_id = "doc_x",
            content = markdown
        )

        convert_calls = [
            call for call in http_client.calls
            if "/open-apis/docx/v1/documents/blocks/convert" in call.get("url", "")
        ]
        self.assertGreaterEqual(len(convert_calls), 2)
        convert_contents = [
            call.get("json_body", {}).get("content", "")
            for call in convert_calls
        ]
        self.assertIn("# Title", convert_contents[0])
        self.assertIn("print('x')", "".join(convert_contents))

    def test_native_children_retry_on_schema_mismatch(self) -> None:
        """Native children append should retry when API returns schema mismatch once.

        Args:
            self: Test case instance.
        """

        http_client = FakeHttpClient()
        http_client.fail_once_schema_mismatch_children = True
        doc_writer = DocWriterService(
            auth_client = FakeAuthClient(),
            http_client = http_client,
            base_url = "https://open.feishu.cn",
            folder_token = "fld_x"
        )

        doc_writer.write_markdown_by_native_blocks(
            document_id = "doc_x",
            content = "# Title"
        )

        children_calls = [
            call for call in http_client.calls
            if "/open-apis/docx/v1/documents/" in call.get("url", "")
            and "/children" in call.get("url", "")
        ]
        self.assertGreaterEqual(len(children_calls), 2)

    def test_descendant_retry_on_schema_mismatch(self) -> None:
        """Descendant append should retry when API returns schema mismatch once.

        Args:
            self: Test case instance.
        """

        http_client = FakeHttpClient()
        http_client.fail_once_schema_mismatch_descendant = True
        doc_writer = DocWriterService(
            auth_client = FakeAuthClient(),
            http_client = http_client,
            base_url = "https://open.feishu.cn",
            folder_token = "fld_x"
        )

        doc_writer.convert_markdown(
            document_id = "doc_x",
            content = "hello world"
        )

        descendant_calls = [
            call for call in http_client.calls
            if "/open-apis/docx/v1/documents/" in call.get("url", "")
            and "/descendant" in call.get("url", "")
        ]
        self.assertGreaterEqual(len(descendant_calls), 2)

    def test_relative_link_downgraded_in_native_inline_parser(self) -> None:
        """Relative markdown links should be downgraded to plain text for native blocks.

        Args:
            self: Test case instance.
        """

        http_client = FakeHttpClient()
        doc_writer = DocWriterService(
            auth_client = FakeAuthClient(),
            http_client = http_client,
            base_url = "https://open.feishu.cn",
            folder_token = "fld_x"
        )

        elements = doc_writer._build_text_elements_from_markdown(
            text = "See [local](./a.md) and [web](https://example.com)."
        )
        local_runs = [
            element.get("text_run", {})
            for element in elements
            if element.get("text_run", {}).get("content") == "local"
        ]
        web_runs = [
            element.get("text_run", {})
            for element in elements
            if element.get("text_run", {}).get("content") == "web"
        ]

        self.assertTrue(local_runs)
        self.assertTrue(web_runs)
        self.assertNotIn("text_element_style", local_runs[0])
        self.assertEqual(
            web_runs[0].get("text_element_style", {}).get("link", {}).get("url"),
            "https://example.com"
        )

    def test_native_block_fallback_when_convert_fails(self) -> None:
        """Convert failure should fallback to native blocks instead of raw markdown.

        Args:
            self: Test case instance.
        """

        http_client = FakeHttpClient()
        http_client.fail_convert = True
        doc_writer = DocWriterService(
            auth_client = FakeAuthClient(),
            http_client = http_client,
            base_url = "https://open.feishu.cn",
            folder_token = "fld_x",
            convert_max_bytes = 4000
        )

        markdown = (
            "# Title\n\n"
            "Paragraph with **bold** and [link](https://example.com).\n\n"
            "- item one\n"
            "1. ordered one\n"
            "> quoted\n\n"
            "| A | B |\n"
            "| --- | --- |\n"
            "| **x** | y |\n"
        )
        doc_writer.write_markdown_with_fallback(
            document_id = "doc_x",
            content = markdown
        )

        convert_calls = [
            call for call in http_client.calls
            if "/open-apis/docx/v1/documents/blocks/convert" in call.get("url", "")
        ]
        self.assertGreaterEqual(len(convert_calls), 1)

        children_calls = [
            call for call in http_client.calls
            if "/open-apis/docx/v1/documents/doc_x/blocks/doc_x/children" in call.get("url", "")
            and call.get("method") == "POST"
        ]
        self.assertGreaterEqual(len(children_calls), 1)

        written_blocks = []
        for call in children_calls:
            body = call.get("json_body", {}) or {}
            written_blocks.extend(body.get("children", []))

        self.assertTrue(any(block.get("block_type") == 3 for block in written_blocks))
        self.assertTrue(any("heading1" in block for block in written_blocks))

        has_bold = False
        has_link = False
        for block in written_blocks:
            for field_name in [
                "text",
                "heading1",
                "heading2",
                "heading3",
                "bullet",
                "ordered",
                "quote"
            ]:
                payload = block.get(field_name, {})
                elements = payload.get("elements", [])
                for element in elements:
                    style = ((element.get("text_run") or {}).get("text_element_style") or {})
                    if style.get("bold"):
                        has_bold = True
                    link = style.get("link", {})
                    if isinstance(link, dict) and link.get("url"):
                        has_link = True
        self.assertTrue(has_bold)
        self.assertTrue(has_link)

    def test_ensure_folder_path_creates_missing_segments(self) -> None:
        """Folder hierarchy should reuse existing and create missing folders.

        Args:
            self: Test case instance.
        """

        http_client = FakeHttpClient()
        doc_writer = DocWriterService(
            auth_client = FakeAuthClient(),
            http_client = http_client,
            base_url = "https://open.feishu.cn",
            folder_token = "fld_root",
            convert_max_bytes = 20
        )

        folder_token = doc_writer.ensure_folder_path(relative_dir = "existing/new_leaf")
        self.assertEqual(folder_token, "fld_new_leaf")

        create_folder_calls = [
            call for call in http_client.calls
            if call.get("url", "").endswith("/open-apis/drive/v1/files/create_folder")
        ]
        self.assertEqual(len(create_folder_calls), 1)
        self.assertEqual(
            (create_folder_calls[0].get("json_body") or {}).get("folder_token"),
            "fld_existing"
        )

    def test_ensure_folder_path_retry_on_contention(self) -> None:
        """Folder creation should retry when API returns contention code.

        Args:
            self: Test case instance.
        """

        http_client = FakeHttpClient()
        http_client.fail_once_folder_contention = True
        doc_writer = DocWriterService(
            auth_client = FakeAuthClient(),
            http_client = http_client,
            base_url = "https://open.feishu.cn",
            folder_token = "fld_root",
            convert_max_bytes = 20
        )

        folder_token = doc_writer.ensure_folder_path(relative_dir = "retry_me")
        self.assertEqual(folder_token, "fld_retry_me")

        create_folder_calls = [
            call for call in http_client.calls
            if call.get("url", "").endswith("/open-apis/drive/v1/files/create_folder")
        ]
        self.assertEqual(len(create_folder_calls), 2)

    def test_ensure_folder_name_truncated_by_bytes(self) -> None:
        """Folder segment should be truncated to API byte limit.

        Args:
            self: Test case instance.
        """

        http_client = FakeHttpClient()
        doc_writer = DocWriterService(
            auth_client = FakeAuthClient(),
            http_client = http_client,
            base_url = "https://open.feishu.cn",
            folder_token = "fld_root",
            convert_max_bytes = 20
        )

        long_name = "测" * 120
        doc_writer.ensure_folder_path(relative_dir = long_name)

        create_folder_calls = [
            call for call in http_client.calls
            if call.get("url", "").endswith("/open-apis/drive/v1/files/create_folder")
        ]
        self.assertEqual(len(create_folder_calls), 1)
        sent_name = (create_folder_calls[0].get("json_body") or {}).get("name", "")
        self.assertTrue(sent_name)
        self.assertLessEqual(len(sent_name.encode("utf-8")), 256)

    def test_webhook_notify_chunked(self) -> None:
        """Webhook notification should split overlong messages.

        Args:
            self: Test case instance.
        """

        http_client = FakeHttpClient()
        notify = WebhookNotifyService(
            webhook_url = "https://example.com/webhook",
            http_client = http_client,
            max_bytes = 10
        )

        notify.send_status(chat_id = "", message = "abcdefghijk")
        self.assertEqual(len(http_client.calls), 2)

    def test_wiki_create_space_requires_user_token(self) -> None:
        """Create space should fail without user access token.

        Args:
            self: Test case instance.
        """

        http_client = FakeHttpClient()
        wiki_service = WikiService(
            auth_client = FakeAuthClient(),
            http_client = http_client,
            base_url = "https://open.feishu.cn",
            user_access_token = ""
        )

        with self.assertRaises(ApiResponseError):
            wiki_service.get_or_create_space(space_name = "demo")

    def test_wiki_create_space_uses_user_token(self) -> None:
        """Create space should use explicit user token header.

        Args:
            self: Test case instance.
        """

        http_client = FakeHttpClient()
        wiki_service = WikiService(
            auth_client = FakeAuthClient(),
            http_client = http_client,
            base_url = "https://open.feishu.cn",
            user_access_token = "u_user_token"
        )

        space_id = wiki_service.get_or_create_space(space_name = "demo")
        self.assertEqual(space_id, "space_created")

        create_calls = [
            call for call in http_client.calls
            if call.get("url", "").endswith("/open-apis/wiki/v2/spaces") and call.get("method") == "POST"
        ]
        self.assertEqual(len(create_calls), 1)
        headers = create_calls[0].get("headers", {})
        self.assertEqual(headers.get("Authorization"), "Bearer u_user_token")

    def test_wiki_move_doc_payload(self) -> None:
        """Move docs payload should align with wiki API schema.

        Args:
            self: Test case instance.
        """

        http_client = FakeHttpClient()
        wiki_service = WikiService(
            auth_client = FakeAuthClient(),
            http_client = http_client,
            base_url = "https://open.feishu.cn",
            user_access_token = "u_user_token"
        )

        node_token = wiki_service.move_doc_to_wiki(
            space_id = "space_1",
            document_id = "doc_1",
            parent_node_token = "wiki_parent",
            title = "Demo"
        )
        self.assertEqual(node_token, "wiki_node_1")

        move_calls = [
            call for call in http_client.calls
            if "/move_docs_to_wiki" in call.get("url", "")
        ]
        self.assertEqual(len(move_calls), 1)
        body = move_calls[0].get("json_body", {})
        self.assertEqual(body.get("parent_wiki_token"), "wiki_parent")
        self.assertEqual(body.get("obj_type"), "docx")
        self.assertEqual(body.get("obj_token"), "doc_1")
        self.assertEqual(body.get("apply"), True)

    def test_user_token_manager_refresh_and_cache(self) -> None:
        """Refresh token should update access token and cache file.

        Args:
            self: Test case instance.
        """

        with tempfile.TemporaryDirectory() as tmp:
            cache_path = f"{tmp}/token.json"
            manager = FeishuUserTokenManager(
                app_id = "app_x",
                app_secret = "sec_x",
                base_url = "https://open.feishu.cn",
                http_client = FakeHttpClient(),
                access_token = "",
                refresh_token = "refresh_ok",
                cache_path = cache_path
            )

            token = manager.refresh_access_token()
            self.assertEqual(token, "access_new")

            with open(cache_path, "r", encoding = "utf-8") as fp:
                payload = json.load(fp)
            self.assertEqual(payload.get("access_token"), "access_new")
            self.assertEqual(payload.get("refresh_token"), "refresh_new")

    def test_user_token_manager_refresh_when_expired(self) -> None:
        """Expired access token should trigger proactive refresh.

        Args:
            self: Test case instance.
        """

        manager = FeishuUserTokenManager(
            app_id = "app_x",
            app_secret = "sec_x",
            base_url = "https://open.feishu.cn",
            http_client = FakeHttpClient(),
            access_token = "expired_token",
            refresh_token = "refresh_ok",
            cache_path = ""
        )
        manager._expires_at = 1.0

        token = manager.get_access_token(refresh_if_missing = True)
        self.assertEqual(token, "access_new")

    def test_wiki_create_space_auto_refresh_user_token(self) -> None:
        """Wiki create should retry once after auto refreshing user token.

        Args:
            self: Test case instance.
        """

        http_client = FakeHttpClient()
        http_client.fail_once_invalid_token = True
        token_manager = FeishuUserTokenManager(
            app_id = "app_x",
            app_secret = "sec_x",
            base_url = "https://open.feishu.cn",
            http_client = http_client,
            access_token = "expired_token",
            refresh_token = "refresh_ok",
            cache_path = ""
        )
        wiki_service = WikiService(
            auth_client = FakeAuthClient(),
            http_client = http_client,
            base_url = "https://open.feishu.cn",
            user_access_token = "",
            user_token_manager = token_manager
        )

        space_id = wiki_service.get_or_create_space(space_name = "demo")
        self.assertEqual(space_id, "space_created")

        refresh_calls = [
            call for call in http_client.calls
            if call.get("url", "").endswith("/open-apis/authen/v2/oauth/token")
            and (call.get("json_body") or {}).get("grant_type") == "refresh_token"
        ]
        self.assertEqual(len(refresh_calls), 1)

    def test_build_authorize_url_encodes_redirect_uri(self) -> None:
        """Authorize URL should percent-encode redirect_uri parameter.

        Args:
            self: Test case instance.
        """

        manager = FeishuUserTokenManager(
            app_id = "cli_test",
            app_secret = "sec_test",
            base_url = "https://open.feishu.cn",
            http_client = FakeHttpClient(),
            access_token = "",
            refresh_token = "",
            cache_path = ""
        )
        url = manager.build_authorize_url(
            redirect_uri = "http://127.0.0.1:8765/callback",
            scope = "wiki:wiki offline_access",
            state = "state_1"
        )
        self.assertIn(
            "redirect_uri=http%3A%2F%2F127.0.0.1%3A8765%2Fcallback",
            url
        )


if __name__ == "__main__":
    unittest.main()
