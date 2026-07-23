from fastapi import APIRouter

from app.modules.accounts.router import router as accounts_router
from app.modules.workspaces.router import router as workspaces_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(accounts_router)
api_v1_router.include_router(workspaces_router)