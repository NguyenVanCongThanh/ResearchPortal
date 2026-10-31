"""UI/worker shared workflows. Rendering never dispatches a provider request."""
from datetime import datetime, timezone
import json

from .builder import build, inventory_digest, validated_bundle
from .domain import BuildOptions, Conflict, PortalError, digest, now, scrub
from .providers import Providers


class Service:
    def __init__(self, settings, store, providers=None):
        self.settings, self.store = settings, store
        self.providers = providers or Providers(settings, store)

    def test_connection(self, account_id):
        account = self.store.account(account_id)
        if not account["enabled"]:
            raise PortalError("Connection disabled")
        return self.store.enqueue("test", {"revision": account["revision"]}, account_id,
                                  cooldown=self.settings.cooldown)

    def check(self, notebook_id):
        notebook = self.store.notebook(notebook_id)
        ids = []
        for provider, account_key in (("kaggle", "account_id"), ("wandb", "wandb_account_id")):
            account_id = notebook[account_key]
            if account_id and self.store.account(account_id)["enabled"]:
                ids.append(self.store.enqueue("check_" + provider, {"notebook_id": notebook_id}, account_id,
                                              notebook_id, cooldown=self.settings.cooldown))
        return ids

    def request_build(self, account_id, options):
        options = BuildOptions(**options).validate().payload()
        account = self.store.account(account_id)
        if not account["enabled"]:
            raise PortalError("Account disabled")
        return self.store.enqueue("build", {"options": options, "revision": account["revision"]},
                                  account_id, cooldown=self.settings.cooldown)

    def validate_preview(self, preview, current_options=None):
        if (datetime.now(timezone.utc) - datetime.fromisoformat(preview["created_at"])).total_seconds() > 86400:
            raise Conflict("Preview expired after 24 hours; build again")
        account = self.store.account(preview["account_id"])
        if not account["enabled"] or account["archived"]:
            raise PortalError("Account disabled; build with an enabled account")
        if (account["revision"], account["credential_revision"]) != (preview["account_revision"], preview["credential_revision"]):
            raise Conflict("Account/credential changed after preview; build again")
        if current_options is not None and digest(current_options) != digest(preview["options"]):
            raise Conflict("Options changed after preview; build again")
        if self.settings.mode == "live":
            if preview["manifest"]["source_revision"] != self.settings.revision or inventory_digest(self.settings) != preview["manifest"]["source_digest"]:
                raise Conflict("BHSD source changed; build again")
        return account, validated_bundle(self.store, preview)

    def request_submit(self, preview_id, current_options, idem):
        preview = self.store.preview(preview_id)
        payload = {"preview_id": preview_id, "bundle_digest": preview["manifest"]["bundle_digest"]}
        if self.store.rows("SELECT id FROM operations WHERE mode=? AND idem=?", (self.store.mode, idem)):
            if digest(current_options) != digest(preview["options"]):
                raise Conflict("Options differ from the original request")
            return self.store.enqueue("submit", payload, preview["account_id"], preview["manifest"]["kernel"], idem=idem)
        if self.settings.mode == "live" and not self.settings.allow_live_submit:
            raise PortalError("Live submit is disabled in settings")
        account, _ = self.validate_preview(preview, current_options)
        if self.settings.mode == "live" and hasattr(self.providers, "preflight"):
            self.providers.preflight("kaggle")
        return self.store.enqueue("submit", payload,
                                  account["id"], preview["manifest"]["kernel"], idem=idem)

    def execute(self, operation):
        kind, payload = operation["kind"], json.loads(operation["payload"])
        account_id = operation["account_id"]
        if kind == "test":
            result = self.providers.call(account_id, "test")
            with self.store.tx() as db:
                db.execute("UPDATE accounts SET tested_at=?,test_result=? WHERE id=? AND mode=? AND revision=?",
                           (result["fetched_at"], result["error"] or "verified", account_id, self.settings.mode, payload["revision"]))
            return result
        if kind.startswith("check_"):
            provider = kind.removeprefix("check_")
            notebook = self.store.notebook(payload["notebook_id"])
            result = self.providers.call(account_id, "check", notebook["kernel"] if provider == "kaggle" else notebook["run_ref"])
            self.store.observe(notebook["id"], provider, result)
            return result
        if kind == "build":
            account = self.store.account(account_id)
            if account["revision"] != payload["revision"]:
                raise Conflict("Account changed before build")
            return build(self.settings, self.store, account, payload["options"])
        if kind == "reconcile":
            original = self.store.operation(payload["operation_id"])
            if original["state"] not in ("unknown", "reconciling"):
                raise PortalError("Submission does not require reconciliation")
            result = self.providers.call(account_id, "reconcile", original["target"])
            self.store.audit("reconciliation_probe", {"operation": original["id"], "evidence": "insufficient"})
            return result
        if kind != "submit":
            raise PortalError("Unknown operation")
        if self.settings.mode == "live" and not self.settings.allow_live_submit:
            raise PortalError("Live submit is disabled")
        preview = self.store.preview(payload["preview_id"])
        account, bundle = self.validate_preview(preview)
        if self.settings.mode == "live" and hasattr(self.providers, "preflight"):
            self.providers.preflight("kaggle")
        if payload["bundle_digest"] != preview["manifest"]["bundle_digest"]:
            raise Conflict("Submission digest mismatch")
        # Read the exact credential snapshot before fencing. Rotation leaves old files
        # intact until offline cleanup. No fallback to the server's identity.
        credential = self.store.credential(account_id) if self.settings.mode == "live" else None
        with self.store.tx() as db:
            current = db.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
            if not current["enabled"] or current["archived"] or current["revision"] != preview["account_revision"]:
                raise Conflict("Account changed before dispatch")
            op = db.execute("SELECT * FROM operations WHERE id=?", (operation["id"],)).fetchone()
            if op["state"] != "running" or op["dispatched_at"]:
                raise Conflict("Submission already dispatched or no longer claimable")
            db.execute("UPDATE operations SET dispatched_at=?,updated_at=? WHERE id=?", (now(), now(), operation["id"]))
        # Dispatch is fenced BEFORE the network call. Any exception beyond this point
        # becomes unknown, even when the provider might have accepted the request.
        try:
            if hasattr(self.providers, "push_snapshot"):
                result = self.providers.push_snapshot(account, credential, preview["manifest"]["kernel"], bundle)
            else:  # Contract fakes in offline tests.
                result = self.providers.call(account_id, "push", preview["manifest"]["kernel"], bundle=bundle)
        except Exception:
            self.store.finish(operation["id"], error="Dispatch outcome unknown", state="unknown")
            return None
        if result["error"]:
            self.store.finish(operation["id"], result=result, error=result["error"], state="unknown")
            return None
        if not result["data"].get("accepted"):
            self.store.finish(operation["id"], result=result, error="Acceptance unverified", state="unknown")
            return None
        notebook_id = self.store.attach(account_id, preview["manifest"]["kernel"], attempt_id=operation["id"])
        self.store.audit("submission_accepted", {"operation": operation["id"], "preview": preview["id"], "notebook": notebook_id})
        return {"provider": result, "notebook_id": notebook_id, "preview_id": preview["id"]}

    def resolve_unknown(self, operation_id, accepted, evidence, remote_version=""):
        if not evidence.strip() or len(evidence) > 1000 or (accepted and not remote_version.strip()):
            raise PortalError("Record evidence and, if accepted, the observed remote version")
        with self.store.tx() as db:
            op = db.execute("SELECT * FROM operations WHERE id=? AND mode=?", (operation_id, self.store.mode)).fetchone()
            if not op or op["kind"] != "submit" or op["state"] not in ("unknown", "reconciling"):
                raise Conflict("Only unresolved submissions can be adjudicated")
            result = {"operator_reported": True, "accepted": bool(accepted),
                      "evidence": scrub(evidence, self.store.redaction_values()), "remote_version": scrub(remote_version, self.store.redaction_values())}
            db.execute("UPDATE operations SET state=?,result=?,error=NULL,updated_at=? WHERE id=?",
                       ("succeeded" if accepted else "cancelled", json.dumps(result), now(), operation_id))
        if accepted:
            self.store.attach(op["account_id"], op["target"], attempt_id=operation_id)
        self.store.audit("operator_resolution", {"operation": operation_id, "accepted": bool(accepted)})


