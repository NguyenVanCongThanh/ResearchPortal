"""System status and capabilities routes."""
from fastapi import APIRouter
from ..providers import capabilities


def create_system_router(portal) -> APIRouter:
    router = APIRouter()
    settings = portal.settings
    store = portal.store

    @router.get("/system/status")
    def get_system_status():
        return {
            "mode": settings.mode,
            "allow_live_submit": settings.allow_live_submit,
            "revision": settings.revision,
            "worker_online": store.worker_online(),
            "capabilities": capabilities(),
        }

    return router

