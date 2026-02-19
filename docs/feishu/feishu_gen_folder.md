# 多级目录导入：先建一级子文件夹的设计方案

## 目标
- 当源目录是多级结构（如 `examples/ai-agent-book/zh`）时，不直接把所有内容写到 `FEISHU_FOLDER_TOKEN` 根下。
- 先创建一个“任务级子文件夹”，再把章节文档和自动导航文档写入该子文件夹（以及其内部层级）。
- 保持 `wiki` 编排不变，优化 `folder` 侧可管理性。

## 设计思路

### 1) 新增参数
- `--folder-root-subdir` / `--no-folder-root-subdir`
  - 默认建议：`True`（仅在 `write-mode` 包含 `folder` 时生效）
- `--folder-root-subdir-name <name>`
  - 可选；未传时自动生成

### 2) 子文件夹命名规则（自动）
- 优先：`--folder-root-subdir-name`
- 否则自动：`<source_name>-<yyyyMMdd-HHmm>`
  - `local`：取 `--path` 最后一级目录名（如 `zh`）
  - `github`：取仓库名或 `repo/subdir` 最后一级

### 3) 写入路径策略
- 若 `folder_root_subdir = True`：
  - 在 `FEISHU_FOLDER_TOKEN` 下 `ensure/create` 一级子文件夹（任务根）
  - `folder_subdirs = False`：所有 md 文档都写入任务根
  - `folder_subdirs = True`：在任务根下继续按 `relative_dir` 建子层级
- 自动导航文档写入任务根（不写到更深层）

### 4) 兼容性
- 不影响 `wiki` 节点编排和 `move_doc_to_wiki` 行为
- 不影响 title fallback、convert fallback、失败不中断机制
- `--no-folder-root-subdir` 时行为与当前版本一致

### 5) 日志与可观测性
- 增加结构化日志：
  - `robot_push | stage = folder_root_created | folder_token = ...`
  - `robot_push | stage = folder_root_reused | folder_token = ...`
  - `robot_push | stage = doc_created | ...`
  - `robot_push | stage = folder_nav_created | ...`

### 6) 验收标准
- 对 `--source local --path examples/ai-agent-book/zh --write-mode folder --folder-subdirs`：
  - 在目标根目录下只新增一个任务级子文件夹
  - 48 个 md + 1 个导航文档都在该任务子树内
  - 不与历史导入批次混写
  - 日志可完整追踪 `root folder -> doc -> nav`
