# 飞书知识库自动导入器 - API 接口文档

## 概述

这是飞书知识库自动导入器的后端 API 接口文档。后端使用 FastAPI 框架，提供 RESTful API 接口，供前端调用以执行文档导入任务。

## 最新补充（2026-02）

- 新增本地原生选择器接口：`POST /api/sources/local/pick`
  - 请求示例：
    ```json
    {
      "target": "directory",
      "extensions": ["md", "markdown"]
    }
    ```
  - 响应示例：
    ```json
    {
      "path": "/absolute/path/to/docs",
      "target": "directory"
    }
    ```
- 新增浏览器文件选择上传接口：`POST /api/sources/local/upload`
  - 用于接收浏览器选择器（目录/文件）返回的文件集合并保存为服务端临时路径。
- Web 导入请求 `POST /api/import/start` 新增并透传字段：
  - `space_id`, `chat_id`, `subdir`, `structure_order`, `toc_file`,
  - `folder_subdirs`, `folder_root_subdir`, `folder_root_subdir_name`,
  - `folder_nav_doc`, `folder_nav_title`, `llm_fallback`, `llm_max_calls`,
  - `skip_root_readme`, `import_type`
- `skip_root_readme` 默认 `false`：仅在显式开启时跳过根 `README.md/readme.md`，不会过滤根 `index.md`。

## 基础配置

### 服务器信息
- 基础 URL: `http://localhost:8000`
- API 前缀: `/api/v1`
- 文档地址: `http://localhost:8000/docs` (Swagger UI)
- 备用文档: `http://localhost:8000/redoc` (ReDoc)

### 请求格式
- 所有请求使用 `JSON` 格式
- 请求头需包含: `Content-Type: application/json`

### 响应格式
```json
{
  "success": true,
  "message": "操作成功",
  "data": {},
  "code": 200
}
```

## API 接口

### 1. 健康检查

**接口地址**: `GET /api/v1/health`

**功能**: 检查服务状态

**响应示例**:
```json
{
  "success": true,
  "message": "Service is healthy",
  "data": {
    "status": "ok",
    "timestamp": "2024-01-01T12:00:00Z"
  },
  "code": 200
}
```

---

### 2. 获取配置

**接口地址**: `GET /api/v1/config`

**功能**: 获取当前应用配置

**响应示例**:
```json
{
  "success": true,
  "message": "配置获取成功",
  "data": {
    "feishu_app_id": "cli_a1b2c3d4e5f6g7h8",
    "feishu_app_secret": "********************************",
    "feishu_folder_token": "fld1234567890abcdef1234567890abcdef",
    "feishu_webhook_url": "",
    "llm_base_url": "https://api.openai.com/v1",
    "llm_api_key": "sk-********************************"
  },
  "code": 200
}
```

---

### 3. 保存配置

**接口地址**: `POST /api/v1/config`

**功能**: 保存应用配置

**请求参数**:
```json
{
  "feishu_app_id": "cli_a1b2c3d4e5f6g7h8",
  "feishu_app_secret": "********************************",
  "feishu_folder_token": "fld1234567890abcdef1234567890abcdef",
  "feishu_webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/12345678-1234-1234-1234-1234567890abcdef",
  "llm_base_url": "https://api.openai.com/v1",
  "llm_api_key": "sk-********************************",
  "llm_model": "gpt-4"
}
```

**响应示例**:
```json
{
  "success": true,
  "message": "配置保存成功",
  "data": {},
  "code": 200
}
```

---

### 4. 运行导入任务

**接口地址**: `POST /api/v1/import/run`

**功能**: 执行文档导入任务

**请求参数**:
```json
{
  "source": "local",
  "config": {
    "local": {
      "path": "/path/to/docs"
    },
    "github": {
      "repo": "BrenchCC/Context_Engineering_Analysis",
      "ref": "main",
      "subdir": "docs/zh"
    },
    "feishu": {
      "write_mode": "wiki",
      "space_name": "Context Engineering Analysis",
      "space_id": "wki1234567890abcdef1234567890abcdef",
      "chat_id": "oc_1234567890abcdef1234567890abcdef"
    },
    "advanced": {
      "max_workers": 4,
      "chunk_workers": 2,
      "structure_order": "toc_first",
      "toc_file": "TABLE_OF_CONTENTS.md",
      "folder_subdirs": false,
      "folder_nav_doc": true,
      "dry_run": false,
      "oauth_local_server": true,
      "notify_level": "normal",
      "folder_nav_title": "00-导航总目录"
    }
  }
}
```

