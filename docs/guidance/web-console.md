# Web 控制台使用指南

## 🚀 启动 Web 服务

### 基本启动

```bash
python web/main.py
```

默认监听 `0.0.0.0:8000`。

### 自定义启动参数

可通过环境变量覆盖默认配置：

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `WEB_HOST` | Web 监听地址 | `0.0.0.0` |
| `WEB_PORT` | Web 监听端口 | `8000` |
| `WEB_RELOAD` | 是否热更新 | `true` |
| `WEB_PUBLIC_BASE_URL` | 对外展示访问地址（日志展示） | 自动推断 |

示例：

```bash
WEB_HOST=127.0.0.1 WEB_PORT=9000 python web/main.py
```

## 📁 本地导入（文件/目录自适应）

1. 在 Web 页面选择 `本地目录`。
2. 点击 `浏览`，系统会先尝试文件选择（`.md/.markdown/.docx`），未选择时自动回退到目录选择。
3. 选择后会自动上传到服务端临时目录并填充 `本地路径`，无需手填路径类型。

### 说明

- 单文件导入支持 `.md`、`.markdown` 与 `.docx`。
- 导入 `.docx` 时依赖 `pandoc`，服务端需可执行 `pandoc` 命令。
- 如在无 GUI 环境运行，原生选择器接口会返回 409，请改用手动输入路径。

## ⚙️ Web 高级参数与 CLI 对齐

Web 导入请求会透传以下关键参数，与 CLI 行为一致：

### 源配置
- `ref/branch/subdir`（对应 `--ref/--subdir`）

### 结构配置
- `structure_order/toc_file`（对应 `--structure-order/--toc-file`）
- `folder_subdirs`（对应 `--folder-subdirs`）
- `skip_root_readme`（对应 `--skip-root-readme`，默认关闭）
- `folder_root_subdir`（对应 `--folder-root-subdir`）
- `folder_root_subdir_name`（对应 `--folder-root-subdir-name`，用于自定义任务根子目录名）
- `folder_nav_doc/folder_nav_title`（对应 `--folder-nav-doc/--folder-nav-title`）

### LLM 配置
- `llm_fallback/llm_max_calls`（对应 `--llm-fallback/--llm-max-calls`）

### 并发配置
- `max_workers/chunk_workers`（对应 `--max-workers/--chunk-workers`）

### 通知配置
- `notify_level/dry_run`（对应 `--notify-level/--dry-run`）

## 🔧 curl 快速示例

### 基础操作

先设置基地址：

```bash
BASE_URL="http://127.0.0.1:8000"
```

健康检查：

```bash
curl -s "${BASE_URL}/health"
```

读取当前系统配置：

```bash
curl -s "${BASE_URL}/api/system/config"
```

### 系统配置

更新系统配置（示例）：

```bash
curl -s -X POST "${BASE_URL}/api/system/config" \
  -H "Content-Type: application/json" \
  -d '{
    "feishu_app_id": "cli_xxx",
    "feishu_app_secret": "xxx",
    "feishu_folder_token": "fld_xxx",
    "llm_base_url": "https://api.openai.com/v1",
    "llm_api_key": "sk-xxx",
    "llm_model": "gpt-4o-mini"
  }'
```

### 本地源操作

本地目录扫描：

```bash
curl -s "${BASE_URL}/api/sources/local/scan?path=/absolute/path/to/docs&recursive=true"
```

调用系统原生选择器（目录）：

```bash
curl -s -X POST "${BASE_URL}/api/sources/local/pick" \
  -H "Content-Type: application/json" \
  -d '{
    "target": "directory",
    "extensions": ["md", "markdown", "docx"]
  }'
```

### 任务操作

启动本地导入任务（示例，含根子目录自定义）：

```bash
curl -s -X POST "${BASE_URL}/api/import/start" \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "local",
    "path": "/absolute/path/to/docs",
    "write_mode": "folder",
    "import_type": "directory",
    "structure_order": "toc_first",
    "toc_file": "TABLE_OF_CONTENTS.md",
    "folder_subdirs": true,
    "folder_root_subdir": true,
    "folder_root_subdir_name": "my-custom-batch",
    "folder_nav_doc": true,
    "folder_nav_title": "00-导航总目录",
    "llm_fallback": "toc_ambiguity",
    "llm_max_calls": 3,
    "skip_root_readme": false,
    "max_workers": 2,
    "chunk_workers": 2,
    "notify_level": "normal",
    "dry_run": false
  }'
```

启动 GitHub 导入任务（示例）：

```bash
curl -s -X POST "${BASE_URL}/api/import/start" \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "github",
    "path": "BrenchCC/Context_Engineering_Analysis",
    "ref": "main",
    "subdir": "docs",
    "write_mode": "wiki",
    "space_name": "Context Engineering Analysis",
    "notify_level": "minimal",
    "dry_run": false
  }'
```

查询任务状态（把 `<TASK_ID>` 替换成返回的 `task_id`）：

```bash
curl -s "${BASE_URL}/api/import/status/<TASK_ID>"
```

查询任务结果：

```bash
curl -s "${BASE_URL}/api/import/result/<TASK_ID>"
```

取消任务：

```bash
curl -s -X POST "${BASE_URL}/api/import/cancel/<TASK_ID>"
```

查询任务列表：

```bash
curl -s "${BASE_URL}/api/tasks/?page=1&page_size=10"
```