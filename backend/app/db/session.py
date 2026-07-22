"""
Async database session management.

Provides:
1. An async SQLAlchemy engine (connection pool to PostgreSQL)
2. A session factory that creates new sessions
3. A FastAPI dependency that yields sessions (auto-closes on request end)

The key insight: each HTTP request gets its own database session.
When the request finishes (success or error), the session is closed.
This prevents connection leaks and ensures transaction isolation.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

def _get_async_url() -> str:
    """
    Convert the standard psycopg URL to the async variant.
    
    SQLAlchemy requires different URL schemes for sync vs async:
    - Sync:  postgresql+psycopg://...
    - Async: postgresql+psycopg_async://...
    
    We store the sync version in .env (simpler, works with alembic)
    and convert here for the async engine.
    """
    return settings.DATABASE_URL.replace(
        "postgresql+psycopg://",
        "postgresql+psycopg_async://",
    )


# ── Engine ──
# The engine manages a pool of database connections.
engine = create_async_engine(
    _get_async_url(),
    echo=False,
    pool_size=10,        # Max connections in the pool
    max_overflow=20,     # Extra connections allowed during traffic spikes
    pool_recycle=3600,   # Recreate connections after 1 hour (prevents stale connections)
)


# ── Session Factory ──
# Creates new AsyncSession instances. Each session = one unit of work.
# expire_on_commit=False: objects remain usable after commit
#   (without this, accessing user.email after commit() raises an error)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    """
    FastAPI dependency that provides a database session.
    
    Usage in a route:
        @router.get("/users")
        async def list_users(db: AsyncSession = Depends(get_db)):
            ...
    
    The `yield` makes this a generator dependency:
    1. FastAPI calls next() → creates and yields the session
    2. Your route handler runs with the session
    3. FastAPI calls next() again → the `finally` block closes the session
    
    This guarantees the session is ALWAYS closed, even if the handler raises an exception.
    """

    async with AsyncSessionLocal() as session:
        try: 
            yield session
        finally:
            await session.close()
