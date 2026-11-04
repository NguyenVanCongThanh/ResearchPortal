"""Pydantic schemas and shared HTTP error helpers for ResearchPortal API."""
from typing import Any, Dict, Optional
from fastapi import HTTPException
from pydantic import BaseModel, Field

from ..domain import Conflict


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


def raise_http_error(exc: Exception) -> None:
    if isinstance(exc, Conflict):
        raise HTTPException(status_code=409, detail=str(exc)) from None
    if "not found" in str(exc).lower():
        raise HTTPException(status_code=404, detail=str(exc)) from None
    raise HTTPException(status_code=400, detail=str(exc)) from None

