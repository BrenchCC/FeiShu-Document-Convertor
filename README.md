# 飞书知识库自动导入器

<p align="center">
  <img src="assets/logo.png" alt="项目 Logo" width="500">
</p>

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-15%20passed-brightgreen.svg)](tests/)
[![Coverage](https://img.shields.io/badge/Coverage-Coming%20soon-yellow.svg)](tests/)

将本地目录或 GitHub 仓库中的文档导入飞书云文档，并可写入知识库。本地源支持 Markdown 与 DOCX（DOCX 通过 Pandoc 转换为 Markdown 后导入）。

## 🚀 项目简介

飞书知识库自动导入器是一个功能强大的文档迁移工具，旨在帮助用户将本地文档或 GitHub 仓库中的内容快速、高效地导入到飞书云文档或知识库中。该工具支持多种数据源和写入模式，并提供了丰富的配置选项，以满足不同场景的需求。

## ✨ 核心功能

### 数据源支持
- **本地目录**：支持 `.md`、`.markdown` 和 `.docx` 文件
- **GitHub 仓库**：直接导入 GitHub 仓库中的 Markdown 文档
- **智能转换**：DOCX 文件通过 Pandoc 自动转换为 Markdown 格式

### 写入模式
- **云盘文件夹**：将文档写入飞书云盘指定文件夹
- **知识库**：将文档写入飞书知识库（需 OAuth 授权）
- **同时写入**：支持同时写入云盘文件夹和知识库

### 关键特性
✅ **OAuth 授权**：支持本地回调自动授权和手动授权码两种方式
✅ **容错机制**：按文件粒度失败不中断，任务末尾统一汇总失败信息
✅ **通知系统**：支持飞书机器人 webhook 和 chat_id 通知
✅ **表格处理优化**：自动降级策略避免飞书 API 参数限制
✅ **Web 控制台**：提供直观的 Web 界面，支持本地目录/单文件导入
✅ **并发优化**：支持文档级和分片级并发处理
✅ **调试模式**：提供 dry run 模式，验证流程而不实际写入

## 📁 目录结构

```text
├── cli/             # CLI 辅助模块
├── config/          # 配置管理
├── core/            # 核心业务逻辑（编排、异常处理、bootstrap）
├── data/            # 数据模型与源适配器
├── integrations/    # 第三方 API 集成（飞书、HTTP 客户端）
├── utils/           # 工具函数（Markdown 解析、文本分块、HTTP、日志）
├── web/             # Web API 与前端静态资源
├── tests/           # 单元测试与集成测试
├── docs/            # 详细文档与使用指南
└── main.py          # CLI 入口点
```

## 🔧 环境变量

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

## 🚀 快速开始

### 查看帮助信息

```bash
python main.py -h
```

### 基本使用示例

#### 📁 本地目录 -> 云盘文件夹

```bash
python main.py \
  --source local \
  --path /path/to/docs \
  --write-mode folder
```

#### 🌐 GitHub 仓库 -> 云盘文件夹

```bash
python main.py \
  --source github \
  --repo BrenchCC/llm-transformer-book \
  --write-mode folder
```

#### ⚡ 多进程导入（推荐）

```bash
python main.py \
  --source local \
  --path /path/to/docs \
  --write-mode folder \
  --folder-subdirs \
  --max-workers 3 \
  --chunk-workers 4
```

#### 📚 本地目录 -> 知识库

```bash
python main.py \
  --source local \
  --path examples/ai-agent-book/zh \
  --write-mode wiki \
  --space-name "AI Agent 开发指南" \
  --oauth-local-server
```

#### 🔍 GitHub 子目录 -> 知识库

```bash
python main.py \
  --source github \
  --repo BrenchCC/llm-transformer-book \
  --subdir docs/chapter1 \
  --write-mode wiki \
  --space-name "LLM Transformer"
```

#### 🧪 调试模式（Dry Run）

```bash
python main.py \
  --source github \
  --repo BrenchCC/LLMs_Thinking_Analysis \
  --write-mode wiki \
  --space-name dry-run \
  --dry-run \
  --notify-level none
```

## 🌐 Web 控制台

### 启动 Web 服务

```bash
python web/main.py
```

默认监听 `0.0.0.0:8000`。

## 🐳 Docker 运行

### 构建镜像

```bash
docker build -f docker/Dockerfile -t feishu-doc-convertor .
```

### 使用 Docker Compose

```bash
docker-compose -f ./docker/docker-compose.yml up -d
```

单独启动服务：

```bash
docker-compose -f ./docker/docker-compose.yml up -d server
docker-compose -f ./docker/docker-compose.yml up -d cli
```

### Web 控制台功能

- 本地文件/目录导入
- GitHub 仓库导入
- 任务管理与监控
- 系统配置管理
- 任务结果查看

## 📖 详细文档

项目提供了完整的详细文档，位于 `docs/guidance/` 目录：

- [Web 控制台使用指南](docs/guidance/web-console.md)：Web 控制台的详细使用说明
- [OAuth 授权使用指南](docs/guidance/oauth-guide.md)：OAuth 授权使用指南
- [通知系统](docs/guidance/notification-system.md)：通知系统配置与使用
- [并发调优建议](docs/guidance/concurrency-tuning.md)：并发调优建议
- [常见问题与解决方案](docs/guidance/troubleshooting.md)：常见问题与解决方案
- [命令语法和参数说明](docs/guidance/command-reference.md)：命令语法和参数详细说明

## 📊 测试命令

### 使用 conda 环境（推荐）

项目使用的 conda 环境名称是：`knowledge_generator`

```bash
# 激活环境
conda activate knowledge_generator

# 运行所有测试（推荐）
conda run -n knowledge_generator python -m unittest discover -s tests -v

# 运行特定测试文件
conda run -n knowledge_generator python -m pytest tests/test_feishu_api.py -v

# 运行特定测试类
conda run -n knowledge_generator python -m pytest tests/test_feishu_api.py::TestFeishuApiOptimizations -v
```

### 直接运行（不使用 conda）

```bash
# 运行所有测试（推荐）
python -m unittest discover -s tests -v

# 运行特定测试文件（pytest 可选）
python -m pytest tests/test_feishu_api.py -v

# 运行特定测试类
python -m pytest tests/test_feishu_api.py::TestFeishuApiOptimizations -v
```

## 🛠️ 开发说明

### 代码风格

- **PEP 8 规范**：使用 `flake8` 进行代码检查
- **类型注解**：推荐使用类型注解
- **文档字符串**：函数定义必须有 `"""` 文档字符串
- **日志配置**：统一放在 `utils/logging_setup.py`，CLI/Web 复用

### 项目依赖

#### 使用 pip 安装

```bash
pip install -r requirements.txt
```

#### 使用 conda 环境

项目使用的 conda 环境名称是：`knowledge_generator`

```bash
# 激活环境
conda activate knowledge_generator

# 在环境中安装依赖
conda run -n knowledge_generator pip install -r requirements.txt
```

### DOCX 导入依赖

DOCX 导入依赖 `pandoc`，请确保系统已安装：

```bash
pandoc --version
```

## 📈 技术架构

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

## 📚 使用指南

### 快速开始

1. 安装项目依赖
2. 配置环境变量（参考 `.env.example`）
3. 运行命令导入文档

### 常用命令

```bash
# 查看帮助
python main.py -h

# 本地目录导入到云盘文件夹
python main.py --source local --path /path/to/docs --write-mode folder

# GitHub 仓库导入到知识库
python main.py --source github --repo BrenchCC/llm-transformer-book --write-mode wiki --space-name "LLM Transformer" --oauth-local-server

# 多进程导入
python main.py --source local --path /path/to/docs --write-mode folder --folder-subdirs --max-workers 3 --chunk-workers 4

# 调试模式
python main.py --source local --path /path/to/docs --write-mode folder --dry-run --notify-level none
```

## 🎯 下一步计划

- [ ] 支持更多文档格式（PDF）并增强 Word 保真导入
- [ ] 实现增量同步功能
- [ ] 增强表格格式保留
- [ ] 优化图片上传成功率
- [ ] 提供更多导出格式支持

**🤝 欢迎贡献**：请参考 CONTRIBUTING.md 文件。
