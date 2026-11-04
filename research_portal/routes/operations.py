"""Operations ledger, reconciliation, and operator resolution routes."""
import json
from fastapi import APIRouter

from ..domain import Conflict, PortalError
from .schemas import ResolvePayload, raise_http_error


def create_operations_router(portal) -> APIRouter:
    router = APIRouter()
    store = portal.store
    service = portal.service
    settings = portal.settings

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
            raise_http_error(exc)

    @router.post("/operations/{operation_id}/resolve")
    def resolve_operation(operation_id: str, payload: ResolvePayload):
        try:
            service.resolve_unknown(operation_id, payload.accepted, payload.evidence, payload.remote_version)
            return {"success": True}
        except (Conflict, PortalError) as exc:
            raise_http_error(exc)

    return router

