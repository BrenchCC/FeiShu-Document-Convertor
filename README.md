# 飞书知识库自动导入器（Python CLI）

将本地目录或 GitHub 仓库中的 Markdown（含图片、公式）导入飞书云文档，并可写入知识库。

## 功能概览

- 数据源：`local` / `github`（仅 `git clone/fetch/checkout`）
- 写入模式：`folder` / `wiki` / `both`
- OAuth：支持手动 `auth code` 与本地回调自动授权
- 失败策略：按文件粒度失败不中断，任务末尾统一汇总
- 通知：支持 webhook 或 chat_id 发送进度

## 目录结构

```text
config/
core/
data/
integrations/
utils/
tests/
main.py
```

## 环境变量

参考 `.env.example`：

- `FEISHU_WEBHOOK_URL`
- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_USER_ACCESS_TOKEN`
- `FEISHU_USER_REFRESH_TOKEN`
- `FEISHU_USER_TOKEN_CACHE_PATH`（默认 `cache/user_token.json`）
- `FEISHU_FOLDER_TOKEN`
- `FEISHU_BASE_URL`
- `REQUEST_TIMEOUT`
- `MAX_RETRIES`
- `RETRY_BACKOFF`
- `FEISHU_MESSAGE_MAX_BYTES`
- `FEISHU_CONVERT_MAX_BYTES`
- `NOTIFY_LEVEL`

## 一条命令看帮助

```bash
python main.py -h
```

## 命令总语法

```bash
python main.py \
  --source {local|github} \
  [--path <local_dir>] \
  [--repo <owner/name_or_url>] \
  [--ref <branch_or_tag_or_commit>] \
  [--subdir <repo_subdir>] \
  --write-mode {folder|wiki|both} \
  [--folder-subdirs | --no-folder-subdirs] \
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

## 参数说明（完整）

### 源参数

- `--source`：`local` 或 `github`，必填
- `--path`：本地目录（当 `--source local` 必填）
- `--repo`：仓库地址或 `owner/name`（当 `--source github` 必填）
- `--ref`：分支/标签/commit，默认 `main`
- `--subdir`：仅导入仓库子目录，默认空

### 写入参数

- `--write-mode`：`folder` / `wiki` / `both`，默认 `folder`
- `--folder-subdirs`：仅在 `--write-mode folder|both` 下生效；按源目录层级在 `FEISHU_FOLDER_TOKEN` 下自动创建子文件夹并写入
- `--space-name`：目标知识库空间名
- `--space-id`：已有知识库空间 ID
- `--chat-id`：通知机器人 chat_id（当没配 webhook 时可用）

### 任务参数

- `--dry-run`：只解析不写飞书
- `--notify-level`：`none|minimal|normal`，默认 `normal`
- `--max-workers`：预留并发参数，当前版本仍顺序执行（建议保持 `1`）

### OAuth 参数

- `--auth-code`：手动授权码换 token
- `--oauth-redirect-uri`：OAuth 回调地址
- `--print-auth-url`：只打印授权链接后退出
- `--oauth-local-server`：开启本地回调自动拿 code
- `--oauth-timeout`：本地回调等待秒数，默认 `300`
- `--oauth-open-browser` / `--no-oauth-open-browser`：本地授权时是否自动打开浏览器
- `--persist-user-token-env` / `--no-persist-user-token-env`：是否把 token 写回 `.env`
- `--oauth-scope`：授权 scope，默认 `"wiki:wiki offline_access"`
- `--oauth-state`：OAuth state，默认 `kg_state`

## 参数约束（必看）

- `--source local` 必须带 `--path`
- `--source github` 必须带 `--repo`
- `--write-mode wiki|both` 必须提供 `--space-name` 或 `--space-id`
- 使用 `--auth-code` 必须提供 `--oauth-redirect-uri`
- 使用 `--print-auth-url` 必须提供 `--oauth-redirect-uri`
- 使用 `--oauth-local-server` 必须提供 `--oauth-redirect-uri`
- `--oauth-local-server` 与 `--auth-code` 互斥
- `--max-workers >= 1`
- `--oauth-timeout >= 1`

## 常用命令模板

### 1) 本地目录 -> 云盘文件夹

```bash
python main.py \
  --source local \
  --path /path/to/docs \
  --write-mode folder
```

### 2) GitHub -> 云盘文件夹

```bash
python main.py \
  --source github \
  --repo waylandzhang/llm-transformer-book \
  --write-mode folder
```