**响应示例**:
```json
{
  "success": true,
  "message": "任务已启动",
  "data": {
    "task_id": "task_1234567890abcdef1234567890abcdef",
    "status": "running"
  },
  "code": 200
}
```

---

### 5. 获取任务状态

**接口地址**: `GET /api/v1/import/status/{task_id}`

**功能**: 获取任务执行状态

**路径参数**:
- `task_id`: 任务 ID (string)

**响应示例**:
```json
{
  "success": true,
  "message": "状态获取成功",
  "data": {
    "task_id": "task_1234567890abcdef1234567890abcdef",
    "status": "completed",
    "progress": 100,
    "total": 15,
    "success": 12,
    "failed": 1,
    "skipped": 2,
    "start_time": "2024-01-01T12:00:00Z",
    "end_time": "2024-01-01T12:05:30Z",
    "duration": 330
  },
  "code": 200
}
```

---

### 6. 获取任务日志

**接口地址**: `GET /api/v1/import/logs/{task_id}`

**功能**: 获取任务执行日志

**路径参数**:
- `task_id`: 任务 ID (string)

**响应示例**:
```json
{
  "success": true,
  "message": "日志获取成功",
  "data": [
    {
      "timestamp": "2024-01-01T12:00:00Z",
      "level": "INFO",
      "message": "任务开始"
    },
    {
      "timestamp": "2024-01-01T12:00:01Z",
      "level": "INFO",
      "message": "初始化源适配器"
    },
    {
      "timestamp": "2024-01-01T12:00:02Z",
      "level": "INFO",
      "message": "解析源文件结构"
    }
  ],
  "code": 200
}
```

---

### 7. 取消任务

**接口地址**: `POST /api/v1/import/cancel/{task_id}`

**功能**: 取消正在执行的任务

**路径参数**:
- `task_id`: 任务 ID (string)

**响应示例**:
```json
{
  "success": true,
  "message": "任务已取消",
  "data": {
    "task_id": "task_1234567890abcdef1234567890abcdef",
    "status": "cancelled"
  },
  "code": 200
}
```

---

### 8. 获取任务历史

**接口地址**: `GET /api/v1/import/history`

**功能**: 获取任务执行历史

**查询参数**:
- `page`: 页码 (int, 默认: 1)
- `size`: 每页条数 (int, 默认: 10)
- `status`: 任务状态 (string, 可选: running/completed/cancelled/failed)

**响应示例**:
```json
{
  "success": true,
  "message": "历史记录获取成功",
  "data": {
    "tasks": [
      {
        "task_id": "task_1234567890abcdef1234567890abcdef",
        "status": "completed",
        "source": "local",
        "path": "/path/to/docs",
        "total": 15,
        "success": 12,
        "failed": 1,
        "skipped": 2,
        "start_time": "2024-01-01T12:00:00Z",
        "end_time": "2024-01-01T12:05:30Z",
        "duration": 330
      }
    ],
    "page": 1,
    "size": 10,
    "total": 5
  },
  "code": 200
}
```

---

### 9. 测试飞书连接

**接口地址**: `POST /api/v1/feishu/test-connection`

**功能**: 测试飞书 API 连接性

**请求参数**:
```json
{
  "app_id": "cli_a1b2c3d4e5f6g7h8",
  "app_secret": "********************************"
}
```

**响应示例**:
```json
{
  "success": true,
  "message": "连接成功",
  "data": {
    "tenant_access_token": "t-a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0",
    "expire": 7200
  },
  "code": 200
}
```

---

### 10. 获取 OAuth 授权 URL

**接口地址**: `GET /api/v1/feishu/oauth/url`

**功能**: 获取飞书 OAuth 授权 URL

