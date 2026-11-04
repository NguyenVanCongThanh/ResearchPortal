"""FastAPI REST API application factory and router entrypoint for ResearchPortal."""
from contextlib import asynccontextmanager
import fcntl
import os
from pathlib import Path
import sqlite3
import threading
from typing import Optional

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse

from .domain import Conflict
from .routes import create_api_router
from .routes.schemas import (
    AccountPayload,
    AttachNotebookPayload,
    BuildPayload,
    SubmitPayload,
    ResolvePayload,
    raise_http_error,
)
from .service import Service
from .settings import Settings, load_settings
from .storage import Store, uid
from .worker import process_one


# Backwards compatibility helper
def _raise_http(exc: Exception) -> None:
    raise_http_error(exc)


class PortalApi:
    """Manages service lifecycle, store connections, and in-process background worker."""

    def __init__(self, settings: Optional[Settings] = None, store: Optional[Store] = None):
        self.settings = settings or load_settings()
        self.store = store or Store(self.settings.runtime, self.settings.mode)
        self.service = Service(self.settings, self.store)
        self.stop_worker = threading.Event()
        self.worker_thread: Optional[threading.Thread] = None

    def start_background_worker(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return

        ready = threading.Event()

        def _worker_loop():
            worker_id = f"inproc-{uid()}"
            lock_path = self.store.root / "worker.lock"
            with open(lock_path, "a") as lock_file:
                acquired = False
                while not self.stop_worker.is_set():
                    if not acquired:
                        try:
                            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            acquired = True
                            self.store.recover()
                            self.store.heartbeat()
                            ready.set()
                        except BlockingIOError:
                            ready.set()
                            self.stop_worker.wait(2.0)
                            continue
                        except (sqlite3.Error, OSError):
                            ready.set()
                            self.stop_worker.wait(2.0)
                            continue
                    try:
                        self.store.heartbeat()
                        handled = process_one(self.settings, self.store, worker_id, self.service.providers)
                        if not handled:
                            self.stop_worker.wait(0.5)
                    except Exception:
                        self.stop_worker.wait(1.0)
                if acquired:
                    try:
                        with self.store.tx() as db:
                            db.execute("DELETE FROM worker WHERE mode=? AND pid=?", (self.settings.mode, os.getpid()))
                    except (sqlite3.Error, OSError):
                        pass
                    try:
                        fcntl.flock(lock_file, fcntl.LOCK_UN)
                    except OSError:
                        pass

        self.stop_worker.clear()
        self.worker_thread = threading.Thread(target=_worker_loop, daemon=True, name="in-process-worker")
        self.worker_thread.start()
        ready.wait(timeout=2.0)

    def stop_background_worker(self):
        self.stop_worker.set()
        if self.worker_thread:
            self.worker_thread.join(timeout=3.0)


def create_router(portal: PortalApi) -> APIRouter:
    """Creates and aggregates all modular REST API routers."""
    return create_api_router(portal)


def create_app(settings: Optional[Settings] = None, store: Optional[Store] = None) -> FastAPI:
    """Builds and configures the FastAPI application instance."""
    portal = PortalApi(settings, store)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if portal.store.mode == "fixture" and not portal.store.rows("SELECT id FROM accounts WHERE mode='fixture' LIMIT 1"):
            acc = portal.store.save_account(provider="kaggle", name="Demo Kaggle", slug="demo-kaggle", principal="demo-owner", is_default=True)
            tra = portal.store.save_account(provider="wandb", name="Demo W&B", slug="demo-wandb", principal="demo-team")
            portal.store.attach(acc["id"], "demo-owner/running", tra["id"], "demo-team/demo-project/default")
        portal.start_background_worker()
        yield
        portal.stop_background_worker()

    app = FastAPI(title="ResearchPortal API", version="2.0.0", lifespan=lifespan)

    api_router = create_router(portal)
    app.include_router(api_router)

    static_dir = (Path(__file__).resolve().parents[1] / "static").resolve()
    if static_dir.is_dir():
        from fastapi.staticfiles import StaticFiles
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        @app.get("/")
        def serve_index():
            return FileResponse(static_dir / "index.html")

        @app.get("/{full_path:path}")
        def serve_spa_or_static(full_path: str):
            raw = Path(full_path)
            if raw.is_absolute() or ".." in raw.parts or full_path.startswith(("api/", "static/", "docs", "redoc", "openapi.json")):
                raise HTTPException(status_code=404, detail="Not Found")
            candidate_unres = static_dir / raw
            if candidate_unres.is_symlink():
                raise HTTPException(status_code=404, detail="Not Found")
            candidate = candidate_unres.resolve()
            if not candidate.is_relative_to(static_dir):
                raise HTTPException(status_code=404, detail="Not Found")
            if candidate.is_file():
                return FileResponse(candidate)
            if "." in raw.name:
                raise HTTPException(status_code=404, detail="Not Found")
            return FileResponse(static_dir / "index.html")

    return app
