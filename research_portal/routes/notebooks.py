"""Notebooks and live training monitor routes."""
import json
from fastapi import APIRouter

from ..domain import Conflict, PortalError
from ..service import monitor_health
from ..storage import uid
from .schemas import AttachNotebookPayload, raise_http_error


def create_notebooks_router(portal) -> APIRouter:
    router = APIRouter()
    store = portal.store
    service = portal.service
    settings = portal.settings

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
            raise_http_error(exc)

    @router.post("/notebooks/{notebook_id}/check")
    def check_notebook(notebook_id: str):
        try:
            op_ids = service.check(notebook_id)
            return {"success": True, "operation_ids": op_ids}
        except (Conflict, PortalError) as exc:
            raise_http_error(exc)

    @router.get("/notebooks/{notebook_id}/logs")
    def get_notebook_logs(notebook_id: str):
        try:
            store.notebook(notebook_id)
        except PortalError as exc:
            raise_http_error(exc)
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

    return router

