# Contributing Guide

感谢你为 `knowledge_generator` 做贡献。本指南用于统一提交质量、降低评审沟通成本。

## 贡献范围

欢迎以下类型的贡献：
- Bug 修复
- 新功能实现
- 测试补充与稳定性改进
- 文档改进（README、示例命令、排障说明）

## 开始之前

1. 确认变更目标明确：建议先提 Issue 或在已有 Issue 下认领。
2. 避免大而全改动：优先小步提交，单个 PR 聚焦一个问题。
3. 涉及行为变更时，务必同步测试与文档。

## 本地开发

### 环境准备

```bash
pip install -r requirements.txt
```

如需真实写入飞书，请先配置 `.env`（可参考 `.env.example`）。

### 快速自检

```bash
# 仅验证流程，不写远端
python main.py --source local --path . --write-mode folder --dry-run --notify-level none
```

## 代码规范

请遵循仓库内约定（见 `AGENTS.md`）：
- Python 使用 4 空格缩进。
- 函数建议带类型注解。
- 函数必须有英文 docstring，说明参数语义。
- 注释使用英文。
- import 分组：标准库 / 第三方 / 本地模块。
- 参数与赋值格式保持现有风格：`arg = value`。
- `argparse` 参数解析放在 `parse_args()` 中。

## 测试规范

- 测试框架：`unittest`
- 测试文件命名：`tests/test_<feature>.py`
- 每次行为变更都要补充或更新测试，至少覆盖：
  - 成功路径
  - 失败路径
  - 关键边界条件

推荐命令：

```bash
# 全量测试
python -m unittest discover -s tests -v

# 运行单个测试模块
python -m unittest tests.test_orchestrator -v
```

## 提交规范

推荐提交信息格式：

```text
type(scope): summary
```

示例：
- `fix(orchestrator): handle grouped import keyboard interrupt`
- `docs(readme): clarify max-workers recommendation`
- `test(feishu): add schema mismatch retry cases`

## Pull Request 规范

PR 描述建议包含以下内容：
- 变更目标（解决什么问题）
- 主要改动模块（涉及哪些文件）
- 测试命令与结果摘要
- 兼容性/行为变化说明
- 是否需要更新 `.env` 配置项

建议附上最小可复现命令，便于评审验证。

## 安全与敏感信息

- 不要提交 `.env`、token、密钥、用户隐私数据。
- 不要在日志、截图、PR 描述中泄露密钥或 chat_id 等敏感信息。
- 与飞书接口相关的错误日志请优先脱敏后再分享。

## 文档更新要求

当出现以下情况时，请同步更新文档：
- CLI 参数含义或默认值变化
- 导入流程变化（如并发、目录策略、fallback 逻辑）
- 新增常见报错及排障路径

README 命令示例默认使用 `python`/`pip` 风格，保持可直接复制执行。

## 评审前检查清单

- [ ] 变更范围聚焦且可解释
- [ ] 关键路径已有测试覆盖
- [ ] 全量或相关测试已通过
- [ ] 无敏感信息泄露
- [ ] 文档已同步更新

