# FastAPI 앱, lifespan (DB init, ChromaDB init, 스케줄러), CORS, 라우터, SPA fallback
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.core.config import settings
from api.core.database import close_pool, init_db
from api.routers import alpaca, dashboard, macro, news, rag, performance
from api.services.news_indexer import get_chroma_client
from api.services.scheduler import get_scheduler, setup_scheduler




logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 리소스를 초기화/정리한다."""
    logger.info("AlphaFlow US starting...")

    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error("Database init failed: %s", e)

    try:
        get_chroma_client()
        logger.info("ChromaDB initialized")
    except Exception as e:
        logger.error("ChromaDB init failed: %s", e)

    try:
        scheduler = setup_scheduler()
        scheduler.start()
        logger.info("Scheduler started")
    except Exception as e:
        logger.error("Scheduler start failed: %s", e)

    logger.info("AlphaFlow US ready on %s:%d", settings.APP_HOST, settings.APP_PORT)
    yield

    logger.info("AlphaFlow US shutting down...")
    try:
        scheduler = get_scheduler()
        scheduler.shutdown(wait=False)
    except Exception:
        pass
    await close_pool()
    logger.info("AlphaFlow US stopped")


app = FastAPI(
    title="AlphaFlow US",
    description="S&P 500 AI Swing Trading Automation System",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router)
app.include_router(news.router)
app.include_router(alpaca.router)
app.include_router(rag.router)
app.include_router(macro.router)
app.include_router(performance.router)

@app.get("/api/health")
async def health_check() -> dict:
    """헬스 체크 엔드포인트."""
    return {"status": "ok", "service": "AlphaFlow US"}


@app.get("/api/ollama/status")
async def ollama_status() -> dict:
    """Ollama 상태를 확인한다."""
    from api.services.ollama_client import health_check
    return await health_check()


@app.post("/api/batch/run")
async def run_batch() -> dict:
    """전체 배치를 수동 실행한다."""
    from api.services.batch import run_full_batch
    return await run_full_batch()



FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")

if os.path.isdir(FRONTEND_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        """SPA fallback: 프론트엔드 index.html을 서빙한다."""
        if full_path.startswith("api/"):
            return JSONResponse({"error": "Not Found"}, status_code=404)

        file_path = os.path.join(FRONTEND_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)

        index_path = os.path.join(FRONTEND_DIR, "index.html")
        if os.path.isfile(index_path):
            return FileResponse(index_path)

        return JSONResponse({"error": "Not Found"}, status_code=404)
