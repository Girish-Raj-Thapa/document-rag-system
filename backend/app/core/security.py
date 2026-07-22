"""
Security utilities: password hashing and JWT tokens.

Design decisions:
- Passwords hashed with bcrypt (industry standard, intentionally slow)
- Dual-token JWT: separate secrets for access and refresh tokens
- Access tokens: short-lived (30 min), in JSON response body
- Refresh tokens: long-lived (7 days), in HttpOnly cookies

Why separate secrets?
If an attacker finds your access token secret (e.g., in a log leak),
they can forge access tokens — but they CANNOT forge refresh tokens
because those use a different secret. Damage is limited to 30 minutes
instead of 7 days.
"""

from datetime import datetime, timedelta, timezone
import uuid

from fastapi import Response
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.schemas import TokenPayload

settings = get_settings()


# ── Password Hashing ──
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """
    Hash a plaintext password. One-way — cannot be reversed.
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Check a plaintext password against a stored hash. Returns True if match.
    """
    return pwd_context.verify(plain_password, hashed_password)


# ── JWT Token Creation ──

def create_access_token(subject: str, jti: uuid.UUID, expires_delta: timedelta | None = None) -> str:
    """
    Create a short-lived access token.
    
    Args:
        subject: The user ID (as string). This goes into the 'sub' claim.
        jti: The unique token ID.
        expires_delta: How long until the token expires.
    """
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))

    payload = {
        "sub": subject,
        "type": "access",
        "exp": expire,
        "iat": now,
        "jti": str(jti),
    }

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)



def create_refresh_token(subject: str, jti: uuid.UUID, expires_delta: timedelta | None = None) -> str:
    """
    Create a long-lived refresh token.
    
    IMPORTANT: Uses a DIFFERENT secret key than access tokens.
    This token is sent as an HttpOnly cookie — JavaScript cannot read it.
    """
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))

    payload = {
        "sub": subject,
        "type": "refresh",
        "exp": expire,
        "iat": now,
        "jti": str(jti),
    }

    # Note: JWT_REFRESH_SECRET_KEY, not SECRET_KEY
    return jwt.encode(payload, settings.JWT_REFRESH_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


# ── JWT Token Decoding ──

def decode_access_token(token: str) -> TokenPayload:
    """
    Decode and validate an access token.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return TokenPayload(**payload)
    except (JWTError, ValidationError):
        raise  # Let the caller handle it


def decode_refresh_token(token: str) -> TokenPayload:
    """
    Decode and validate a refresh token.
    Uses the refresh-specific secret key.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_REFRESH_SECRET_KEY,  # Different key!
            algorithms=[settings.JWT_ALGORITHM],
        )
        return TokenPayload(**payload)
    except (JWTError, ValidationError):
        raise


# ── Cookie Helpers ──

def set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    """Helper to attach both HttpOnly auth cookies to a response."""
    response.set_cookie(
        key=settings.ACCESS_COOKIE_NAME,
        value=access_token,
        httponly=True,
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )


def clear_auth_cookies(response: Response):
    """Clear the access and refresh token cookies."""
    response.delete_cookie(settings.ACCESS_COOKIE_NAME)
    response.delete_cookie(settings.REFRESH_COOKIE_NAME)

