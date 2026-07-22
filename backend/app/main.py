"""
Application entrypoint.

Uvicorn imports `app` from here:
    uvicorn app.main:app
    
Keep this file thin — all configuration lives in core/setup.py.
"""

from app.core.setup import create_app

app = create_app()