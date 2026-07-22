"""
FastAPI application factory.

Creates, configures, and returns the complete FastAPI application.
All middleware, exception handlers, and routes are wired here.
"""

from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan: startup and shutdown.
    
    Startup:
        - Connect to Redis
        - Log readiness
    
    Shutdown:
        - Close Redis connection gracefully
    """
    settings = get_settings()

    # ── Startup ──
    app.state.redis = aioredis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )

    # Verify Redis is reachable
    await app.state.redis.ping()
    print("Connected to Redis")

    yield

    # ── Shutdown ──
    await app.state.redis.close()
    print("Redis connection closed")


def create_app() -> FastAPI:
    """
    Build the complete FastAPI application.
    """

    # ── Configure logging first (before anything else logs) ──
    setup_logging()

    settings = get_settings()

    app = FastAPI(
        title="Document RAG System",
        description="Document Intelligence Platform — RAG Backend",
        version="0.1.0",
        lifespan=lifespan,
    )

    # ── CORS ──
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception Handlers ──
    register_exception_handlers(app)

    from app.api.v1.router import api_v1_router
    app.include_router(api_v1_router)

    # ── Health Check ──
    @app.get("/health", tags=["system"])
    async def health_check():
        """
        Health check endpoint.
        
        Validates connectivity to both PostgreSQL and Redis.
        Docker uses this to know when the container is ready to serve traffic.
        """
        health = {"status": "ok", "service": "docrag-api"}

        # Check Redis
        try:
            await app.state.redis.ping()
            health["redis"] = "connected"
        except Exception:
            health["redis"] = "disconnected"
            health["status"] = "degraded"

        # Check PostgreSQL
        try:
            from app.db.session import engine
            async with engine.connect() as conn:
                await conn.execute(
                    __import__("sqlalchemy").text("SELECT 1")
                )
            health["database"] = "connected"
        except Exception:
            health["database"] = "disconnected"
            health["status"] = "degraded"

        return health

    return app
