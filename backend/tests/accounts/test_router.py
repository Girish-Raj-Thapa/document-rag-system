import pytest
import datetime
from app.core.config import get_settings

settings = get_settings()

@pytest.mark.asyncio
async def test_register_success(client):
    response = await client.post("/api/v1/accounts/register", json={
        "email": "router_user@example.com",
        "full_name": "Router User",
        "password": "StrongPassword123"
    })
    
    assert response.status_code == 201
    data = response.json()
    assert data["message"] == "Registration successful"
    assert data["data"]["email"] == "router_user@example.com"
    assert "id" in data["data"]
    
    # Check cookies
    cookies = response.cookies
    assert settings.ACCESS_COOKIE_NAME in cookies
    assert settings.REFRESH_COOKIE_NAME in cookies
    
    # Wait, httpx cookies doesn't directly expose httponly flags cleanly in the dict,
    # but we can get it from the headers.
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert any("HttpOnly" in h for h in set_cookie_headers)
    assert any("samesite=lax" in h.lower() for h in set_cookie_headers)

@pytest.mark.asyncio
async def test_register_validation_error(client):
    response = await client.post("/api/v1/accounts/register", json={
        "email": "not-an-email",
        "password": "pwd"
        # missing full_name
    })
    
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_register_duplicate_email(client, make_user):
    await make_user(email="dup_router@example.com")
    
    response = await client.post("/api/v1/accounts/register", json={
        "email": "dup_router@example.com",
        "full_name": "User",
        "password": "MySecretPassword123"
    })
    
    assert response.status_code == 409
    assert "already exists" in response.json()["message"].lower()

@pytest.mark.asyncio
async def test_login_success(client, make_user):
    await make_user(email="login_router@example.com", password="MySecretPassword123")
    
    response = await client.post("/api/v1/accounts/login", json={
        "email": "login_router@example.com",
        "password": "MySecretPassword123"
    })
    
    assert response.status_code == 200
    assert response.json()["message"] == "Login successful"
    assert settings.ACCESS_COOKIE_NAME in response.cookies
    
@pytest.mark.asyncio
async def test_login_wrong_credentials(client, make_user):
    await make_user(email="login_router2@example.com", password="MySecretPassword123")
    
    response = await client.post("/api/v1/accounts/login", json={
        "email": "login_router2@example.com",
        "password": "WrongPassword"
    })
    
    assert response.status_code == 401
    assert "invalid email or password" in response.json()["message"].lower()
    
@pytest.mark.asyncio
async def test_get_me_success(auth_client):
    response = await auth_client.get("/api/v1/accounts/me")
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["id"] == str(auth_client.current_user_id)

@pytest.mark.asyncio
async def test_get_me_no_token(client):
    response = await client.get("/api/v1/accounts/me")
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_get_me_expired_token(auth_client, frozen_time):
    # Move time forward past access token expiry (default is 30 mins)
    frozen_time.tick(delta=datetime.timedelta(minutes=45))
    
    response = await auth_client.get("/api/v1/accounts/me")
    assert response.status_code == 401
    assert "expired" in response.json()["message"].lower()

@pytest.mark.asyncio
async def test_refresh_success(auth_client):
    # Access and refresh cookies are already set in auth_client
    response = await auth_client.post("/api/v1/accounts/refresh")
    
    assert response.status_code == 200
    assert "Token refreshed successfully" in response.json()["message"]
    
    # Should get new cookies
    assert settings.ACCESS_COOKIE_NAME in response.cookies
    assert settings.REFRESH_COOKIE_NAME in response.cookies

@pytest.mark.asyncio
async def test_refresh_missing_cookie(client):
    response = await client.post("/api/v1/accounts/refresh")
    assert response.status_code == 401
    assert "missing refresh token cookie" in response.json()["message"].lower()

@pytest.mark.asyncio
async def test_refresh_expired_cookie(auth_client, frozen_time):
    # Move time forward past refresh token expiry (default is 7 days)
    frozen_time.tick(delta=datetime.timedelta(days=10))
    
    response = await auth_client.post("/api/v1/accounts/refresh")
    assert response.status_code == 401
    assert "expired" in response.json()["message"].lower()

@pytest.mark.asyncio
async def test_refresh_reused_token_full(client, make_user, db_session):
    user = await make_user()
    
    from app.modules.accounts.service import AccountService
    service = AccountService(db_session)
    tokens = await service.issue_tokens(user)
    
    old_refresh_token = tokens["refresh_token"]
    
    # Refresh #1 (Succeeds)
    resp1 = await client.post("/api/v1/accounts/refresh", cookies={settings.REFRESH_COOKIE_NAME: old_refresh_token})
    assert resp1.status_code == 200
    
    # Refresh #2 (Reuse - Fails) - intentionally send the old token again
    resp2 = await client.post("/api/v1/accounts/refresh", cookies={settings.REFRESH_COOKIE_NAME: old_refresh_token})
    assert resp2.status_code == 401
    assert "reuse detected" in resp2.json()["message"].lower()
    
@pytest.mark.asyncio
async def test_logout(auth_client):
    response = await auth_client.post("/api/v1/accounts/logout")
    assert response.status_code == 200
    
    # Check that Set-Cookie headers were sent to delete the cookies
    set_cookies = [c.lower() for c in response.headers.get_list("set-cookie")]
    assert any(settings.ACCESS_COOKIE_NAME.lower() in c and 'max-age=0' in c for c in set_cookies)
    assert any(settings.REFRESH_COOKIE_NAME.lower() in c and 'max-age=0' in c for c in set_cookies)
