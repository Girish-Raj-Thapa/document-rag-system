"""
Application exception hierarchy and global error handlers.

Design: every known error condition has its own exception class.
Routes never construct HTTPException directly — they raise these domain exceptions,
and the global handlers format them into consistent JSON responses.

This gives you:
1. Consistent error response format across ALL endpoints
2. Centralized logging of errors
3. Clean route code (raise NotFoundError("User") instead of HTTPException(...))
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.responses import ApiResponse

logger = logging.getLogger(__name__)



# ═══════════════════════════════════════════
# Exception Classes
# ═══════════════════════════════════════════

class AppError(Exception):
    """
    Base exception for all application errors.
    
    Every custom exception inherits from this.
    The global handler catches AppError and formats it as JSON.
    """

    def __init__(
        self,
        message: str = "An error occurred",
        details: Any = None,
    ):
        self.message = message
        self.details = details
        super().__init__(self.message)


class ValidationError(AppError):
    """
    Invalid input data.
    """

    def __init__(self, message: str = "Validation error", details: Any = None):
        super().__init__(message=message, details=details)


class AuthenticationError(AppError):
    """
    Missing or invalid credentials.
    """

    def __init__(self, message: str = "Authentication required"):
        super().__init__(message=message)


class PermissionDeniedError(AppError):
    """
    Authenticated but not authorized for this action.
    """

    def __init__(self, message: str = "Permission denied"):
        super().__init__(message=message)


class NotFoundError(AppError):
    """
    Resource not found.
    """

    def __init__(self, resource: str = "Resource"):
        super().__init__(message=f"{resource} not found")


class ConflictError(AppError):
    """
    Resource already exists or state conflict.
    """

    def __init__(self, message: str = "Resource already exists"):
        super().__init__(message=message)



# ═══════════════════════════════════════════
# Global Exception Handlers
# ═══════════════════════════════════════════

def _error_response(status_code: int, message: str, details: Any = None) -> JSONResponse:
    """Build a consistent error JSON response using ApiResponse wrapper."""
    body = ApiResponse(success=False, message=message, data=details).model_dump(exclude_none=True)
    return JSONResponse(status_code=status_code, content=body)


def register_exception_handlers(app: FastAPI) -> None:
    """
    Register global exception handlers on the FastAPI app.
    
    Order matters — more specific handlers are checked first.
    """

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        """Handle our custom application errors."""
        status_code = 500
        if isinstance(exc, ValidationError):
            status_code = 422
        elif isinstance(exc, AuthenticationError):
            status_code = 401
        elif isinstance(exc, PermissionDeniedError):
            status_code = 403
        elif isinstance(exc, NotFoundError):
            status_code = 404
        elif isinstance(exc, ConflictError):
            status_code = 409

        logger.warning(f"AppError: {status_code} — {exc.message}")
        return _error_response(status_code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        """
        Handle Pydantic validation errors.
        
        FastAPI raises this when request body/params don't match the schema.
        We reformat the errors into our standard shape.
        """
        details = []
        for error in exc.errors():
            details.append({
                "field": " → ".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
            })
        return _error_response(422, "Request validation failed", details)

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException):
        """Handle standard HTTP exceptions (404 from missing routes, etc.)."""
        return _error_response(exc.status_code, str(exc.detail))

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        """
        Catch-all for unhandled exceptions.
        
        NEVER expose the actual error message to the client in production —
        it might contain SQL queries, file paths, or other sensitive info.
        Log it server-side for debugging.
        """
        logger.exception(f"Unhandled exception: {exc}")
        return _error_response(500, "Internal server error")
        