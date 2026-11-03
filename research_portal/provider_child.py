"""One-shot SDK boundary. Invoked by worker only, never by Streamlit rendering."""
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import sys


def error_code(exc):
    code = getattr(exc, "status", None) or getattr(getattr(exc, "response", None), "status_code", None)
    try:
        code = int(code) if code is not None else None
    except (TypeError, ValueError):
        code = None
    if code == 401:
        return "invalid_credentials"
    if code == 403:
        return "forbidden"
    if code == 404:
        return "not_found"
    if code == 429:
        return "rate_limited"
    if code and code >= 500:
        return "network_error"
    if "authentication" in type(exc).__name__.lower():
        return "invalid_credentials"
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)) or any(
        word in type(exc).__name__.lower() for word in ("timeout", "connection", "retry")):
        return "network_error"
    return "unknown"


def parse_log_progress(text):
    if not text:
        return {}
    progress = {}
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return {}
    progress["recent_line"] = lines[-1][:120]
    import re
    for line in reversed(lines[-50:]):
        if "epoch" not in progress:
            m = re.search(r"\bepoch[^\d]*(\d+)(?:[^\d/]+(\d+)|/(\d+))?", line, re.IGNORECASE)
            if m:
                cur = m.group(1)
                total = m.group(2) or m.group(3)
                progress["epoch"] = f"{cur}/{total}" if total else cur
        if "iteration" not in progress:
            m = re.search(r"\b(?:iteration|iter|step)[^\d]*(\d+)(?:[^\d/]+(\d+)|/(\d+))?", line, re.IGNORECASE)
            if m:
                cur = m.group(1)
                total = m.group(2) or m.group(3)
                progress["iteration"] = int(cur)
                if total:
                    progress["iteration_total"] = int(total)
        if "loss" not in progress:
            m = re.search(r"\bloss[^\d\w]*([0-9]+\.[0-9]+)", line, re.IGNORECASE)
            if m:
                progress["loss"] = float(m.group(1))
        if len(progress) >= 4:
            break
    return progress


