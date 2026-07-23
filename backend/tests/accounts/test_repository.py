import pytest
from sqlalchemy.exc import IntegrityError
from app.modules.accounts.repository import UserRepository
from app.core.security import hash_password

@pytest.mark.asyncio
async def test_create_user_success(db_session):
    repo = UserRepository(db_session)
    user = await repo.create(
        email="test_create@example.com",
        full_name="Test User",
        password=hash_password("password123")
    )
    assert user.id is not None
    assert user.email == "test_create@example.com"
    assert user.full_name == "Test User"
    assert user.is_active is True

from app.core.exceptions import ConflictError

@pytest.mark.asyncio
async def test_create_user_duplicate_email(db_session):
    repo = UserRepository(db_session)
    await repo.create(
        email="duplicate@example.com",
        full_name="User 1",
        password="pwd"
    )
    
    with pytest.raises(ConflictError):
        await repo.create(
            email="duplicate@example.com",
            full_name="User 2",
            password="pwd"
        )

@pytest.mark.asyncio
async def test_get_by_email_found(db_session, make_user):
    await make_user(email="findme@example.com")
    repo = UserRepository(db_session)
    user = await repo.get_by_email("findme@example.com")
    assert user is not None
    assert user.email == "findme@example.com"

@pytest.mark.asyncio
async def test_get_by_email_not_found(db_session):
    repo = UserRepository(db_session)
    user = await repo.get_by_email("doesnotexist@example.com")
    assert user is None