### 2.1) 本地目录 -> 云盘文件夹（自动创建子文件夹）

```bash
python main.py \
  --source local \
  --path examples/ai-agent-book/zh \
  --write-mode folder \
  --folder-subdirs
```

### 3) GitHub -> 知识库（按空间名）

```bash
python main.py \
  --source github \
  --repo waylandzhang/llm-transformer-book \
  --write-mode wiki \
  --space-name "LLM Transformer"
```

### 4) GitHub -> 知识库（按 space_id）

```bash
python main.py \
  --source github \
  --repo waylandzhang/llm-transformer-book \
  --write-mode wiki \
  --space-id "7381690234874520324"
```

### 5) GitHub -> 同时写文件夹与知识库

```bash
python main.py \
  --source github \
  --repo waylandzhang/llm-transformer-book \
  --write-mode both \
  --space-name "LLM Transformer"
```

### 6) 只处理仓库子目录

```bash
python main.py \
  --source github \
  --repo waylandzhang/llm-transformer-book \
  --subdir docs/chapter1 \
  --write-mode wiki \
  --space-name "LLM Transformer"
```

### 7) 指定分支/标签/提交

```bash
python main.py \
  --source github \
  --repo waylandzhang/llm-transformer-book \
  --ref main \
  --write-mode wiki \
  --space-name "LLM Transformer"
```

### 8) dry-run 调试

```bash
python main.py \
  --source github \
  --repo BrenchCC/LLMs_Thinking_Analysis \
  --write-mode wiki \
  --space-name dry-run \
  --dry-run \
  --notify-level none
```

## OAuth 使用方法（完整）

### A. 只打印授权链接

```bash
python main.py \
  --source local \
  --path . \
  --write-mode wiki \
  --space-name demo \
  --print-auth-url \
  --oauth-redirect-uri "http://127.0.0.1:8765/callback"
```

### B. 本地回调自动授权（推荐）

先在飞书后台配置白名单 `redirect_uri`，例如：
`http://127.0.0.1:8765/callback`

```bash
python main.py \
  --source github \
  --repo BrenchCC/Context_Engineering_Analysis \
  --write-mode wiki \
  --space-name Context_Engineering_Analysis \
  --oauth-local-server \
  --oauth-redirect-uri "http://127.0.0.1:8765/callback"
```

### C. 手动 code 换 token

```bash
python main.py \
  --source github \
  --repo BrenchCC/Context_Engineering_Analysis \
  --write-mode wiki \
  --space-name Context_Engineering_Analysis \
  --auth-code "<oauth_code>" \
  --oauth-redirect-uri "http://127.0.0.1:8765/callback"
```

### D. 本地授权但不自动拉起浏览器

```bash
python main.py \
  --source local \
  --path . \
  --write-mode wiki \
  --space-name demo \
  --oauth-local-server \
  --oauth-redirect-uri "http://127.0.0.1:8765/callback" \
  --no-oauth-open-browser
```

### E. 不写回 .env，仅用缓存文件

```bash
python main.py \
  --source local \
  --path . \
  --write-mode wiki \
  --space-name demo \
  --oauth-local-server \
  --oauth-redirect-uri "http://127.0.0.1:8765/callback" \
  --no-persist-user-token-env
```

## 通知使用方式

- 若设置了 `FEISHU_WEBHOOK_URL`：默认走 webhook 通知
- 未设置 webhook 时，可通过 `--chat-id` 走消息接口通知
- `--notify-level none`：关闭过程通知
- `--notify-level minimal`：仅关键通知
- `--notify-level normal`：按文件通知（默认）

## 缓存与 Git 策略

- 用户 token 缓存默认路径：`cache/user_token.json`
- `cache/` 已在 `.gitignore`，不会被版本跟踪
- `.gitkeep` 已忽略（`*.gitkeep`）

## 退出码说明

- `0`：任务成功
- `1`：参数错误或运行期致命错误
- `2`：任务完成但存在失败文件

## 测试命令

```bash
python -m unittest discover -s tests -v
```

## 常见问题

- `20029 redirect_uri 请求不合法`  
  检查 `--oauth-redirect-uri` 与飞书后台白名单是否完全一致（协议/域名/端口/路径）。

- `Create wiki space requires user_access_token`  
  先完成 OAuth（`--oauth-local-server` 或 `--auth-code`），或改用 `--space-id` 写入已有空间。

- GitHub 无法直连  
  程序会自动尝试 `gh-proxy` 回退；若仍失败，检查本机网络或代理。
