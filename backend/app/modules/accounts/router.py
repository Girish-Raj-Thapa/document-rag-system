from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError
from app.core.rate_limit import RateLimiter
from app.core.responses import ApiResponse
from app.core.security import decode_refresh_token, set_auth_cookies, clear_auth_cookies
from app.db.session import get_db
from app.modules.accounts.dependencies import get_current_user
from app.modules.accounts.models import User
from app.modules.accounts.schemas import LoginRequest, RegisterRequest, UserRead
from app.modules.accounts.service import AccountService


router = APIRouter(prefix="/accounts", tags=["Accounts"])

settings = get_settings()


@router.post(
    "/register",
    response_model=ApiResponse[UserRead],
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest, 
    response: Response,
    db: AsyncSession = Depends(get_db),
    _rate_limit = Depends(RateLimiter(max_requests=5, window_seconds=60))
):
    service = AccountService(db)
    user = await service.register_user(payload)
    tokens = await service.issue_tokens(user)
    
    set_auth_cookies(response, tokens["access_token"], tokens["refresh_token"])
    
    return ApiResponse(
        message="Registration successful",
        data=UserRead.model_validate(user),
    )


@router.post(
    "/login",
    response_model=ApiResponse[UserRead],
)
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _rate_limit = Depends(RateLimiter(max_requests=10, window_seconds=60))
):
    service = AccountService(db)
    user = await service.login_user(payload)
    tokens = await service.issue_tokens(user)
    
    set_auth_cookies(response, tokens["access_token"], tokens["refresh_token"])
    
    return ApiResponse(
        message="Login successful",
        data=UserRead.model_validate(user),
    )


@router.post(
    "/refresh",
    response_model=ApiResponse[None],
)
async def refresh_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _rate_limit = Depends(RateLimiter(max_requests=5, window_seconds=60))
):
    """Issue a new access token using the HttpOnly refresh cookie."""
    refresh_token = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if not refresh_token:
        raise AuthenticationError("Missing refresh token cookie.")
        
    try:
        payload = decode_refresh_token(refresh_token)
    except Exception:
        raise AuthenticationError("Invalid or expired refresh token.")
        
    service = AccountService(db)
    user = await service.rotate_refresh_token(payload)
    tokens = await service.issue_tokens(user)
    
    set_auth_cookies(response, tokens["access_token"], tokens["refresh_token"])
    
    return ApiResponse(
        message="Token refreshed successfully",
        data=None
    )


@router.post(
    "/logout",
    response_model=ApiResponse[None],
)
async def logout(response: Response):
    """Clear the auth cookies."""
    clear_auth_cookies(response)
    return ApiResponse(message="Logged out successfully")


@router.get(
    "/me",
    response_model=ApiResponse[UserRead],
)
async def get_me(
    user: User = Depends(get_current_user)
):
    """
    Return the currently authenticated user's profile.
    """
    return ApiResponse(
        message="User profile retrieved",
        data=UserRead.model_validate(user)
    )