**查询参数**:
- `redirect_uri`: 重定向 URI (string, 可选)
- `scope`: 授权范围 (string, 可选, 默认: "wiki:wiki offline_access")
- `state`: 状态参数 (string, 可选, 默认: "kg_state")

**响应示例**:
```json
{
  "success": true,
  "message": "授权 URL 生成成功",
  "data": {
    "auth_url": "https://open.feishu.cn/open-apis/authen/v1/index?app_id=cli_a1b2c3d4e5f6g7h8&redirect_uri=http%3A%2F%2Flocalhost%3A8765%2Fcallback&scope=wiki%3Awiki+offline_access&state=kg_state"
  },
  "code": 200
}
```

---

### 11. OAuth 回调处理

**接口地址**: `POST /api/v1/feishu/oauth/callback`

**功能**: 处理 OAuth 授权回调

**请求参数**:
```json
{
  "code": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0",
  "state": "kg_state"
}
```

**响应示例**:
```json
{
  "success": true,
  "message": "授权成功",
  "data": {
    "access_token": "u-a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0",
    "refresh_token": "r-a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0",
    "expire": 7200
  },
  "code": 200
}
```

---

## 错误码说明

| 错误码 | 含义 | 说明 |
|--------|------|------|
| 200 | 成功 | 操作成功 |
| 400 | 参数错误 | 请求参数无效或缺失 |
| 401 | 未授权 | 缺少有效的身份验证 |
| 403 | 禁止访问 | 没有权限执行该操作 |
| 404 | 资源不存在 | 请求的资源不存在 |
| 500 | 服务器内部错误 | 服务器处理请求时出错 |
| 501 | 未实现 | 功能尚未实现 |

## 后端实现建议

### 项目结构

```
knowledge_generator/
├── web/
│   ├── index.html
│   ├── styles.css
│   ├── app.js
│   └── api.md
├── api/
│   ├── __init__.py
│   ├── main.py
│   ├── routes/
│   │   ├── import.py
│   │   ├── feishu.py
│   │   └── config.py
│   ├── models/
│   │   ├── import_config.py
│   │   ├── task.py
│   │   └── response.py
│   ├── services/
│   │   ├── import_service.py
│   │   ├── task_manager.py
│   │   └── config_service.py
│   └── dependencies/
│       ├── feishu_auth.py
│       └── task_context.py
├── core/
├── integrations/
└── data/
```

### 核心技术栈

- **FastAPI**: Web 框架
- **Uvicorn**: ASGI 服务器
- **Pydantic**: 数据验证和序列化
- **SQLAlchemy**: 数据库 ORM (可选)
- **Redis**: 任务队列和缓存 (可选)
- **Celery**: 异步任务处理 (可选)

### 快速开始

```bash
# 安装依赖
pip install fastapi uvicorn pydantic python-dotenv

# 启动开发服务器
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# 查看文档
# Swagger UI: http://localhost:8000/docs
# ReDoc: http://localhost:8000/redoc
```

### 部署建议

```bash
# 使用 Gunicorn 生产部署
pip install gunicorn

gunicorn api.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# 使用 Docker 部署
# 构建镜像
docker build -t feishu-import-api .

# 启动容器
docker run -d -p 8000:8000 --name feishu-import-api feishu-import-api
```

## 前端集成说明

### 请求示例 (JavaScript)

```javascript
const API_BASE = 'http://localhost:8000/api/v1';

async function runImport(config) {
  try {
    const response = await fetch(`${API_BASE}/import/run`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(config)
    });

    const result = await response.json();
    return result;
  } catch (error) {
    console.error('API 请求失败:', error);
    throw error;
  }
}

// 使用 SSE 监听任务进度
function listenToTask(taskId, callback) {
  const eventSource = new EventSource(`${API_BASE}/import/stream/${taskId}`);

  eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    callback(data);
  };

  eventSource.onerror = (error) => {
    console.error('SSE 错误:', error);
    eventSource.close();
  };

  return eventSource;
}
```

### 错误处理

```javascript
async function handleApiResponse(response) {
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.message || '请求失败');
  }

  return response.json();
}
```

---

## 版本历史

### v1.0.0 (2024-01-01)
- 基础导入功能
- 任务管理
- 配置管理
- 飞书 API 集成
