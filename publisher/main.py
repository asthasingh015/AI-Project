"""FastAPI application entrypoint for the Cortex AI Publisher module.

Lifespan (modern asynccontextmanager):
    startup  -> logging -> database init -> scheduler start
    shutdown -> scheduler stop -> dispose database engine
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from publisher.config import settings
from publisher.database import SessionLocal, engine, init_db
from publisher.routes import dashboard, feed, publish, stats
from publisher.scheduler import scheduler_manager
from publisher.utils.logger import get_logger, setup_logging

logger = get_logger("publisher.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown hooks."""
    setup_logging()
    logger.info(
        "Starting %s v%s (environment=%s)",
        settings.app_name,
        settings.app_version,
        settings.environment,
    )

    await init_db()
    scheduler_manager.start()

    try:
        yield
    finally:
        scheduler_manager.shutdown()
        await engine.dispose()
        logger.info("Shutdown complete")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.include_router(feed.router)
app.include_router(dashboard.router)
app.include_router(stats.router)
app.include_router(publish.router)


@app.get("/", response_model=dict)
async def root() -> dict:
    """Simple health endpoint."""
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
    }


@app.get("/health")
async def health() -> JSONResponse:
    """Detailed health check including database and scheduler state."""
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        database_status = "connected"
    except Exception as exc:
        logger.error("Health check database failure: %s", exc)
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "service": settings.app_name,
                "version": settings.app_version,
                "scheduler_status": scheduler_manager.status,
                "database": "unreachable",
            },
        )

    ai_provider = "none"
    if settings.openai_api_key:
        ai_provider = "openai"
    elif settings.gemini_api_key:
        ai_provider = "gemini"

    return JSONResponse(
        content={
            "status": "running",
            "service": settings.app_name,
            "version": settings.app_version,
            "scheduler_status": scheduler_manager.status,
            "database": database_status,
            "ai_provider": ai_provider,
        }
    )
