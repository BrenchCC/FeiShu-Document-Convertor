# 通知系统

## 📢 通知方式

### Webhook 通知（推荐）

**设置方式**：设置 `FEISHU_WEBHOOK_URL` 环境变量。

```bash
# 在 .env 文件中添加
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
```

**优点**：
- 实时接收通知
- 支持富格式消息
- 无需额外配置

**使用场景**：
- 生产环境任务通知
- 重要任务监控

### Chat ID 通知

**设置方式**：使用 `--chat-id` 参数。

```bash
python main.py \
  --source local \
  --path /path/to/docs \
  --write-mode folder \
  --chat-id "oc_xxx"
```

**适用场景**：
- 未配置 webhook 时的备用方案
- 临时任务通知

## 🎚️ 通知级别

### 无通知（none）

关闭所有过程通知，仅在任务失败时显示错误信息。

```bash
python main.py \
  --source local \
  --path /path/to/docs \
  --write-mode folder \
  --notify-level none
```

### 最小通知（minimal）

仅发送关键通知：
- 任务开始
- 任务完成
- 任务失败

```bash
python main.py \
  --source local \
  --path /path/to/docs \
  --write-mode folder \
  --notify-level minimal
```

### 正常通知（normal）

按文件级别通知（默认行为）：
- 任务开始
- 文件处理开始/完成
- 任务完成

```bash
python main.py \
  --source local \
  --path /path/to/docs \
  --write-mode folder \
  --notify-level normal
```

## 📋 通知内容

### 任务开始通知

包含以下信息：
- 任务 ID
- 数据源类型
- 源路径/仓库
- 写入模式
- 预计处理文件数量

### 文件处理通知

包含以下信息：
- 文件路径
- 处理状态（成功/失败）
- 处理时间
- 错误信息（失败时）

### 任务完成通知

包含以下信息：
- 任务 ID
- 处理统计（成功/失败文件数）
- 总耗时
- 失败文件列表（如有）

## 🔧 环境变量

### FEISHU_WEBHOOK_URL

飞书机器人 webhook 地址。

**获取方式**：
1. 打开飞书群组
2. 点击「设置」→「群机器人」→「添加机器人」
3. 选择「自定义机器人」
4. 复制 webhook 地址

**示例**：
```
https://open.feishu.cn/open-apis/bot/v2/hook/7a3c3d8e-1234-5678-9abc-1234567890ab
```

### 安全提示

- Webhook 地址包含敏感信息，请妥善保管
- 不要将 webhook 地址提交到代码仓库
- 建议使用环境变量或 `.env` 文件配置

## 🐛 常见问题

### 通知未收到

**检查清单**：
1. Webhook 地址是否正确
2. 网络连接是否正常
3. 机器人是否被禁用
4. 通知级别是否设置正确

**解决方法**：
1. 测试 webhook 是否可用
2. 检查日志文件中的错误信息
3. 尝试使用最小通知级别
4. 重新启动任务

### 通知格式异常

**可能原因**：
- 飞书 API 变更
- 网络传输问题
- 文档内容包含特殊字符

**解决方法**：
1. 更新到最新版本
2. 检查文档内容
3. 尝试使用其他通知方式