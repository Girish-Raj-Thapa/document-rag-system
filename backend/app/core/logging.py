"""
Logging configuration.

Sets up Python logging with a clean format and filters out
noisy health-check requests from the access log.

Without the health check filter, your logs would be 90% this:
    INFO: 172.18.0.1:54321 - "GET /health HTTP/1.1" 200
repeated every 10 seconds by Docker's healthcheck.
"""

import logging

class HealthCheckFilter(logging.Filter):
    """
    Filter out GET /health requests from access logs.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        # Suppress health check log lines
        if '"GET /health' in message:
            return False
        return True


def setup_logging() -> None:
    """
    Configure application logging.
    
    - Root logger at INFO level
    - Clean format with timestamp + level + module
    - Health check noise filtered from uvicorn access logs
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Suppress health check spam from uvicorn
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.addFilter(HealthCheckFilter())

    # Quiet down noisy libraries
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("celery").setLevel(logging.INFO)

