from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.modules.accounts.models import User
from app.modules.accounts.repository import UserRepository


settings = get_settings()


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Dependency that enforces authentication.
    Usage: @router.get("/me") async def get_me(user = Depends(get_current_user))
    """
    token = request.cookies.get(settings.ACCESS_COOKIE_NAME)
    
    if not token:
        raise AuthenticationError("Not authenticated.")

    # Decode token (raises error if expired or invalid)
    try:
        payload = decode_access_token(token)
    except Exception as e:
        raise AuthenticationError("Invalid or expired access token.")

    if payload.type != "access":
        raise AuthenticationError("Wrong token type for this endpoint.")

    # Fetch fresh user from DB (prevents using a token for a deleted/banned user)
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(payload.sub)

    if not user:
        raise AuthenticationError("User no longer exists.")
    if not user.is_active:
        raise AuthenticationError("User account is disabled.")

    return user

