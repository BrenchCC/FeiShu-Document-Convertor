# 飞书知识库自动导入器（Python CLI）

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-15%20passed-brightgreen.svg)](tests/)
[![Coverage](https://img.shields.io/badge/Coverage-Coming%20soon-yellow.svg)](tests/)

将本地目录或 GitHub 仓库中的 Markdown（含图片、公式）导入飞书云文档，并可写入知识库。

## 功能概览

✅ **数据源支持**：`local` / `github`（仅 `git clone/fetch/checkout`）
✅ **写入模式**：`folder` / `wiki` / `both`
✅ **OAuth 授权**：支持手动 `auth code` 与本地回调自动授权
✅ **容错机制**：按文件粒度失败不中断，任务末尾统一汇总
✅ **通知系统**：支持 webhook 或 chat_id 发送进度
✅ **表格处理优化**：直接降级策略避免飞书 API 参数限制

## 目录结构

```text
config/          # 配置管理
core/            # 核心业务逻辑（编排、异常处理）
data/            # 数据模型与源适配器
integrations/    # 第三方 API 集成（飞书、HTTP 客户端）
utils/           # 工具函数（Markdown 解析、文本分块、HTTP）
tests/           # 单元测试与集成测试
main.py          # CLI 入口点
```

## 环境变量

参考 `.env.example` 文件配置以下环境变量：

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `FEISHU_WEBHOOK_URL` | 飞书机器人 webhook 地址 | `https://open.feishu.cn/open-apis/bot/v2/hook/xxx` |
| `FEISHU_APP_ID` | 飞书应用 ID | `cli_a1b2c3d4e5f6` |
| `FEISHU_APP_SECRET` | 飞书应用密钥 | `abcdef1234567890` |
| `FEISHU_USER_ACCESS_TOKEN` | 用户访问令牌 | `u-xxx` |
| `FEISHU_USER_REFRESH_TOKEN` | 用户刷新令牌 | `ur-xxx` |
| `FEISHU_FOLDER_TOKEN` | 目标文件夹 token | `fld_xxx` |
| `FEISHU_BASE_URL` | 飞书 API 基础 URL | `https://open.feishu.cn` |

**💡 提示**：`.env` 文件已加入 `.gitignore`，不会被版本跟踪。

## 快速开始

### 查看帮助信息

```bash
python main.py -h
```

### 命令总语法

```bash
python main.py \
  --source {local|github} \
  [--path <local_dir>] \
  [--repo <owner/name_or_url>] \
  [--ref <branch_or_tag_or_commit>] \
  [--subdir <repo_subdir>] \
  --write-mode {folder|wiki|both} \
  [--folder-subdirs | --no-folder-subdirs] \
  [--folder-root-subdir | --no-folder-root-subdir] \
  [--folder-root-subdir-name <task_root_folder_name>] \
  [--structure-order {toc_first|path}] \
  [--toc-file <toc_markdown_path>] \
  [--folder-nav-doc | --no-folder-nav-doc] \
  [--folder-nav-title <folder_nav_title>] \
  [--llm-fallback {off|toc_ambiguity}] \
  [--llm-max-calls <int>] \
  [--space-name <wiki_space_name>] \
  [--space-id <wiki_space_id>] \
  [--chat-id <chat_id>] \
  [--dry-run] \
  [--notify-level {none|minimal|normal}] \
  [--max-workers <int>] \
  [--auth-code <oauth_code>] \
  [--oauth-redirect-uri <redirect_uri>] \
  [--print-auth-url] \
  [--oauth-local-server] \
  [--oauth-timeout <seconds>] \
  [--oauth-open-browser | --no-oauth-open-browser] \
  [--persist-user-token-env | --no-persist-user-token-env] \
  [--oauth-scope "<scope1 scope2 ...>"] \
  [--oauth-state <state>]
```

## 参数说明

### 源参数

| 参数 | 说明 | 约束 |
|------|------|------|
| `--source` | 数据源类型 | 必填，`local` 或 `github` |
| `--path` | 本地目录路径 | `--source local` 时必填 |
| `--repo` | GitHub 仓库地址 | `--source github` 时必填 |
| `--ref` | 分支/标签/提交 | 默认 `main` |
| `--subdir` | 仓库子目录 | 默认空 |

### 写入参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--write-mode` | 写入模式 | 必填，`folder`/`wiki`/`both` |
| `--folder-subdirs` | 自动创建子文件夹 | 默认关闭 |
| `--folder-root-subdir` | 创建任务根子文件夹 | 默认开启 |
| `--folder-root-subdir-name` | 任务根文件夹名称 | 自动生成 `<source_name>-<yyyyMMdd-HHmm>` |
| `--structure-order` | 文档结构顺序 | `toc_first` |
| `--toc-file` | TOC 文件路径 | `TABLE_OF_CONTENTS.md` |
| `--folder-nav-doc` | 生成导航文档 | 默认开启 |
| `--folder-nav-title` | 导航文档标题 | `00-导航总目录` |

### OAuth 参数

**🔐 重要**：使用 `wiki` 模式需要用户级权限，必须配置 OAuth。

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--oauth-local-server` | 本地回调自动授权 | 推荐使用 |
| `--auth-code` | 手动输入授权码 | 不常用 |
| `--print-auth-url` | 只打印授权链接 | 用于调试 |

## 常用命令模板

### 📁 本地目录 -> 云盘文件夹

```bash
python main.py \
  --source local \
  --path /path/to/docs \
  --write-mode folder
```

### 🚀 GitHub 仓库 -> 云盘文件夹

```bash
python main.py \
  --source github \
  --repo waylandzhang/llm-transformer-book \
  --write-mode folder
```

### 📂 本地目录 -> 云盘文件夹（自动创建子文件夹）

```bash
python main.py \
  --source local \
  --path examples/ai-agent-book/zh \
  --write-mode folder \
  --folder-subdirs
```

### 📚 本地目录 -> 知识库

```bash
python main.py \
  --source local \
  --path examples/ai-agent-book/zh \
  --write-mode wiki \
  --space-name "AI Agent 开发指南" \
  --oauth-local-server \
  --oauth-redirect-uri "http://127.0.0.1:8765/callback"
```

### 🔍 GitHub 子目录 -> 知识库

```bash
python main.py \
  --source github \
  --repo waylandzhang/llm-transformer-book \
  --subdir docs/chapter1 \
  --write-mode wiki \
  --space-name "LLM Transformer"
```

### 🧪 调试模式（Dry Run）

```bash
python main.py \
  --source github \
  --repo BrenchCC/LLMs_Thinking_Analysis \
  --write-mode wiki \
  --space-name dry-run \
  --dry-run \
  --notify-level none
```

## OAuth 使用方法

### A. 本地回调自动授权（推荐）

1. 在飞书后台配置回调地址白名单：`http://127.0.0.1:8765/callback`
2. 运行命令：

```bash
python main.py \
  --source github \
  --repo BrenchCC/Context_Engineering_Analysis \
  --write-mode wiki \
  --space-name Context_Engineering_Analysis \
  --oauth-local-server \
  --oauth-redirect-uri "http://127.0.0.1:8765/callback"
```

### B. 手动授权码换 Token

```bash
python main.py \
  --source github \
  --repo BrenchCC/Context_Engineering_Analysis \
  --write-mode wiki \
  --space-name Context_Engineering_Analysis \
  --auth-code "<你的授权码>" \
  --oauth-redirect-uri "http://127.0.0.1:8765/callback"
```

## 通知系统

### 通知方式

- **Webhook**：设置 `FEISHU_WEBHOOK_URL` 环境变量（推荐）
- **Chat ID**：使用 `--chat-id` 参数（未配置 webhook 时）

### 通知级别

- `--notify-level none`：关闭过程通知
- `--notify-level minimal`：仅关键通知（任务开始/完成）
- `--notify-level normal`：按文件通知（默认）

## 缓存与 Git 策略

- **用户 Token 缓存**：默认路径 `cache/user_token.json`
- **Git 忽略**：`cache/` 和 `.env` 已在 `.gitignore`
- **临时文件**：`.gitkeep` 文件已被忽略（`*.gitkeep`）

## 表格处理优化

**📝 说明**：飞书 API 对表格块有严格的参数限制，我们实现了以下优化：

```python
# 在 write_markdown_by_block_matching 方法中
if segment.kind == "table":
    logger.info("Direct fallback for table block")
    self._write_segment_by_native_blocks(
        document_id, segment.kind, segment_content
    )
    continue
```

**✅ 效果**：表格块现在直接转换为文本块，避免了 API 参数不合法错误。

## 测试命令

```bash
# 运行所有测试（使用 conda 环境）
conda run -n knowledge_generator python -m pytest tests/ -v

# 运行特定测试文件
conda run -n knowledge_generator python -m pytest tests/test_feishu_api.py -v

# 运行特定测试类
conda run -n knowledge_generator python -m pytest tests/test_feishu_api.py::TestFeishuApiOptimizations -v
```

## 常见问题

### 1. 表格导入失败

**问题**：飞书 API 返回 `1770001 invalid param`（参数不合法）

**解决方案**：我们的代码已自动优化，对表格块使用直接降级策略，避免了 API 限制。

### 2. OAuth 授权失败

**问题**：`20029 redirect_uri 请求不合法`

**检查清单**：
- 飞书后台白名单配置是否与 `--oauth-redirect-uri` 完全一致
- 协议（http/https）是否匹配
- 端口是否相同
- 路径是否一致

### 3. 知识库创建失败

**问题**：`Create wiki space requires user_access_token`

**解决方案**：
- 使用 `--oauth-local-server` 自动授权
- 或使用 `--auth-code` 手动授权
- 或改用 `--space-id` 写入已有空间

### 4. GitHub 仓库无法访问

**问题**：Git 克隆失败或网络超时

**解决方案**：
- 检查网络连接
- 尝试使用代理
- 程序会自动尝试 `gh-proxy` 回退

## 退出码说明

| 代码 | 含义 | 说明 |
|------|------|------|
| `0` | 成功 | 任务完成，所有文件处理成功 |
| `1` | 错误 | 参数错误或运行期致命错误 |
| `2` | 部分失败 | 任务完成但存在失败文件 |

## 开发说明

### 代码风格

- **PEP 8 规范**：使用 `flake8` 进行代码检查
- **类型注解**：推荐使用类型注解
- **文档字符串**：函数定义必须有 `"""` 文档字符串

### 项目依赖

```bash
# 安装依赖
pip install -r requirements.txt

# 或使用 conda
conda install -n knowledge_generator pip
conda run -n knowledge_generator pip install -r requirements.txt
```

## 技术架构

```
┌──────────────────────┐
│    CLI 入口（main.py）    │
└──────────────────────┘
           ↓
┌──────────────────────┐
│  核心编排逻辑（orchestrator.py）  │
└──────────────────────┘
           ↓
┌──────────────────────┐
│  源适配器（data/source_adapters.py）  │
└──────────────────────┘
           ↓
┌──────────────────────┐
│  文档处理（feishu_api.py）   │
└──────────────────────┘
           ↓
┌──────────────────────┐
│  Markdown 解析（utils/markdown_block_parser.py）  │
└──────────────────────┘
           ↓
┌──────────────────────┐
│  文本分块（utils/text_chunker.py）  │
└──────────────────────┘
           ↓
┌──────────────────────┐
│  飞书 API 集成（integrations/feishu_api.py）  │
└──────────────────────┘
```

## 下一步计划

- [ ] 支持更多文档格式（PDF、Word）
- [ ] 实现增量同步功能
- [ ] 增强表格格式保留
- [ ] 优化图片上传成功率

**🤝 欢迎贡献**：请参考 CONTRIBUTING.md 文件。
