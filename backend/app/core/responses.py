"""
Standard response helpers.

Every successful API response uses the same JSON shape:
{
    "success": true,
    "data": { ... },
    "message": "optional message"
}

This makes the API predictable for frontend developers — they always know where to find the data.
"""

from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")

class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str | None = None
    data: T | None = None

    