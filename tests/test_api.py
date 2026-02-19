"""
API接口测试

测试FastAPI接口的功能和性能
"""

import json
import os
import shutil

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from web.api import sources as source_api
from web.main import app


@pytest.fixture
def client():
    """创建测试客户端"""
    with TestClient(app) as test_client:
        yield test_client


class TestSystemAPI:
    """系统管理API测试"""

    def test_health_check(self, client):
        """测试健康检查接口"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "ok"

    def test_get_system_info(self, client):
        """测试获取系统信息"""
        response = client.get("/api/system/info")
        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        assert "status" in data
        assert "features" in data
        assert data["status"] == "running"
        assert len(data["features"]) > 0

    def test_get_system_config(self, client):
        """测试获取系统配置"""
        response = client.get("/api/system/config")
        assert response.status_code == 200
        data = response.json()
        assert "feishu_app_id" in data
        assert "feishu_app_secret" in data
        assert "feishu_user_access_token" in data
        assert "feishu_user_refresh_token" in data
        assert "feishu_folder_token" in data
        assert "llm_base_url" in data
        assert "llm_api_key" in data
        assert "llm_model" in data


class TestSourcesAPI:
    """源管理API测试"""

    @patch("web.api.sources.LocalSourceAdapter.list_markdown")
    @patch("os.path.exists")
    @patch("os.path.isdir")
    def test_scan_local_directory_success(self, mock_isdir, mock_exists, mock_list, client):
        """测试扫描本地目录成功"""
        # 模拟路径验证
        mock_exists.return_value = True
        mock_isdir.return_value = True

        mock_list.return_value = [
            "docs/01-intro.md",
            "docs/02-quickstart.md"
        ]

        with patch("os.walk") as mock_walk:
            mock_walk.return_value = [
                ("/test/path", ["docs", "docs/images"], ["README.md", "requirements.txt"]),
                ("/test/path/docs", [], ["01-intro.md", "02-quickstart.md"]),
                ("/test/path/docs/images", [], ["logo.png"])
            ]

            response = client.get("/api/sources/local/scan?path=/test/path&recursive=true")
            assert response.status_code == 200
            data = response.json()
            assert data["total_files"] == 2
            assert data["markdown_files"] == 2
            assert data["other_files"] == 0
            assert len(data["files"]) == 2

    def test_scan_local_directory_invalid_path(self, client):
        """测试扫描无效路径"""
        response = client.get("/api/sources/local/scan?path=/invalid/path&recursive=true")
        assert response.status_code == 404

    @patch("web.api.sources.GitHubSourceAdapter")
    def test_clone_github_repo_success(self, mock_adapter, client):
        """测试克隆GitHub仓库成功"""
        # 创建模拟的GitHubSourceAdapter实例
        mock_instance = mock_adapter.return_value
        mock_instance.list_markdown.return_value = [
            "docs/01-intro.md",
            "docs/02-quickstart.md"
        ]

        with patch("os.walk") as mock_walk:
            mock_walk.return_value = [
                ("/tmp/test_repo", ["docs"], ["README.md", "requirements.txt"]),
                ("/tmp/test_repo/docs", [], ["01-intro.md", "02-quickstart.md"])
            ]

            response = client.post("/api/sources/github/clone", json={
                "repo": "BrenchCC/Context_Engineering_Analysis",
                "branch": "main"
            })

            assert response.status_code == 200
            data = response.json()
            assert data["repo"] == "BrenchCC/Context_Engineering_Analysis"
            assert data["branch"] == "main"
            assert len(data["files"]) > 0

    def test_validate_github_repo_success(self, client):
        """测试验证GitHub仓库成功"""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            response = client.post("/api/sources/github/validate", json={
                "repo": "BrenchCC/Context_Engineering_Analysis"
            })

            assert response.status_code == 200
            data = response.json()
            assert "message" in data

    def test_validate_github_repo_invalid_format(self, client):
        """测试验证无效格式的GitHub仓库"""
        response = client.post("/api/sources/github/validate", json={
            "repo": "invalid-repo-format"
        })
        assert response.status_code == 400

    @patch("web.api.sources.pick_local_path")
    def test_pick_local_path_success(self, mock_pick_local_path, client):
        """测试本地路径选择成功"""
        mock_pick_local_path.return_value = "/Users/demo/docs"

        response = client.post("/api/sources/local/pick", json={
            "target": "directory",
            "extensions": ["md", "markdown"]
        })

        assert response.status_code == 200
        data = response.json()
        assert data["path"] == "/Users/demo/docs"
        assert data["target"] == "directory"

    @patch("web.api.sources.pick_local_path")
    def test_pick_local_path_cancelled(self, mock_pick_local_path, client):
        """测试本地路径选择取消"""
        mock_pick_local_path.side_effect = source_api.PickerCancelledError("cancel")

        response = client.post("/api/sources/local/pick", json={
            "target": "directory"
        })

        assert response.status_code == 400
        data = response.json()
        assert "未选择任何路径" in data["detail"]

    @patch("web.api.sources.pick_local_path")
    def test_pick_local_path_unavailable(self, mock_pick_local_path, client):
        """测试无GUI环境下本地路径选择失败"""
        mock_pick_local_path.side_effect = source_api.PickerUnavailableError("headless")

        response = client.post("/api/sources/local/pick", json={
            "target": "file"
        })

        assert response.status_code == 409
        data = response.json()
        assert "无法打开系统选择器" in data["detail"]

    def test_upload_local_directory_success(self, client):
        """测试上传本地目录文件成功"""
        entries = [
            {"relative_path": "docs/a.md"},
            {"relative_path": "docs/sub/b.md"}
        ]
        response = client.post(
            "/api/sources/local/upload",
            data = {
                "target": "directory",
                "entries_json": json.dumps(entries)
            },
            files = [
                ("files", ("a.md", b"# A\n", "text/markdown")),
                ("files", ("b.md", b"# B\n", "text/markdown"))
            ]
        )

        assert response.status_code == 200
        data = response.json()
        assert data["target"] == "directory"
        assert data["file_count"] == 2
        assert os.path.isdir(data["path"])
        assert os.path.isfile(os.path.join(data["path"], "docs", "a.md"))
        assert os.path.isfile(os.path.join(data["path"], "docs", "sub", "b.md"))
        shutil.rmtree(data["path"], ignore_errors = True)

    def test_upload_local_file_success(self, client):
        """测试上传本地单文件成功"""
        entries = [{"relative_path": "single.md"}]
        response = client.post(
            "/api/sources/local/upload",
            data = {
                "target": "file",
                "entries_json": json.dumps(entries)
            },
            files = [
                ("files", ("single.md", b"# Single\n", "text/markdown"))
            ]
        )

        assert response.status_code == 200
        data = response.json()
        assert data["target"] == "file"
        assert data["file_count"] == 1
        assert os.path.isfile(data["path"])
        shutil.rmtree(os.path.dirname(data["path"]), ignore_errors = True)


class TestImportAPI:
    """导入管理API测试"""

    @patch("os.environ.get")
    @patch("web.tasks.import_task.start_import_task")
    @patch("web.models.task.Task")
    @patch("os.path.exists")
    @patch("os.path.isdir")
    def test_start_import_success(self, mock_isdir, mock_exists, mock_task_model, mock_task, mock_env, client):
        """测试启动导入任务成功"""
        # 模拟路径验证
        mock_exists.return_value = True
        mock_isdir.return_value = True

        # 模拟环境变量
        mock_env.return_value = "true"

        # 模拟Task模型
        mock_task_instance = MagicMock()
        mock_task_instance.task_id = "test-task-id"
        mock_task_model.return_value = mock_task_instance

        response = client.post("/api/import/start", json={
            "source_type": "local",
            "path": "/test/path",
            "write_mode": "folder",
            "import_type": "directory",
            "ref": "release-1",
            "space_name": "Test Space",
            "space_id": "space_1",
            "chat_id": "chat_1",
            "structure_order": "path",
            "toc_file": "docs/toc.md",
            "folder_subdirs": True,
            "folder_root_subdir": True,
            "folder_root_subdir_name": "batch_demo",
            "folder_nav_doc": False,
            "folder_nav_title": "导航",
            "llm_fallback": "off",
            "llm_max_calls": 5,
            "skip_root_readme": True,
            "max_workers": 2,
            "chunk_workers": 4,
            "notify_level": "normal",
            "dry_run": False
        })

        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert "status" in data
        assert data["status"] == "started"
        mock_task.delay.assert_called_once()
        _, request_payload = mock_task.delay.call_args[0]
        assert request_payload["skip_root_readme"] == True
        assert request_payload["structure_order"] == "path"
        assert request_payload["folder_subdirs"] == True
        assert request_payload["folder_root_subdir"] == True
        assert request_payload["folder_root_subdir_name"] == "batch_demo"
        assert request_payload["llm_fallback"] == "off"
        assert request_payload["llm_max_calls"] == 5

    @patch("os.environ.get")
    @patch("web.tasks.import_task.start_import_task")
    @patch("web.models.task.Task")
    @patch("os.path.exists")
    @patch("os.path.isdir")
    def test_start_import_invalid_source(self, mock_isdir, mock_exists, mock_task_model, mock_task, mock_env, client):
        """测试启动无效源类型的导入任务"""
        # 模拟路径验证
        mock_exists.return_value = True
        mock_isdir.return_value = True

        # 模拟异步执行
        mock_env.return_value = "true"
        mock_task.delay.side_effect = ValueError("不支持的源类型")

        mock_task_instance = MagicMock()
        mock_task_instance.task_id = "test-task-id"
        mock_task_model.return_value = mock_task_instance

        response = client.post("/api/import/start", json={
            "source_type": "invalid",
            "path": "/test/path",
            "write_mode": "folder"
        })

        assert response.status_code == 500

    @patch("web.models.task.Task.get")
    def test_get_import_status_not_found(self, mock_get, client):
        """测试获取不存在的任务状态"""
        mock_get.return_value = None

        response = client.get("/api/import/status/nonexistent-task-id")
        assert response.status_code == 404


class TestTasksAPI:
    """任务管理API测试"""

    @patch("web.api.tasks.Task.get_all")
    def test_get_tasks(self, mock_get_all, client):
        """测试获取任务列表"""
        mock_tasks = []

        class MockTask:
            def __init__(self, task_id, status):
                self.task_id = task_id
                self.status = status
                self.source_type = "local"
                self.path = "/test/path"
                self.write_mode = "folder"
                self.space_name = "Test Space"
                self.branch = None
                self.commit = None
                self.max_workers = 2
                self.chunk_workers = 4
                self.notify_level = "normal"
                self.dry_run = False
                self.progress = 0
                self.total = 0
                self.success = 0
                self.failed = 0
                self.skipped = 0
                self.start_time = 1630000000
                self.end_time = 1630000100

        mock_tasks.append(MockTask("task1", "completed"))
        mock_tasks.append(MockTask("task2", "running"))
        mock_get_all.return_value = mock_tasks

        response = client.get("/api/tasks/")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["tasks"]) == 2


class TestNotificationsAPI:
    """通知管理API测试"""

    @patch("web.api.notifications.WebhookNotifyService.send_status")
    @patch("web.api.notifications.NotifyService.send_status")
    def test_test_notification(self, mock_chat_notify, mock_webhook_notify, client):
        """测试通知功能"""
        response = client.post("/api/notifications/test", json={
            "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/test",
            "chat_id": "oc_1234567890abcdef1234567890abcdef",
            "level": "normal"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["webhook_sent"] == True
        assert data["chat_id_sent"] == True
        assert "通知测试成功" in data["message"]


class TestAPIErrorHandling:
    """API错误处理测试"""

    def test_non_existent_endpoint(self, client):
        """测试访问不存在的端点"""
        response = client.get("/api/non_existent_endpoint")
        assert response.status_code == 404

    @patch("web.api.sources.LocalSourceAdapter.list_markdown")
    @patch("os.path.exists")
    @patch("os.path.isdir")
    def test_scan_directory_exception(self, mock_isdir, mock_exists, mock_list, client):
        """测试扫描目录异常"""
        # 模拟路径验证
        mock_exists.return_value = True
        mock_isdir.return_value = True

        mock_list.side_effect = Exception("扫描失败")

        response = client.get("/api/sources/local/scan?path=/test/path&recursive=true")
        assert response.status_code == 500
        data = response.json()
        assert "扫描失败" in data["detail"]


if __name__ == "__main__":
    # 运行所有测试
    pytest.main([__file__, "-v"])
