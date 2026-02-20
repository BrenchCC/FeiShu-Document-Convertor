"""
Feishu document converter web entrypoint.

Provides FastAPI endpoints for import task creation and monitoring.
"""
import os
import sys
import logging
from importlib import import_module
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from web.config import settings
from config.config import get_project_root
from utils.logging_setup import configure_web_logging

system_api = import_module("web.api.system")
sources_api = import_module("web.api.sources")
import_router_api = import_module("web.api.import_router")
tasks_api = import_module("web.api.tasks")
notifications_api = import_module("web.api.notifications")


logger = logging.getLogger(__name__)

app = FastAPI(
    title = "飞书文档转换器API",
    description = "用于将本地目录或GitHub仓库中的Markdown文档导入飞书云文档或知识库的Web API",
    version = "1.0.0",
    docs_url = "/docs",
    redoc_url = "/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins = ["*"],
    allow_credentials = True,
    allow_methods = ["*"],
    allow_headers = ["*"],
)

project_root = get_project_root()
static_dir = project_root / "web"
assets_dir = project_root / "assets"
app.mount("/static", StaticFiles(directory = str(static_dir)), name = "static")
app.mount("/assets", StaticFiles(directory = str(assets_dir)), name = "assets")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unhandled exceptions for API requests.

    Args:
        request: FastAPI request.
        exc: Exception instance.
    """

    logger.error("Request %s failed: %s", request.url, str(exc), exc_info = True)
    return JSONResponse(
        status_code = 500,
        content = {"error": "内部服务器错误", "message": str(exc)}
    )


app.include_router(system_api.router, prefix = "/api/system", tags = ["系统管理"])
app.include_router(sources_api.router, prefix = "/api/sources", tags = ["源管理"])
app.include_router(import_router_api.router, prefix = "/api/import", tags = ["导入管理"])
app.include_router(tasks_api.router, prefix = "/api/tasks", tags = ["任务管理"])
app.include_router(notifications_api.router, prefix = "/api/notifications", tags = ["通知管理"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""

    return {"status": "ok", "version": "1.0.0"}


@app.get("/")
async def root():
    """Redirect to the frontend index page."""

    from fastapi.responses import RedirectResponse
    return RedirectResponse(url = "/static/index.html")


if __name__ == "__main__":
    configure_web_logging(level = logging.INFO)

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
        reload = settings.WEB_RELOAD,
        log_level = settings.LOG_LEVEL.lower(),
        access_log = True,
        log_config = None
    )
