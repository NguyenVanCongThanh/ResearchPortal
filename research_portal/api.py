"""FastAPI REST API router and application for ResearchPortal."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .builder import download_bundle, validated_bundle
from .domain import BuildOptions, Conflict, PortalError
from .providers import capabilities
from .service import Service, monitor_health
from .settings import Settings, load_settings
from .storage import Store, uid
from .worker import process_one


# --- Pydantic Schemas ---
class AccountPayload(BaseModel):
    provider: str = Field(..., description="'kaggle' or 'wandb'")
    name: str = Field(..., description="Display name")
    slug: str = Field(..., description="Unique slug")
    principal: str = Field(..., description="Kaggle username or W&B entity")
    description: str = ""
    enabled: bool = True
    is_default: bool = False
    secret: str = ""
    account_id: Optional[str] = None
    revision: Optional[int] = None


class AttachNotebookPayload(BaseModel):
    account_id: str
    kernel: str
    wandb_account_id: Optional[str] = None
    run_ref: Optional[str] = None
    new_attempt: bool = False


class BuildPayload(BaseModel):
    account_id: str
    options: Dict[str, Any]


class SubmitPayload(BaseModel):
    preview_id: str
    options: Dict[str, Any]
    idem: Optional[str] = None


class ResolvePayload(BaseModel):
    accepted: bool
    evidence: str
    remote_version: str = ""


class PortalApi:
    def __init__(self, settings: Optional[Settings] = None, store: Optional[Store] = None):
        self.settings = settings or load_settings()
        self.store = store or Store(self.settings.runtime, self.settings.mode)
        self.service = Service(self.settings, self.store)
        self.stop_worker = threading.Event()
        self.worker_thread: Optional[threading.Thread] = None

    def start_background_worker(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return

        def _worker_loop():
            while not self.stop_worker.is_set():
                try:
                    handled = process_one(self.settings, self.store, self.service)
                    if not handled:
                        self.stop_worker.wait(1.0)
                except Exception:
                    self.stop_worker.wait(2.0)

        self.stop_worker.clear()
        self.worker_thread = threading.Thread(target=_worker_loop, daemon=True, name="in-process-worker")
        self.worker_thread.start()

    def stop_background_worker(self):
        self.stop_worker.set()
        if self.worker_thread:
            self.worker_thread.join(timeout=2.0)


def create_router(portal: PortalApi) -> APIRouter:
    router = APIRouter(prefix="/api")
    store = portal.store
    service = portal.service
    settings = portal.settings

    # --- System & Capabilities ---
    @router.get("/system/status")
    def get_system_status():
        worker_online = store.worker_online() or (portal.worker_thread is not None and portal.worker_thread.is_alive())
        return {
            "mode": settings.mode,
            "allow_live_submit": settings.allow_live_submit,
            "revision": settings.revision,
            "worker_online": worker_online,
            "capabilities": capabilities(),
        }

    # --- Accounts ---
    @router.get("/accounts")
    def list_accounts(provider: Optional[str] = None):
        accounts = store.accounts(provider)
        # Redact any accidental secrets, return metadata only
        return [{k: a[k] for k in ("id", "provider", "name", "slug", "principal", "description",
                                   "enabled", "is_default", "configured", "revision", "tested_at",
                                   "test_result", "rotated_at")} for a in accounts]

    @router.post("/accounts")
    def save_account(payload: AccountPayload):
        try:
            saved = store.save_account(
                provider=payload.provider,
                name=payload.name,
                slug=payload.slug,
                principal=payload.principal,
                description=payload.description,
                enabled=payload.enabled,
                is_default=payload.is_default,
                secret=payload.secret,
                account_id=payload.account_id,
                revision=payload.revision,
            )
            return {"success": True, "account": saved}
        except (Conflict, PortalError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/accounts/{account_id}/test")
    def test_account(account_id: str):
        try:
            op = service.test_connection(account_id)
            return {"success": True, "operation_id": op}
        except (Conflict, PortalError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.delete("/accounts/{account_id}")
    def archive_account(account_id: str, revision: int = Query(...)):
        try:
            store.archive_account(account_id, revision)
            return {"success": True}
        except (Conflict, PortalError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    # --- Notebooks & Monitor ---
    @router.get("/notebooks")
    def list_notebooks():
        notebooks = store.notebooks()
        results = []
        for nb in notebooks:
            k_obs = store.observations(nb["id"], "kaggle")
            w_obs = store.observations(nb["id"], "wandb")
            health = monitor_health(k_obs, w_obs, stall_seconds=settings.stall_seconds, stale_seconds=settings.stale_seconds)
            account = store.account(nb["account_id"])
            wandb_acc = store.account(nb["wandb_account_id"]) if nb["wandb_account_id"] else None

            latest_k = k_obs[0] if k_obs else None
            logs_info = latest_k["data"].get("logs", {}) if latest_k and not latest_k.get("error") else {}
            remote_ver = latest_k.get("remote_version") if latest_k else None

            results.append({
                "id": nb["id"],
                "kernel": nb["kernel"],
                "account_id": nb["account_id"],
                "account_name": account["name"] if account else "Unknown",
                "wandb_account_id": nb["wandb_account_id"],
                "wandb_account_name": wandb_acc["name"] if wandb_acc else None,
                "run_ref": nb["run_ref"],
                "attempt_id": nb["attempt_id"],
                "health": health,
                "remote_version": remote_ver,
                "latest_kaggle": latest_k,
                "latest_wandb": w_obs[0] if w_obs else None,
                "logs_summary": {
                    "availability": logs_info.get("availability", "not_yet_published"),
                    "source": logs_info.get("source", "none"),
                    "truncated": logs_info.get("truncated", False),
                    "progress": logs_info.get("progress", {}),
                    "has_text": bool(logs_info.get("text")),
                },
            })
        return results

    @router.post("/notebooks")
    def attach_notebook(payload: AttachNotebookPayload):
        try:
            nb_id = store.attach(
                account_id=payload.account_id,
                kernel=payload.kernel,
                wandb_account_id=payload.wandb_account_id or None,
                run_ref=payload.run_ref or "",
                attempt_id=uid() if payload.new_attempt else None,
            )
            return {"success": True, "notebook_id": nb_id}
        except (Conflict, PortalError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/notebooks/{notebook_id}/check")
    def check_notebook(notebook_id: str):
        try:
            op_ids = service.check(notebook_id)
            return {"success": True, "operation_ids": op_ids}
        except (Conflict, PortalError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.get("/notebooks/{notebook_id}/logs")
    def get_notebook_logs(notebook_id: str):
        k_obs = store.observations(notebook_id, "kaggle")
        good = next((o for o in k_obs if not o.get("error")), None)
        if not good:
            return {"availability": "not_yet_published", "text": "", "progress": {}, "source": "none"}
        logs = good["data"].get("logs", {})
        return {
            "availability": logs.get("availability", "available" if logs.get("text") else "not_yet_published"),
            "text": logs.get("text", ""),
            "truncated": logs.get("truncated", False),
            "source": logs.get("source", "cli_kernels_logs"),
            "progress": logs.get("progress", {}),
            "fetched_at": good.get("fetched_at"),
        }

    # --- Build, Preview & Submit ---
    @router.get("/previews")
    def list_previews(account_id: Optional[str] = None):
        previews = store.previews()
        if account_id:
            previews = [p for p in previews if p["account_id"] == account_id]
        return previews

    @router.post("/previews")
    def request_build_preview(payload: BuildPayload):
        try:
            op = service.request_build(payload.account_id, payload.options)
            return {"success": True, "operation_id": op}
        except (Conflict, PortalError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.get("/previews/{preview_id}")
    def get_preview(preview_id: str):
        try:
            p = store.preview(preview_id)
            return p
        except Exception:
            raise HTTPException(status_code=404, detail="Preview not found")

    @router.get("/previews/{preview_id}/download")
    def download_preview_bundle(preview_id: str):
        try:
            preview = store.preview(preview_id)
            bundle_zip = download_bundle(store, preview)
            from io import BytesIO
            return StreamingResponse(BytesIO(bundle_zip), media_type="application/zip",
                                     headers={"Content-Disposition": f"attachment; filename=preview-{preview_id}.zip"})
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/submissions")
    def submit_preview(payload: SubmitPayload):
        try:
            idem = payload.idem or f"submit:{payload.preview_id}"
            op = service.request_submit(payload.preview_id, payload.options, idem)
            return {"success": True, "operation_id": op}
        except (Conflict, PortalError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    # --- Operations ---
    @router.get("/operations")
    def list_operations():
        ops = store.operations()
        for op in ops:
            if op.get("result"):
                try:
                    op["result_parsed"] = json.loads(op["result"])
                except Exception:
                    op["result_parsed"] = None
        return ops

    @router.post("/operations/{operation_id}/resolve")
    def resolve_operation(operation_id: str, payload: ResolvePayload):
        try:
            service.resolve_unknown(operation_id, payload.accepted, payload.evidence, payload.remote_version)
            return {"success": True}
        except (Conflict, PortalError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    return router


def create_app(settings: Optional[Settings] = None, store: Optional[Store] = None) -> FastAPI:
    portal = PortalApi(settings, store)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Seed fixture demo data if needed
        if portal.store.mode == "fixture" and not portal.store.rows("SELECT id FROM accounts WHERE mode='fixture' LIMIT 1"):
            acc = portal.store.save_account(provider="kaggle", name="Demo Kaggle", slug="demo-kaggle", principal="demo-owner", is_default=True)
            tra = portal.store.save_account(provider="wandb", name="Demo W&B", slug="demo-wandb", principal="demo-team")
            portal.store.attach(acc["id"], "demo-owner/running", tra["id"], "demo-team/demo-project/default")
        # Start in-process background worker so no second terminal is required!
        portal.start_background_worker()
        yield
        portal.stop_background_worker()

    app = FastAPI(title="ResearchPortal API", version="2.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api_router = create_router(portal)
    app.include_router(api_router)

    # Static UI directory
    static_dir = Path(__file__).resolve().parents[1] / "static"
    if static_dir.exists():
        from fastapi.staticfiles import StaticFiles
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        @app.get("/")
        def serve_index():
            return FileResponse(static_dir / "index.html")

    return app
