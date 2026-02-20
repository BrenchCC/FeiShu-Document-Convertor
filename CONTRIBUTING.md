# 贡献指南

感谢你对 `飞书知识库自动导入器` 项目的兴趣和支持！本指南将帮助你快速上手并参与到项目的开发中来。

## 🏁 开始之前

### 项目概述

飞书知识库自动导入器是一个用于将本地目录或 GitHub 仓库中的 Markdown 文档（含图片、公式）导入飞书云文档或知识库的工具。支持多种写入模式和并发处理优化。

### 贡献类型

我们欢迎以下类型的贡献：
- Bug 修复
- 新功能实现
- 测试补充与稳定性改进
- 文档改进（README、示例命令、排障说明）

## 🚀 快速开始

### 环境准备

```bash
# 克隆项目
git clone <项目地址>
cd <项目名称>

# 安装依赖
pip install -r requirements.txt
```

### 如需使用 conda 环境

项目使用的 conda 环境名称是：`knowledge_generator`

```bash
# 激活环境
conda activate knowledge_generator

# 在环境中安装依赖
conda run -n knowledge_generator pip install -r requirements.txt
```

### 快速自检

```bash
# 仅验证流程，不写远端
python main.py --source local --path . --write-mode folder --dry-run --notify-level none
```

## 📝 代码规范

请遵循以下代码规范：

### Python 规范
- 使用 4 空格缩进
- 函数建议带类型注解
- 函数必须有英文 docstring，说明参数语义
- 注释使用英文
- import 分组：标准库 / 第三方 / 本地模块
- 参数与赋值格式保持现有风格：`arg = value`
- `argparse` 参数解析放在 `parse_args()` 中

### 文档规范
- 所有文档使用 Markdown 格式
- 代码示例使用 ```bash 或 ```python 语法高亮
- 表格使用 Markdown 表格语法
- 链接使用相对路径

## 🔍 测试规范

### 测试框架
项目使用 `unittest` 作为测试框架。

### 测试文件命名
- 测试文件命名：`tests/test_<feature>.py`
- 测试类命名：`Test<Feature>`
- 测试方法命名：`test_<scenario>`

### 测试要求
每次行为变更都要补充或更新测试，至少覆盖：
- 成功路径
- 失败路径
- 关键边界条件

### 运行测试

```bash
# 全量测试
python -m unittest discover -s tests -v

# 运行单个测试模块
python -m unittest tests.test_orchestrator -v

# 使用 conda 环境
conda run -n knowledge_generator python -m unittest discover -s tests -v
```

## 📦 提交规范

### 提交信息格式

推荐使用以下提交信息格式：

```text
type(scope): summary
```

#### 类型说明（type）
- `feat`：新功能
- `fix`：bug 修复
- `docs`：文档改进
- `test`：测试补充
- `refactor`：重构
- `style`：格式调整
- `chore`：杂项修改

#### 范围说明（scope）
- `main`：主程序
- `cli`：命令行界面
- `web`：Web 控制台
- `core`：核心业务逻辑
- `data`：数据模型
- `integrations`：第三方集成
- `utils`：工具函数
- `tests`：测试

#### 示例
```text
feat(web): 添加本地文件选择功能
fix(core): 修复文档导入失败的问题
docs(readme): 更新快速开始示例
test(integrations): 补充飞书 API 测试
```

## 🎯 Pull Request 规范

### PR 描述要求

PR 描述建议包含以下内容：
- 变更目标（解决什么问题）
- 主要改动模块（涉及哪些文件）
- 测试命令与结果摘要
- 兼容性/行为变化说明
- 是否需要更新 `.env` 配置项

### 最小可复现命令

建议附上最小可复现命令，便于评审验证。

## 🔒 安全与敏感信息

- 不要提交 `.env`、token、密钥、用户隐私数据
- 不要在日志、截图、PR 描述中泄露密钥或 chat_id 等敏感信息
- 与飞书接口相关的错误日志请优先脱敏后再分享

## 📚 文档更新要求

当出现以下情况时，请同步更新文档：
- CLI 参数含义或默认值变化
- 导入流程变化（如并发、目录策略、fallback 逻辑）
- 新增常见报错及排障路径

README 命令示例默认使用 `python`/`pip` 风格，保持可直接复制执行。

## ✅ 评审前检查清单

- [ ] 变更范围聚焦且可解释
- [ ] 关键路径已有测试覆盖
- [ ] 全量或相关测试已通过
- [ ] 无敏感信息泄露
- [ ] 文档已同步更新

## 📞 支持资源

如果您有任何问题或需要帮助：

1. 查看项目的 Issues 页面
2. 提交新的 Issue 描述问题
3. 加入社区讨论

我们期待您的贡献！ 🎉