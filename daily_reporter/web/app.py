# -*- coding: utf-8 -*-
"""FastAPI 应用工厂与服务启动"""

import threading
import webbrowser
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .routes.snapshots import router as snapshots_router
from .routes.reports import router as reports_router
from .routes.compare import router as compare_router
from .routes.watch import router as watch_router
from .routes.config_route import router as config_router
from .routes.stats import router as stats_router
from .deps import set_config_path

_WEB_DIR = Path(__file__).parent
_TEMPLATES_DIR = _WEB_DIR / "templates"
_STATIC_DIR = _WEB_DIR / "static"


def create_app(config_path: Path) -> FastAPI:
    set_config_path(config_path)

    app = FastAPI(
        title="Kgent V3 Web",
        description="本地文件变更监控 · Web 管理界面",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API 路由
    app.include_router(snapshots_router, prefix="/api/snapshots", tags=["Snapshots"])
    app.include_router(reports_router,   prefix="/api/reports",   tags=["Reports"])
    app.include_router(compare_router,   prefix="/api/compare",   tags=["Compare"])
    app.include_router(watch_router,     prefix="/api/watch",     tags=["Watch"])
    app.include_router(config_router,    prefix="/api/config",    tags=["Config"])
    app.include_router(stats_router,     prefix="/api/stats",     tags=["Stats"])

    # 静态资源
    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # SPA 入口：所有非 /api 路径均返回 index.html
    index_html = _TEMPLATES_DIR / "index.html"

    @app.get("/", include_in_schema=False)
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str = ""):
        # /api 前缀路径不应走 SPA，返回 JSON 404
        if full_path.startswith("api/") or full_path == "api":
            from fastapi.responses import JSONResponse
            return JSONResponse({"ok": False, "detail": "Not Found"}, status_code=404)
        return FileResponse(str(index_html))

    return app


def run_server(
    config_path: Path,
    host: str = "127.0.0.1",
    port: int = 7421,
    open_browser: bool = True,
) -> None:
    """启动 uvicorn 服务（阻塞），可选自动打开浏览器。"""
    try:
        import uvicorn
    except ImportError:
        raise SystemExit(
            "[错误] 未安装 uvicorn，请执行: pip install uvicorn[standard]"
        )

    app = create_app(config_path)
    url = f"http://{host}:{port}"

    if open_browser:
        # 延迟 1.2s 等待服务就绪再打开浏览器
        def _open():
            import time
            time.sleep(1.2)
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()

    print(f"[Web] 服务启动：{url}")
    print("[Web] 按 Ctrl+C 退出")
    uvicorn.run(app, host=host, port=port, log_level="warning")