def monitor_health(kaggle, wandb, *, stall_seconds=1200, stale_seconds=180):
    """Evaluate only timestamped evidence; never infer progress from RUNNING."""
    stamp = datetime.now(timezone.utc)

    def age(value):
        if not isinstance(value, str):
            return None
        try:
            elapsed = (stamp - datetime.fromisoformat(value.replace("Z", "+00:00"))).total_seconds()
            return elapsed if elapsed >= 0 else None
        except (TypeError, ValueError):
            return None

    good_k = next((x for x in kaggle if not x.get("error")), None)
    state = good_k["data"].get("provider_state_normalized", "unknown") if good_k else "unknown"
    freshness = age(good_k["fetched_at"]) if good_k else None
    result = {"health": "unknown", "provider_state": state, "status_stale": freshness is None or freshness > stale_seconds,
              "provider_observed_at": good_k["fetched_at"] if good_k else None,
              "last_check_attempt_at": kaggle[0]["fetched_at"] if kaggle else None,
              "last_check_error": kaggle[0].get("error") if kaggle else None, "last_progress_at": None, "last_iteration": None}
    good_w = [x for x in wandb if not x.get("error")]
    if good_w:
        result["last_iteration"] = good_w[0]["data"].get("last_iteration")
        result["last_progress_at"] = good_w[0]["data"].get("observed_last_progress_at")
    if state in ("complete", "error", "cancelled"):
        result["health"] = "terminal"
        return result
    # Observed increase must have a NEW sample timestamp; resampling an old row
    # must not repeatedly refresh the progress clock.
    for newer, older in zip(good_w, good_w[1:]):
        if result["last_progress_at"]:
            break
        a, b = newer["data"], older["data"]
        ai, bi = a.get("last_iteration"), b.get("last_iteration")
        sample = a.get("progress_sample_at")
        if isinstance(ai, (int, float)) and isinstance(bi, (int, float)) and ai > bi and sample:
            result["last_progress_at"] = sample
            break
    elapsed = age(result["last_progress_at"])
    if state == "queued":
        result["health"] = "pending"
    elif state == "running" and elapsed is not None:
        result["health"] = "suspected_stall" if elapsed > stall_seconds else "progressing"
    return result
