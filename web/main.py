"""
飞书文档转换器Web应用主入口

提供基于FastAPI的Web接口，支持文档导入任务的创建、监控和管理。
"""

import logging
import sys

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from web.config import settings

# 添加项目根目录到Python路径
sys.path.insert(0, '/Users/brench/brench_project_collections/Self_Learning_Project/FeiShu-Document-Convertor')

# 配置日志
logging.basicConfig(
    level = logging.INFO,
    format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers = [logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

# 创建FastAPI应用
app = FastAPI(
    title = "飞书文档转换器API",
    description = "用于将本地目录或GitHub仓库中的Markdown文档导入飞书云文档或知识库的Web API",
    version = "1.0.0",
    docs_url = "/docs",
    redoc_url = "/redoc"
)

# 配置CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins = ["*"],
    allow_credentials = True,
    allow_methods = ["*"],
    allow_headers = ["*"],
)

# 挂载静态文件（前端页面）
app.mount("/static", StaticFiles(directory = "/Users/brench/brench_project_collections/Self_Learning_Project/FeiShu-Document-Convertor/web"), name = "static")
app.mount("/assets", StaticFiles(directory = "/Users/brench/brench_project_collections/Self_Learning_Project/FeiShu-Document-Convertor/assets"), name = "assets")

# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理"""
    logger.error(f"请求 {request.url} 失败: {str(exc)}", exc_info = True)
    return JSONResponse(
        status_code = 500,
        content = {"error": "内部服务器错误", "message": str(exc)}
    )

# 导入API路由
from web.api import system, sources, import_router, tasks, notifications

app.include_router(system.router, prefix = "/api/system", tags = ["系统管理"])
app.include_router(sources.router, prefix = "/api/sources", tags = ["源管理"])
app.include_router(import_router, prefix = "/api/import", tags = ["导入管理"])
app.include_router(tasks.router, prefix = "/api/tasks", tags = ["任务管理"])
app.include_router(notifications.router, prefix = "/api/notifications", tags = ["通知管理"])

# 健康检查接口
@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "ok", "version": "1.0.0"}

# 根路径重定向到前端页面
@app.get("/")
async def root():
    """根路径重定向到前端页面"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url = "/static/index.html")

if __name__ == "__main__":
    # 启动服务器
    logger.info("=" * 80)
    logger.info("飞书文档转换器Web服务启动")
    logger.info("=" * 80)

    host = settings.WEB_HOST
    port = settings.WEB_PORT
    public_base_url = settings.WEB_PUBLIC_BASE_URL.strip()
    if not public_base_url:
        if host in {"0.0.0.0", "::"}:
            public_base_url = f"http://localhost:{port}"
        else:
            public_base_url = f"http://{host}:{port}"

    logger.info("WEB_HOST = %s", host)
    logger.info("WEB_PORT = %d", port)
    logger.info("WEB_PUBLIC_BASE_URL = %s", public_base_url)

    uvicorn.run(
        "web.main:app",
        host = host,
        port = port,
        reload = settings.WEB_RELOAD
    )
