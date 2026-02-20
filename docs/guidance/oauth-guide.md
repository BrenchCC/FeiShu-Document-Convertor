# OAuth 授权使用指南

## 🔐 重要说明

使用 `wiki` 模式需要用户级权限，必须配置 OAuth。

## 🚀 授权方式

### A. 本地回调自动授权（推荐）

这是最简单且推荐的授权方式，系统会自动启动本地服务器处理 OAuth 回调。

#### 配置步骤

1. 在飞书后台配置回调地址白名单：
   - 地址：`http://127.0.0.1:8765/callback`
   - 确保协议、域名、端口和路径完全一致

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

#### 工作流程

1. 系统会自动打开浏览器访问飞书授权页面
2. 用户在浏览器中完成授权
3. 系统自动获取授权码并交换访问令牌
4. 令牌会自动缓存到 `cache/user_token.json`

### B. 手动授权码换 Token

如果无法使用本地回调（如在无 GUI 环境下），可以使用手动授权方式。

#### 步骤

1. 使用 `--print-auth-url` 参数获取授权链接：

```bash
python main.py \
  --source github \
  --repo BrenchCC/Context_Engineering_Analysis \
  --write-mode wiki \
  --space-name Context_Engineering_Analysis \
  --print-auth-url \
  --oauth-redirect-uri "http://127.0.0.1:8765/callback"
```

2. 在浏览器中打开返回的授权链接，完成授权
3. 授权成功后，飞书会显示授权码
4. 使用授权码运行命令：

```bash
python main.py \
  --source github \
  --repo BrenchCC/Context_Engineering_Analysis \
  --write-mode wiki \
  --space-name Context_Engineering_Analysis \
  --auth-code "<你的授权码>" \
  --oauth-redirect-uri "http://127.0.0.1:8765/callback"
```

## ⚙️ OAuth 相关参数

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

## 🐛 常见问题

### 1. 授权失败：`20029 redirect_uri 请求不合法`

**原因**：回调地址与飞书后台配置的白名单不匹配。

**检查清单**：
- 协议（http/https）是否匹配
- 域名/IP 是否一致
- 端口是否相同
- 路径是否完全一致（包括 `/callback`）
- 是否有多余的参数或路径

**解决方法**：
1. 确认飞书后台白名单配置正确
2. 确保命令中的 `--oauth-redirect-uri` 参数与白名单完全一致
3. 重新运行授权流程

### 2. 授权页面无法访问

**可能原因**：
- 本地服务器未正常启动
- 端口被其他程序占用
- 防火墙阻止了访问

**解决方法**：
1. 检查端口是否被占用（默认 8765）
2. 尝试使用其他端口（需同时修改飞书后台配置）
3. 关闭防火墙或添加白名单

### 3. 授权成功但无法创建知识库

**错误信息**：`Create wiki space requires user_access_token`

**原因**：系统无法获取有效的用户访问令牌。

**解决方法**：
1. 确保用户 token 已正确缓存到 `cache/user_token.json`
2. 检查 token 文件权限
3. 尝试重新授权