def kaggle(request):
    # Support both Kaggle Access Token (KGAT_...) and legacy API key.
    secret = str(request.get("secret", "")).strip()
    if secret.startswith("KGAT_"):
        os.environ["KAGGLE_API_TOKEN"] = secret
        token_path = Path(os.environ["KAGGLE_CONFIG_DIR"]) / "access_token"
        token_path.write_text(secret)
        token_path.chmod(0o600)
    else:
        path = Path(os.environ["KAGGLE_CONFIG_DIR"]) / "kaggle.json"
        path.write_text(json.dumps({"username": request["principal"], "key": secret}))
        path.chmod(0o600)
    from kaggle.api.kaggle_api_extended import KaggleApi
    api = KaggleApi()
    api.authenticate()
    action, ref = request["action"], request["remote_ref"]
    if action == "test":
        api.kernels_list(page_size=1, user=request["principal"])
        return {"data": {"connection": "verified", "principal_verification": "unverified"}}
    if action == "push":
        # A single dispatch method, one invocation, and no fallback/retry by this adapter.
        # SDK's timeout argument is a training session limit, NOT an HTTP timeout.
        response = api.kernels_push(request["bundle"])
        if getattr(response, "error", None):
            return {"error": "provider_rejected", "data": {}}
        version = getattr(response, "version_number", None)
        if not getattr(response, "ref", None):
            return {"error": "unknown", "data": {}}
        if response.ref.lower() != ref.lower():
            return {"error": "remote_ref_mismatch", "data": {"actual_ref": response.ref}}
        return {"data": {"accepted": True, "url": "https://www.kaggle.com/code/" + ref},
                "remote_version": str(version) if version is not None else None}
    response = api.kernels_status(ref)
    raw_status = response.get("status", "unknown") if isinstance(response, dict) else getattr(response, "status", "unknown")
    status = str(getattr(raw_status, "name", raw_status)).lower()
    if action == "reconcile":
        return {"data": {"evidence": "insufficient", "latest_provider_state": status,
                         "message": "Latest status is not evidence of this preview/version; inspect remote version manually"}}
    states = {"queued": "queued", "running": "running", "complete": "complete", "error": "error",
              "cancelacknowledged": "cancelled", "cancel_acknowledged": "cancelled"}
    data = {"provider_state_raw": status, "provider_state_normalized": states.get(status, "unknown"),
            "logs": {"availability": "unsupported", "text": "", "source": "none", "progress": {}}}
    # Fetch logs via official Kaggle CLI API (kernels_logs) or bounded legacy endpoint fallback.
    if hasattr(api, "kernels_logs"):
        try:
            raw = api.kernels_logs(ref) or ""
            if raw:
                truncated = len(raw) > 64000
                data["logs"] = {
                    "availability": "available",
                    "text": raw[-64000:] if truncated else raw,
                    "truncated": truncated,
                    "source": "cli_kernels_logs",
                    "progress": parse_log_progress(raw),
                    "total_bytes": len(raw),
                }
            else:
                data["logs"] = {"availability": "not_yet_published", "text": "", "source": "cli_kernels_logs", "progress": {}}
        except Exception as exc:
            code = error_code(exc)
            data["logs"] = {
                "availability": "forbidden" if code == "forbidden" else ("rate_limited" if code == "rate_limited" else ("network_error" if code == "network_error" else "not_yet_published")),
                "text": "",
                "source": "cli_kernels_logs",
                "progress": {},
            }
    else:
        try:
            import requests
            owner, slug = ref.split("/")
            with requests.get("https://www.kaggle.com/api/v1/kernels/output", params={"userName": owner, "kernelSlug": slug},
                              auth=(request["principal"], request["secret"]), timeout=10, stream=True) as response:
                if response.status_code == 200:
                    body = bytearray()
                    for block in response.iter_content(8192):
                        body.extend(block)
                        if len(body) > 1_000_000:
                            data["logs"] = {"availability": "truncated", "text": "", "reason": "Output response exceeds 1 MB", "source": "legacy_endpoint", "progress": {}}
                            break
                    else:
                        raw = json.loads(body).get("log") or ""
                        try:
                            events = json.loads(raw)
                            if isinstance(events, list):
                                raw = "".join(e.get("data", "") for e in events if isinstance(e, dict))
                        except ValueError:
                            pass
                        truncated = len(raw) > 64000
                        data["logs"] = {
                            "availability": "available" if raw else "not_yet_published",
                            "text": raw[-64000:],
                            "truncated": truncated,
                            "source": "legacy_endpoint",
                            "progress": parse_log_progress(raw),
                        }
                else:
                    data["logs"]["availability"] = {403: "forbidden", 404: "not_yet_published", 429: "rate_limited"}.get(response.status_code, "unknown")
        except Exception:
            data["logs"]["availability"] = "network_error"
    remote_version = None
    try:
        with api.build_kaggle_client() as kaggle_client:
            from kagglesdk.kernels.types.kernels_api_service import ApiGetKernelRequest
            owner, slug = ref.split("/")
            k_req = ApiGetKernelRequest()
            k_req.user_name = owner
            k_req.kernel_slug = slug
            k_res = kaggle_client.kernels.kernels_api_client.get_kernel(k_req)
            if hasattr(k_res, "metadata") and k_res.metadata:
                ver = getattr(k_res.metadata, "current_version_number", None) or getattr(k_res.metadata, "currentVersionNumber", None)
                if ver is not None:
                    remote_version = str(ver)
    except Exception:
        pass
    return {"data": data, "remote_version": remote_version}


def wandb(request):
    import wandb as sdk
    # Explicit credential, isolated HOME, no wandb.login/global session.
    api = sdk.Api(api_key=request["secret"], timeout=min(request["timeout"], 30),
                  overrides={"entity": request["principal"]})
    if request["action"] == "test":
        _ = api.viewer
        return {"data": {"connection": "verified", "principal_verification": "unverified"}}
    run = api.run(request["remote_ref"])
    rows = run.history(samples=20, pandas=False)
    # These are bounded sampled points, not an exact history export or a proof of recency.
    from .domain import sampled_progress
    config = dict(run.config)
    method = config.get("method", {})
    method = method.get("name") if isinstance(method, dict) else method
    progress = sampled_progress(rows, method)
    attrs = getattr(run, "_attrs", {})
    return {"data": {"state": run.state, "url": run.url, "config": config, "summary": dict(run.summary), **progress,
                     "last_telemetry_at": attrs.get("heartbeatAt"), "system": run.system_metrics,
                     "history_sampled": True},
            "warnings": ["Progress is sampled (20 rows); training iteration may be unavailable. Heartbeat is tracking liveness only."]}


def main():
    request = json.load(sys.stdin)
    # SDK diagnostics may contain credentials. Suppress them before the protocol boundary.
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        try:
            result = kaggle(request) if request["provider"] == "kaggle" else wandb(request)
        except Exception as exc:
            result = {"error": error_code(exc), "data": {}}
    sys.stdout.write(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
