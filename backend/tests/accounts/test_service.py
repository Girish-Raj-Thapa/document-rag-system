import pytest
from app.core.exceptions import AuthenticationError, ConflictError
from app.modules.accounts.service import AccountService
from app.modules.accounts.schemas import RegisterRequest, LoginRequest
from app.core.security import verify_password
from app.core.schemas import TokenPayload

@pytest.mark.asyncio
async def test_register_user_success(db_session):
    service = AccountService(db_session)
    payload = RegisterRequest(
        email="NewUser@Example.com",  # mixed case to test normalization
        full_name=" New User ",       # trailing spaces
        password="MySecretPassword123"
    )
    user = await service.register_user(payload)
    
    assert user.id is not None
    assert user.email == "newuser@example.com"
    assert user.full_name == "New User"
    # Password should be hashed
    assert user.password != "MySecretPassword123"
    assert verify_password("MySecretPassword123", user.password) is True

    # Check that workspace was automatically created
    from app.modules.workspaces.repository import WorkspaceRepository
    workspace_repo = WorkspaceRepository(db_session)
    workspaces = await workspace_repo.list_for_user(user.id)
    assert len(workspaces) == 1
    assert workspaces[0].name == "New User's Workspace"

@pytest.mark.asyncio
async def test_register_user_duplicate_email(db_session, make_user):
    await make_user(email="duplicate@example.com")
    service = AccountService(db_session)
    payload = RegisterRequest(
        email="duplicate@example.com",
        full_name="User",
        password="MySecretPassword123"
    )
    # The IntegrityError from repository should be caught and raised as ConflictError
    with pytest.raises(ConflictError) as exc_info:
        await service.register_user(payload)
    
    assert "email already exists" in str(exc_info.value).lower() or "conflict" in str(exc_info.value).lower()

@pytest.mark.asyncio
async def test_login_user_success(db_session, make_user):
    user = await make_user(email="login@example.com", password="MySecretPassword123")
    service = AccountService(db_session)
    payload = LoginRequest(
        email="login@example.com",
        password="MySecretPassword123"
    )
    logged_in_user = await service.login_user(payload)
    assert logged_in_user.id == user.id

@pytest.mark.asyncio
async def test_login_user_incorrect_password(db_session, make_user):
    await make_user(email="wrongpwd@example.com", password="MySecretPassword123")
    service = AccountService(db_session)
    payload = LoginRequest(
        email="wrongpwd@example.com",
        password="WrongPassword"
    )
    with pytest.raises(AuthenticationError) as exc_info:
        await service.login_user(payload)
    assert "Invalid email or password" in str(exc_info.value)

@pytest.mark.asyncio
async def test_login_user_nonexistent_email(db_session):
    service = AccountService(db_session)
    payload = LoginRequest(
        email="notfound@example.com",
        password="MySecretPassword123"
    )
    with pytest.raises(AuthenticationError) as exc_info:
        await service.login_user(payload)
    # Should not enumerate user existence
    assert "Invalid email or password" in str(exc_info.value)

@pytest.mark.asyncio
async def test_login_user_inactive(db_session, make_user):
    await make_user(email="inactive@example.com", password="MySecretPassword123", is_active=False)
    service = AccountService(db_session)
    payload = LoginRequest(
        email="inactive@example.com",
        password="MySecretPassword123"
    )
    with pytest.raises(AuthenticationError) as exc_info:
        await service.login_user(payload)
    assert "disabled" in str(exc_info.value).lower()

@pytest.mark.asyncio
async def test_issue_tokens(db_session, make_user):
    user = await make_user()
    service = AccountService(db_session)
    tokens = await service.issue_tokens(user)
    
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    assert user.current_refresh_jti is not None

@pytest.mark.asyncio
async def test_rotate_refresh_token_success(db_session, make_user):
    user = await make_user()
    service = AccountService(db_session)
    tokens = await service.issue_tokens(user)
    
    original_jti = user.current_refresh_jti
    
    from app.core.security import decode_refresh_token
    payload = decode_refresh_token(tokens["refresh_token"])
    
    # Rotate token
    rotated_user = await service.rotate_refresh_token(payload)
    new_tokens = await service.issue_tokens(rotated_user)
    
    assert rotated_user.current_refresh_jti != original_jti

@pytest.mark.asyncio
async def test_rotate_refresh_token_reuse_revokes_family(db_session, make_user):
    user = await make_user()
    service = AccountService(db_session)
    tokens = await service.issue_tokens(user)
    
    from app.core.security import decode_refresh_token
    payload = decode_refresh_token(tokens["refresh_token"])
    
    # Manually change current_refresh_jti to simulate token was already rotated
    import uuid
    user.current_refresh_jti = uuid.uuid4()
    await db_session.commit()
    
    # Attempting to use the old token again should throw AuthenticationError
    with pytest.raises(AuthenticationError) as exc_info:
        await service.rotate_refresh_token(payload)
        
    assert "reuse" in str(exc_info.value).lower()
    
    # Verify the entire token family was revoked
    assert user.current_refresh_jti is None
