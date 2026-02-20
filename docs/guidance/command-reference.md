# 命令语法和参数说明

## 📝 命令总语法

```bash
python main.py \
  --source {local|github} \
  [--path <local_dir>] \
  [--repo <owner/name_or_url>] \
  [--ref <branch_or_tag_or_commit>] \
  [--subdir <repo_subdir>] \
  --write-mode {folder|wiki|both} \
  [--folder-subdirs | --no-folder-subdirs] \
  [--skip-root-readme] \
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
  [--chunk-workers <int>] \
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

## 📋 参数说明

### 源参数

| 参数 | 说明 | 约束 |
|------|------|------|
| `--source` | 数据源类型 | 必填，`local` 或 `github` |
| `--path` | 本地路径（目录或单个 Markdown 文件） | `--source local` 时必填，支持仓库目录、子目录或单文件 |
| `--repo` | GitHub 仓库地址 | `--source github` 时必填，支持 `owner/name` 或完整 URL |
| `--ref` | GitHub 分支/标签/提交 | 默认 `main` |
| `--subdir` | GitHub 子目录 | 默认空，填相对路径 |

### 写入参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--write-mode` | 写入模式 | 必填，`folder` 写飞书云盘；`wiki` 写知识库；`both` 两者都写 |
| `--folder-subdirs` | 按源目录自动创建子文件夹 | 默认关闭 |
| `--skip-root-readme` | 跳过根目录 `README.md/readme.md` | 默认关闭；开启后仅过滤根 README，不影响 `index.md` |
| `--folder-root-subdir` | 是否先创建任务根子文件夹 | 默认开启 |
| `--folder-root-subdir-name` | 任务根文件夹名称 | 空则自动生成 `<source_name>-<yyyyMMdd-HHmm>` |
| `--structure-order` | 文档排序策略 | `toc_first` 优先 TOC；`path` 按路径字典序 |
| `--toc-file` | TOC 文件路径 | 默认 `TABLE_OF_CONTENTS.md`，相对源目录 |
| `--folder-nav-doc` | 生成导航文档 | 默认开启；`folder-subdirs=true` 走 LLM 总目录，失败直接跳过 |
| `--folder-nav-title` | 导航文档标题 | 默认 `00-导航总目录` |
| `--max-workers` | 文档级并发数 | `1` 串行；`>1` 按一级目录分组多进程（根目录归 `__root__`）；飞书 API 场景建议 `2~4` |
| `--chunk-workers` | 单文档分片规划线程数 | 仅影响分片计算并发，API 写入仍顺序执行；建议不超过 CPU 逻辑核数 |

### LLM 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--llm-fallback` | LLM 降级策略 | `off` 关闭；`toc_ambiguity` TOC 排序歧义时使用 |
| `--llm-max-calls` | LLM 最大调用次数 | `3` |

### 知识库参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--space-name` | 知识库名称 | 必填（`--write-mode wiki` 或 `both` 时） |
| `--space-id` | 知识库 ID | 空则自动创建新空间 |

### 通知参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--chat-id` | 聊天 ID | - |
| `--dry-run` | 调试模式（不实际写入） | 默认关闭 |
| `--notify-level` | 通知级别 | `normal`；`none` 关闭；`minimal` 仅关键通知；`normal` 按文件通知 |

### OAuth 参数

**🔐 重要**：使用 `wiki` 模式需要用户级权限，必须配置 OAuth。

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--oauth-local-server` | 启动本地回调并自动交换 token | - |
| `--auth-code` | 手动输入授权码 | - |
| `--print-auth-url` | 只打印授权链接并退出 | - |
| `--oauth-redirect-uri` | OAuth 重定向 URI | `http://127.0.0.1:8765/callback` |
| `--oauth-timeout` | OAuth 超时时间（秒） | `300` |
| `--oauth-open-browser` / `--no-oauth-open-browser` | 是否自动打开浏览器 | 自动打开 |
| `--persist-user-token-env` / `--no-persist-user-token-env` | 是否保存用户 token 到环境变量 | 否 |
| `--oauth-scope` | OAuth 授权范围 | 默认范围 |
| `--oauth-state` | OAuth 状态参数 | 自动生成 |

## 🚀 常用命令模板

### 本地目录 -> 云盘文件夹

```bash
python main.py \
  --source local \
  --path /path/to/docs \
  --write-mode folder
```

### 多进程导入（推荐）

```bash
python main.py \
  --source local \
  --path /path/to/docs \
  --write-mode folder \
  --folder-subdirs \
  --max-workers 3 \
  --chunk-workers 4
```

### GitHub 仓库 -> 云盘文件夹

```bash
python main.py \
  --source github \
  --repo BrenchCC/llm-transformer-book \
  --write-mode folder
```

### 本地目录 -> 云盘文件夹（自动创建子文件夹）

```bash
python main.py \
  --source local \
  --path examples/ai-agent-book/zh \
  --write-mode folder \
  --folder-subdirs
```

### 本地目录 -> 知识库

```bash
python main.py \
  --source local \
  --path examples/ai-agent-book/zh \
  --write-mode wiki \
  --space-name "AI Agent 开发指南" \
  --oauth-local-server
```

### GitHub 子目录 -> 知识库

```bash
python main.py \
  --source github \
  --repo BrenchCC/llm-transformer-book \
  --subdir docs/chapter1 \
  --write-mode wiki \
  --space-name "LLM Transformer"
```

### 调试模式（Dry Run）

```bash
python main.py \
  --source github \
  --repo BrenchCC/LLMs_Thinking_Analysis \
  --write-mode wiki \
  --space-name dry-run \
  --dry-run \
  --notify-level none
```

## 📊 退出码说明

| 代码 | 含义 | 说明 |
|------|------|------|
| `0` | 成功 | 任务完成，所有文件处理成功 |
| `1` | 错误 | 参数错误或运行期致命错误 |
| `2` | 部分失败 | 任务完成但存在失败文件 |