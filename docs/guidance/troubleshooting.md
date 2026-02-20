# 常见问题与解决方案

## 📋 问题分类

### 表格处理

#### 问题 1：表格导入失败

**错误信息**：飞书 API 返回 `1770001 invalid param`（参数不合法）

**解决方法**：我们的代码已自动优化，对表格块使用直接降级策略，避免了 API 限制。现在表格块会直接转换为文本块，确保导入成功。

**技术原理**：
```python
# 在 write_markdown_by_block_matching 方法中
if segment.kind == "table":
    logger.info("Direct fallback for table block")
    self._write_segment_by_native_blocks(
        document_id, segment.kind, segment_content
    )
    continue
```

### OAuth 授权

#### 问题 2：OAuth 授权失败

**错误信息**：`20029 redirect_uri 请求不合法`

**检查清单**：
1. 飞书后台白名单配置是否与 `--oauth-redirect-uri` 完全一致
2. 协议（http/https）是否匹配
3. 端口是否相同
4. 路径是否一致

**解决方法**：
1. 确认飞书后台白名单配置正确
2. 确保命令中的 `--oauth-redirect-uri` 参数与白名单完全一致
3. 重新运行授权流程

#### 问题 3：知识库创建失败

**错误信息**：`Create wiki space requires user_access_token`

**解决方法**：
1. 使用 `--oauth-local-server` 自动授权
2. 或使用 `--auth-code` 手动授权
3. 或改用 `--space-id` 写入已有空间

### GitHub 仓库访问

#### 问题 4：GitHub 仓库无法访问

**错误信息**：Git 克隆失败或网络超时

**解决方法**：
1. 检查网络连接
2. 尝试使用代理
3. 程序会自动尝试 `gh-proxy` 回退

### 并发问题

#### 问题 5：并发开启后出现 `schema mismatch` 或“看起来卡住”

**错误信息**：开启多进程后返回 `1770006 schema mismatch`，或终端一段时间无明显输出

**解决方法**：
1. 优先将 `--max-workers` 调低到 `2` 或 `3`
2. 将 `--chunk-workers` 设为 `CPU 逻辑核数` 或更低
3. 查看 `logs/` 下最新日志文件，关注 `group submitted/group finished/group failed` 关键字

### 其他常见问题

#### 问题 6：任务无法开始

**可能原因**：
- 环境变量未正确配置
- 飞书应用配置错误
- 源路径不存在

**检查点**：
1. 确认 `.env` 文件已正确配置
2. 检查 `FEISHU_APP_ID` 和 `FEISHU_APP_SECRET` 是否正确
3. 确认源路径是否存在
4. 检查网络连接

#### 问题 7：文档上传失败

**可能原因**：
- 文件过大
- 文件格式不支持
- 网络超时

**解决方法**：
1. 检查文档大小（建议单个 Markdown 文件不超过 10MB）
2. 确认文件格式为 `.md` 或 `.markdown`
3. 检查网络稳定性
4. 尝试降低并发参数

#### 问题 8：通知未收到

**可能原因**：
- Webhook 地址错误
- 网络连接问题
- 机器人被禁用

**解决方法**：
1. 测试 webhook 是否可用
2. 检查网络连接
3. 确认机器人是否被禁用
4. 尝试使用最小通知级别

#### 问题 9：任务进度显示异常

**可能原因**：
- 文档处理速度差异大
- 某些文档处理耗时过长
- 网络抖动

**解决方法**：
1. 查看日志文件了解具体进度
2. 耐心等待任务完成
3. 如果长时间无响应，考虑停止任务并检查日志

#### 问题 10：内存使用率过高

**可能原因**：
- 文档数量过多
- 文档内容包含大量图片
- 并发参数设置过高

**解决方法**：
1. 降低 `--max-workers` 参数
2. 考虑分批处理文档
3. 检查是否有特别大的文档
4. 增加系统内存

## 🔍 通用排错步骤

### 1. 检查环境变量

确保 `.env` 文件包含以下必要配置：
```
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_FOLDER_TOKEN=
FEISHU_WEBHOOK_URL=
```

### 2. 查看日志文件

每次运行都会生成日志文件：`logs/knowledge_generator_<timestamp>_<pid>.log`

**关注关键字**：
- `ERROR`：错误信息
- `WARNING`：警告信息
- `group submitted`：分组任务开始
- `group finished`：分组任务完成
- `group failed`：分组任务失败

### 3. 测试任务

使用 `--dry-run` 模式测试任务：
```bash
python main.py \
  --source local \
  --path /path/to/docs \
  --write-mode folder \
  --dry-run \
  --notify-level none
```

### 4. 检查网络连接

- 测试飞书 API 连通性
- 检查 GitHub 访问是否正常
- 确认代理设置（如使用代理）

## 📞 支持资源

如果问题无法解决，请：
1. 查看项目的 Issues 页面
2. 提交新的 Issue 描述问题
3. 加入社区讨论