"""Accounts management routes."""
from typing import Optional
from fastapi import APIRouter, Query

from ..domain import Conflict, PortalError
from .schemas import AccountPayload, raise_http_error


def create_accounts_router(portal) -> APIRouter:
    router = APIRouter()
    store = portal.store
    service = portal.service

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
            raise_http_error(exc)

    @router.post("/accounts/{account_id}/test")
    def test_account(account_id: str):
        try:
            op = service.test_connection(account_id)
            return {"success": True, "operation_id": op}
        except (Conflict, PortalError) as exc:
            raise_http_error(exc)

    @router.delete("/accounts/{account_id}")
    def archive_account(account_id: str, revision: int = Query(...)):
        try:
            store.archive_account(account_id, revision)
            return {"success": True}
        except (Conflict, PortalError) as exc:
            raise_http_error(exc)

    return router

