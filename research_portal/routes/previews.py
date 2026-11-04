"""Build previews and submission routes."""
from io import BytesIO
from typing import Optional
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..builder import download_bundle, validated_bundle
from ..domain import Conflict, PortalError
from .schemas import BuildPayload, SubmitPayload, raise_http_error


def create_previews_router(portal) -> APIRouter:
    router = APIRouter()
    store = portal.store
    service = portal.service

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
            raise_http_error(exc)

    @router.get("/previews/{preview_id}")
    def get_preview(preview_id: str):
        try:
            p = store.preview(preview_id)
            bundle = validated_bundle(store, p)
            p["notebook"] = (bundle / "notebook.ipynb").read_text()
            return p
        except (Conflict, PortalError) as exc:
            raise_http_error(exc)

    @router.get("/previews/{preview_id}/download")
    def download_preview_bundle(preview_id: str):
        try:
            preview = store.preview(preview_id)
            bundle_zip = download_bundle(store, preview)
            return StreamingResponse(BytesIO(bundle_zip), media_type="application/zip",
                                     headers={"Content-Disposition": f"attachment; filename=preview-{preview_id}.zip"})
        except (Conflict, PortalError) as exc:
            raise_http_error(exc)

    @router.post("/submissions")
    def submit_preview(payload: SubmitPayload):
        try:
            idem = payload.idem or f"submit:{payload.preview_id}"
            op = service.request_submit(payload.preview_id, payload.options, idem)
            return {"success": True, "operation_id": op}
        except (Conflict, PortalError) as exc:
            raise_http_error(exc)

    return router

