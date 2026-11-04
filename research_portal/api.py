"""FastAPI REST API router and application for ResearchPortal."""
from contextlib import asynccontextmanager
import fcntl
from io import BytesIO
import json
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any, Dict, Optional

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from .builder import download_bundle, validated_bundle
from .domain import Conflict, PortalError
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
    description: Optional[str] = None
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
    attempt_id: Optional[str] = None


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


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, Conflict):
        raise HTTPException(status_code=409, detail=str(exc)) from None
    if "not found" in str(exc).lower():
        raise HTTPException(status_code=404, detail=str(exc)) from None
    raise HTTPException(status_code=400, detail=str(exc)) from None


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
    router = APIRouter(prefix="/api")
    store = portal.store
    service = portal.service
    settings = portal.settings

    # --- System & Capabilities ---
    @router.get("/system/status")
    def get_system_status():
        return {
            "mode": settings.mode,
            "allow_live_submit": settings.allow_live_submit,
            "revision": settings.revision,
            "worker_online": store.worker_online(),
            "capabilities": capabilities(),
        }

    # --- Accounts ---
    @router.get("/accounts")
    def list_accounts(provider: Optional[str] = None):
        accounts = store.accounts(provider)
        return [{k: a[k] for k in ("id", "provider", "name", "slug", "principal", "description",
                                   "enabled", "is_default", "configured", "revision", "tested_at",
                                   "test_result", "rotated_at")} for a in accounts]

    @router.post("/accounts")
    def save_account(payload: AccountPayload):
        try:
            description = payload.description
            if description is None:
                description = store.account(payload.account_id)["description"] if payload.account_id else ""
            saved = store.save_account(
                provider=payload.provider,
                name=payload.name,
                slug=payload.slug,
                principal=payload.principal,
                description=description,
                enabled=payload.enabled,
                is_default=payload.is_default,
                secret=payload.secret,
                account_id=payload.account_id,
                revision=payload.revision,
            )
            return {"success": True, "account": saved}
        except (Conflict, PortalError) as exc:
            _raise_http(exc)

    @router.post("/accounts/{account_id}/test")
    def test_account(account_id: str):
        try:
            op = service.test_connection(account_id)
            return {"success": True, "operation_id": op}
        except (Conflict, PortalError) as exc:
            _raise_http(exc)

    @router.delete("/accounts/{account_id}")
    def archive_account(account_id: str, revision: int = Query(...)):
        try:
            store.archive_account(account_id, revision)
            return {"success": True}
        except (Conflict, PortalError) as exc:
            _raise_http(exc)

    # --- Notebooks & Monitor ---
    @router.get("/notebooks")
    def list_notebooks():
        notebooks = store.notebooks()
        accounts_map = {a["id"]: store.public_account(a)
                        for a in store.rows("SELECT * FROM accounts WHERE mode=?", (store.mode,))}
        results = []
        for nb in notebooks:
            k_obs = store.observations(nb["id"], "kaggle")
            w_obs = store.observations(nb["id"], "wandb")
            health = monitor_health(k_obs, w_obs, stall_seconds=settings.stall_seconds, stale_seconds=settings.stale_seconds)
            account = accounts_map.get(nb["account_id"])
            wandb_acc = accounts_map.get(nb["wandb_account_id"]) if nb["wandb_account_id"] else None

            latest_k = k_obs[0] if k_obs else None
            good_k = next((o for o in k_obs if not o.get("error")), None)
            logs_info = good_k["data"].get("logs", {}) if good_k else {}
            log_text = logs_info.get("text", "")
            remote_ver = (good_k or latest_k or {}).get("remote_version")
            submitted_ver = None
            if nb["attempt_id"]:
                attempts = store.rows("SELECT result FROM operations WHERE id=? AND mode=?", (nb["attempt_id"], store.mode))
                if attempts and attempts[0]["result"]:
                    try:
                        op_res = json.loads(attempts[0]["result"])
                        submitted_ver = op_res.get("provider", {}).get("remote_version") or op_res.get("remote_version")
                    except (ValueError, TypeError):
                        submitted_ver = None

            # Strip bulk log text from list payload; full text is served by GET /api/notebooks/{id}/logs
            latest_k_summary = None
            if latest_k:
                latest_k_summary = dict(latest_k)
                if isinstance(latest_k_summary.get("data"), dict):
                    k_data = dict(latest_k_summary["data"])
                    if isinstance(k_data.get("logs"), dict):
                        k_logs = dict(k_data["logs"])
                        k_logs.pop("text", None)
                        k_data["logs"] = k_logs
                    latest_k_summary["data"] = k_data

            latest_w = w_obs[0] if w_obs else None
            good_w = next((o for o in w_obs if not o.get("error")), None)
            w_data_good = good_w.get("data", {}) if good_w and isinstance(good_w.get("data"), dict) else {}
            latest_w_summary = None
            if latest_w:
                latest_w_summary = dict(latest_w)
                if isinstance(latest_w_summary.get("data"), dict):
                    w_data_copy = dict(latest_w_summary["data"])
                    w_data_copy.pop("live_log_text", None)
                    latest_w_summary["data"] = w_data_copy

            results.append({
                "id": nb["id"],
                "kernel": nb["kernel"],
                "account_id": nb["account_id"],
                "account_name": account["name"] if account else "Unknown",
                "wandb_account_id": nb["wandb_account_id"],
                "wandb_account_name": wandb_acc["name"] if wandb_acc else None,
                "run_ref": nb["run_ref"],
                "attempt_id": nb["attempt_id"],
                "submitted_version": submitted_ver,
                "health": health,
                "remote_version": remote_ver,
                "latest_kaggle": latest_k_summary,
                "latest_wandb": latest_w_summary,
                "logs_summary": {
                    "availability": logs_info.get("availability", "not_yet_published"),
                    "source": logs_info.get("source", "none"),
                    "truncated": logs_info.get("truncated", False),
                    "progress": logs_info.get("progress", {}),
                    "has_text": bool(log_text),
                    "line_count": len(log_text.splitlines()) if log_text else 0,
                    "wandb_live_lines": w_data_good.get("live_log_lines", 0),
                },
            })
        return results

    @router.post("/notebooks")
    def attach_notebook(payload: AttachNotebookPayload):
        try:
            attempt_id = payload.attempt_id if payload.attempt_id is not None else (uid() if payload.new_attempt else None)
            nb_id = store.attach(
                account_id=payload.account_id,
                kernel=payload.kernel,
                wandb_account_id=payload.wandb_account_id or None,
                run_ref=payload.run_ref or "",
                attempt_id=attempt_id,
            )
            return {"success": True, "notebook_id": nb_id}
        except (Conflict, PortalError) as exc:
            _raise_http(exc)

    @router.post("/notebooks/{notebook_id}/check")
    def check_notebook(notebook_id: str):
        try:
            op_ids = service.check(notebook_id)
            return {"success": True, "operation_ids": op_ids}
        except (Conflict, PortalError) as exc:
            _raise_http(exc)

    @router.get("/notebooks/{notebook_id}/logs")
    def get_notebook_logs(notebook_id: str):
        try:
            store.notebook(notebook_id)
        except PortalError as exc:
            _raise_http(exc)
        k_obs = store.observations(notebook_id, "kaggle")
        w_obs = store.observations(notebook_id, "wandb")
        good = next((o for o in k_obs if not o.get("error")), None)
        good_w = next((o for o in w_obs if not o.get("error")), None)
        w_data = good_w.get("data", {}) if good_w and isinstance(good_w.get("data"), dict) else {}
        wandb_live_text = w_data.get("live_log_text", "")
        wandb_fetched_at = good_w.get("fetched_at") if good_w else None
        if not good:
            return {
                "availability": "not_yet_published",
                "text": "",
                "progress": {},
                "source": "none",
                "wandb_live_text": wandb_live_text,
                "wandb_fetched_at": wandb_fetched_at,
            }
        logs = good["data"].get("logs", {})
        return {
            "availability": logs.get("availability", "available" if logs.get("text") else "not_yet_published"),
            "text": logs.get("text", ""),
            "truncated": logs.get("truncated", False),
            "source": logs.get("source", "cli_kernels_logs"),
            "progress": logs.get("progress", {}),
            "fetched_at": good.get("fetched_at"),
            "wandb_live_text": wandb_live_text,
            "wandb_fetched_at": wandb_fetched_at,
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
            _raise_http(exc)

    @router.get("/previews/{preview_id}")
    def get_preview(preview_id: str):
        try:
            p = store.preview(preview_id)
            bundle = validated_bundle(store, p)
            p["notebook"] = (bundle / "notebook.ipynb").read_text()
            return p
        except (Conflict, PortalError) as exc:
            _raise_http(exc)

    @router.get("/previews/{preview_id}/download")
    def download_preview_bundle(preview_id: str):
        try:
            preview = store.preview(preview_id)
            bundle_zip = download_bundle(store, preview)
            return StreamingResponse(BytesIO(bundle_zip), media_type="application/zip",
                                     headers={"Content-Disposition": f"attachment; filename=preview-{preview_id}.zip"})
        except (Conflict, PortalError) as exc:
            _raise_http(exc)

    @router.post("/submissions")
    def submit_preview(payload: SubmitPayload):
        try:
            idem = payload.idem or f"submit:{payload.preview_id}"
            op = service.request_submit(payload.preview_id, payload.options, idem)
            return {"success": True, "operation_id": op}
        except (Conflict, PortalError) as exc:
            _raise_http(exc)

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

    @router.post("/operations/{operation_id}/reconcile")
    def reconcile_operation(operation_id: str):
        try:
            original = store.operation(operation_id)
            if original["kind"] != "submit" or original["state"] not in ("unknown", "reconciling"):
                raise PortalError("Submission does not require reconciliation")
            op_id = store.enqueue("reconcile", {"operation_id": original["id"]},
                                  original["account_id"], original["target"], cooldown=settings.cooldown)
            return {"success": True, "operation_id": op_id}
        except (Conflict, PortalError) as exc:
            _raise_http(exc)

    @router.post("/operations/{operation_id}/resolve")
    def resolve_operation(operation_id: str, payload: ResolvePayload):
        try:
            service.resolve_unknown(operation_id, payload.accepted, payload.evidence, payload.remote_version)
            return {"success": True}
        except (Conflict, PortalError) as exc:
            _raise_http(exc)

    return router


def create_app(settings: Optional[Settings] = None, store: Optional[Store] = None) -> FastAPI:
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
