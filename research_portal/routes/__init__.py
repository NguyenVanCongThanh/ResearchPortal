"""ResearchPortal API route modules."""
from fastapi import APIRouter
from .system import create_system_router
from .accounts import create_accounts_router
from .notebooks import create_notebooks_router
from .previews import create_previews_router
from .operations import create_operations_router


def create_api_router(portal) -> APIRouter:
    router = APIRouter(prefix="/api")
    router.include_router(create_system_router(portal))
    router.include_router(create_accounts_router(portal))
    router.include_router(create_notebooks_router(portal))
    router.include_router(create_previews_router(portal))
    router.include_router(create_operations_router(portal))
    return router

