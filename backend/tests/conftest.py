import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

# Must set before importing settings so it loads .env.test
os.environ["ENV_FILE"] = ".env.test"

from app.core.config import get_settings
from app.db.session import get_db
from app.main import app

settings = get_settings()

def get_async_test_url() -> str:
    return settings.DATABASE_URL.replace(
        "postgresql+psycopg://",
        "postgresql+psycopg_async://",
    )

# 1. Ensure test database schema
@pytest.fixture(scope="session", autouse=True)
def _ensure_test_db_schema():
    """
    Run Alembic migrations to setup the test schema.
    This runs once per test session.
    """
    import alembic.config
    import alembic.command
    alembic_cfg = alembic.config.Config("alembic.ini")
    # Tell alembic to use the test database
    alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    alembic.command.upgrade(alembic_cfg, "head")


# 2. Engine fixture
@pytest_asyncio.fixture(scope="session")
async def db_engine():
    engine = create_async_engine(
        get_async_test_url(),
        echo=False,
        pool_size=5,
        max_overflow=10,
    )
    yield engine
    await engine.dispose()


# 3. Connection fixture
@pytest_asyncio.fixture(scope="function")
async def db_connection(db_engine):
    """
    Create a new connection and start an outer transaction for the test.
    """
    async with db_engine.begin() as conn:
        yield conn
        await conn.rollback()  # Rollback outer transaction, wiping all test data


# 4. Session fixture
@pytest_asyncio.fixture(scope="function")
async def db_session(db_connection):
    """
    Provide an AsyncSession that creates savepoints instead of committing.
    """
    session = AsyncSession(
        bind=db_connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint"
    )
    yield session
    await session.close()


# 5. FastAPI App fixture
@pytest.fixture(scope="function")
def test_app(db_session):
    """
    Provide the FastAPI app with the get_db dependency overridden.
    """
    async def override_get_db():
        yield db_session
        
    app.dependency_overrides[get_db] = override_get_db
    
    # Mock redis to avoid AttributeError in tests
    from unittest.mock import AsyncMock
    if not hasattr(app.state, "redis"):
        mock_redis = AsyncMock()
        mock_redis.incr.return_value = 1
        mock_redis.expire.return_value = True
        app.state.redis = mock_redis
        
    yield app
    app.dependency_overrides.clear()


# 6. HTTPX Client fixture
@pytest_asyncio.fixture(scope="function")
async def client(test_app):
    """
    Async client for testing the API.
    """
    async with AsyncClient(
        transport=ASGITransport(app=test_app), 
        base_url="http://testserver"
    ) as ac:
        yield ac


# 7. User Factory fixture
@pytest_asyncio.fixture(scope="function")
async def make_user(db_session):
    """
    Factory to quickly create users for tests, bypassing HTTP.
    """
    from app.modules.accounts.repository import UserRepository
    from app.core.security import hash_password
    
    async def _make_user(**overrides):
        defaults = {
            "email": "test@example.com", 
            "full_name": "Test User",
            "password": hash_password("Str0ngPass!"), 
        }
        # Hash the password if overridden
        if "password" in overrides:
            overrides["password"] = hash_password(overrides["password"])
            
        is_active = overrides.pop("is_active", True)

        defaults.update(overrides)
        repo = UserRepository(db_session)
        user = await repo.create(**defaults)
        
        # We might also want to set is_active directly on the model if overridden
        if not is_active:
            user.is_active = False
            
        await db_session.commit()
        return user
        
    return _make_user


# 7.5. Workspace Factory fixture
@pytest_asyncio.fixture(scope="function")
async def make_workspace(db_session, make_user):
    """
    Factory to quickly create workspaces for tests, bypassing HTTP.
    Optionally pass an `owner` user to set as the initial owner.
    """
    from app.modules.workspaces.repository import WorkspaceRepository
    from app.modules.workspaces.models import WorkspaceRole
    
    async def _make_workspace(owner=None, **overrides):
        defaults = {
            "name": "Test Workspace",
        }
        defaults.update(overrides)
        
        repo = WorkspaceRepository(db_session)
        workspace = await repo.create_workspace(name=defaults["name"])
        
        if not owner:
            import uuid
            owner = await make_user(email=f"owner_{uuid.uuid4()}@example.com")
            
        await repo.add_member(
            workspace_id=workspace.id,
            user_id=owner.id,
            role=WorkspaceRole.OWNER
        )
        
        await db_session.commit()
        return workspace, owner
        
    return _make_workspace


# 8. Auth Client fixture
@pytest_asyncio.fixture(scope="function")
async def auth_client(client, make_user, db_session):
    """
    Client pre-loaded with a valid access token.
    """
    user = await make_user()
    
    from app.modules.accounts.service import AccountService
    service = AccountService(db_session)
    tokens = await service.issue_tokens(user)
    
    client.cookies.set(settings.ACCESS_COOKIE_NAME, tokens["access_token"])
    client.cookies.set(settings.REFRESH_COOKIE_NAME, tokens["refresh_token"])
    
    # Store user id for assertions
    client.current_user_id = user.id
    client.current_user = user
    
    return client


# 9. Frozen Time fixture
@pytest.fixture
def frozen_time():
    """
    Freeze time for testing token expirations.
    Yields the freezegun freezer object so tests can move time forward.
    """
    from freezegun import freeze_time
    with freeze_time() as freezer:
        yield freezer
