"""
API路由初始化模块

聚合所有API路由，提供统一的路由入口
"""

from web.api.system import router as system_router
from web.api.sources import router as sources_router
from web.api.import_router import router as import_router
from web.api.tasks import router as tasks_router
from web.api.notifications import router as notifications_router

__all__ = [
    "system_router",
    "sources_router",
    "import_router",
    "tasks_router",
    "notifications_router"
]
