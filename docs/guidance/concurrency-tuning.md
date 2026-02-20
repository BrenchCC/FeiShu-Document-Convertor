# 并发调优建议

## 🔄 并发参数概述

### 文档级并发（--max-workers）

控制同时处理的文档数量。每个文档处理会启动独立的子进程。

**建议范围**：`2~4`

**原因**：
- 飞书 API 在更高并发下更容易出现 `1770006 schema mismatch` 或抖动
- 单个进程已经能很好地利用 CPU 和内存资源
- 更高的并发会显著增加 API 失败的风险

### 分片处理并发（--chunk-workers）

控制单个文档的分片计算并发。这是线程级别的并发。

**建议范围**：`min(CPU 逻辑核数, 8)`

**原因**：
- 分片计算是 CPU 密集型任务
- 过多的线程会导致上下文切换开销
- 8 个线程在大多数场景下已经足够

## 📊 推荐配置组合

### 小型任务（< 100 个文档）

```bash
--max-workers 2 --chunk-workers 4
```

**适用场景**：
- 文档数量较少
- 文档内容较短
- 网络条件一般

### 中型任务（100~500 个文档）

```bash
--max-workers 3 --chunk-workers 4
```

**适用场景**：
- 文档数量适中
- 文档内容长度适中
- 网络条件良好

### 大型任务（> 500 个文档）

```bash
--max-workers 4 --chunk-workers 6
```

**适用场景**：
- 文档数量非常多
- 文档内容较长
- 网络条件优秀

## 🎯 调优策略

### 1. 初始配置

使用推荐的默认配置：

```bash
--max-workers 2 --chunk-workers 4
```

### 2. 观察指标

运行任务时关注以下指标：
- 文档处理成功率
- API 错误率
- CPU 使用率
- 内存使用率
- 任务总耗时

### 3. 调整策略

#### 当遇到 API 错误时

- 优先降低 `--max-workers`
- 再考虑降低 `--chunk-workers`
- 检查错误类型（如 `1770006` 是 schema mismatch）

#### 当文档处理缓慢时

- 检查网络延迟
- 检查 CPU 和内存使用率
- 适度增加 `--chunk-workers`（如果 CPU 还有余力）

#### 当任务总耗时过长时

- 在不增加 API 错误率的前提下，适当增加 `--max-workers`
- 考虑优化文档内容大小

## 🔍 监控与调试

### 日志分析

每次运行都会生成独立日志：`logs/knowledge_generator_<timestamp>_<pid>.log`

关注关键字：
- `group submitted`：分组提交任务
- `group finished`：分组任务完成
- `group failed`：分组任务失败

### 日志保留策略

系统会自动仅保留最近 8 份日志文件。

### 常见问题

#### 1. 任务看起来卡住

**现象**：终端一段时间无明显输出

**解决方法**：
1. 查看日志文件中的处理进度
2. 关注分组处理情况
3. 考虑降低 `--max-workers`

#### 2. API 错误频繁

**现象**：出现大量 `1770006 schema mismatch` 或超时

**解决方法**：
1. 降低 `--max-workers` 到 2
2. 检查网络稳定性
3. 考虑调整 API 重试策略

#### 3. 内存使用率过高

**现象**：系统出现 OOM 或 swap 使用过多

**解决方法**：
1. 降低 `--max-workers`
2. 检查文档内容是否包含大量图片或大型文件
3. 考虑增加系统内存

## 💡 实战经验

### 最佳实践

1. 先使用 `--dry-run` 测试任务规模
2. 从保守配置开始
3. 逐步增加并发参数
4. 监控关键指标
5. 根据实际情况调整

### 典型场景

#### 场景一：本地目录导入到云盘文件夹

```bash
python main.py \
  --source local \
  --path /path/to/docs \
  --write-mode folder \
  --folder-subdirs \
  --max-workers 3 \
  --chunk-workers 4
```

#### 场景二：GitHub 仓库导入到知识库

```bash
python main.py \
  --source github \
  --repo BrenchCC/llm-transformer-book \
  --write-mode wiki \
  --space-name "LLM Transformer" \
  --oauth-local-server \
  --max-workers 2 \
  --chunk-workers 4
```

## 📝 总结

并发调优是一个平衡过程，需要在处理速度和稳定性之间找到最佳点。建议：
- 保持 `--max-workers` 在 2~4 范围内
- 根据 CPU 性能调整 `--chunk-workers`
- 监控并及时调整参数
- 保留日志以便分析问题