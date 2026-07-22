"""
Redis-backed rate limiter.

Uses the "fixed window counter" pattern:
1. For each (key, window), increment a Redis counter
2. If the counter exceeds max_requests, reject with 429
3. The counter auto-expires after window_seconds

This is not perfectly accurate (requests near window boundaries
can slightly exceed the limit) but it's simple, fast, and good
enough for our use case.

Usage as a FastAPI dependency:
    @router.post("/login")
    async def login(
        _rate_limit=Depends(RateLimiter(max_requests=10, window_seconds=60)),
    ):
        ...
"""

from fastapi import Depends, HTTPException, Request


class RateLimiter:
    """
    Callable dependency that enforces rate limits via Redis.
    
    Args:
        max_requests: Maximum requests allowed in the window
        window_seconds: Window duration in seconds
    """

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def __call__(self, request: Request) -> None:
        """
        Called by FastAPI's dependency injection on every request.
        
        Uses the client's IP address as the rate limit key.
        If the limit is exceeded, raises HTTP 429.
        """
        redis = request.app.state.redis

        # Build a key like "rate_limit:login:192.168.1.1"
        client_ip = request.client.host if request.client else "unknown"
        endpoint = request.url.path
        key = f"rate_limit:{endpoint}:{client_ip}"

        # Increment the counter. If this is the first request in the window,
        # Redis creates the key with value 1.
        current_count = await redis.incr(key)

        # On first request, set the expiration.
        # After window_seconds, Redis automatically deletes the key,
        # resetting the counter.
        if current_count == 1:
            await redis.expire(key, self.window_seconds)

        if current_count > self.max_requests:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Try again in {self.window_seconds} seconds.",
            )
            