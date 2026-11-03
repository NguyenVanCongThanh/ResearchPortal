"""Fixture adapter and bounded, credential-isolated provider subprocesses."""
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from .domain import PortalError, Result, now, reference, scrub


def isolated_env(home):
    # Deliberately do not inherit provider keys, proxy credentials, .netrc or PYTHONPATH.
    env = {k: os.environ[k] for k in ("PATH", "LANG", "SSL_CERT_FILE", "SSL_CERT_DIR") if k in os.environ}
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(home), PYTHONNOUSERSITE="1",
               WANDB_CONFIG_DIR=str(home), WANDB_CACHE_DIR=str(home), WANDB_DIR=str(home),
               KAGGLE_CONFIG_DIR=str(home), WANDB_SILENT="true", WANDB_CONSOLE="off")
    return env


def capabilities():
    versions = {}
    for name in ("kaggle", "wandb", "streamlit"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not_installed"
    k_ver = versions.get("kaggle", "")
    has_cli_logs = bool(k_ver and not k_ver.startswith("1."))
    return {"versions": versions, "quota": "unsupported",
            "logs_follow": "supported" if has_cli_logs else "unsupported",
            "kaggle_logs": "kernels_logs" if has_cli_logs else "experimental_output_endpoint",
            "authenticated_compatibility": "unverified",
            "templates": {"mean_teacher": ["multiclass", "binary", "resume"], "pick": "unsupported"}}


class Providers:
    def __init__(self, settings, store):
        self.settings, self.store = settings, store

    @staticmethod
    def preflight(provider):
        supported = {"kaggle": {"2.0.2", "1.7.4.5"}, "wandb": {"0.26.1"}}[provider]
        try:
            installed = importlib.metadata.version(provider)
        except importlib.metadata.PackageNotFoundError:
            raise PortalError("Provider dependency is missing; install requirements.txt in the worker environment") from None
        if installed not in supported:
            raise PortalError("Provider version differs from the pinned adapter baseline; compatibility validation required")

    def call(self, account_id, action, remote_ref="", bundle=None, *, account_snapshot=None, secret_snapshot=None):
        account = account_snapshot or self.store.account(account_id)
        provider = account["provider"]
        if not account["enabled"] or account["archived"]:
            raise PortalError("Connection disabled; cached observations remain available")
        if remote_ref:
            reference(remote_ref, 2 if provider == "kaggle" else 3)
        if action not in ("test", "check", "push", "reconcile") or (action in ("push", "reconcile") and provider != "kaggle"):
            raise PortalError("Unsupported provider action")
        if self.settings.mode == "fixture":
            return self.fixture(account_id, provider, action, remote_ref)
        try:
            self.preflight(provider)
        except PortalError:
            return Result(account_id, remote_ref, provider, error="unsupported_dependency",
                          warnings=["Install the pinned requirements in the worker environment"]).payload()
        secret = secret_snapshot if secret_snapshot is not None else self.store.credential(account_id)
        with tempfile.TemporaryDirectory(dir=self.store.root / "work", prefix="provider-") as home:
            request = {"provider": provider, "action": action, "principal": account["principal"],
                       "secret": secret, "remote_ref": remote_ref, "bundle": str(bundle) if bundle else None,
                       "timeout": self.settings.timeout}
            try:
                result = subprocess.run([sys.executable, "-m", "research_portal.provider_child"],
                                        input=json.dumps(request), text=True, capture_output=True,
                                        env=isolated_env(home), cwd=Path(__file__).resolve().parents[1],
                                        timeout=self.settings.timeout)
            except subprocess.TimeoutExpired:
                return Result(account_id, remote_ref, provider, error="ambiguous_timeout" if action == "push" else "network_error").payload()
            # Third-party stdout/stderr is never surfaced, even on failure.
            if result.returncode or len(result.stdout) > 2_000_000:
                return Result(account_id, remote_ref, provider, error="unknown").payload()
            try:
                payload = json.loads(result.stdout)
            except (ValueError, TypeError):
                return Result(account_id, remote_ref, provider, error="unknown").payload()
            secrets = self.store.redaction_values()
            return Result(account_id, remote_ref, provider, data=scrub(payload.get("data", {}), secrets),
                          error=payload.get("error"), warnings=scrub(payload.get("warnings", []), secrets),
                          remote_version=payload.get("remote_version")).payload()

    def push_snapshot(self, account, credential, remote_ref, bundle):
        return self.call(account["id"], "push", remote_ref, bundle=bundle,
                         account_snapshot=account, secret_snapshot=credential)

    @staticmethod
    def fixture(account_id, provider, action, ref):
        fixtures = json.loads((Path(__file__).resolve().parents[1] / "tests/fixtures/providers.json").read_text())
        if action == "test":
            data = {"connection": "verified", "principal_verification": "unverified"}
        elif action == "push":
            data = {"accepted": True, "url": f"https://www.kaggle.com/code/{ref}", "remote_version": "fixture-1"}
        elif action == "reconcile":
            data = {"evidence": "insufficient", "message": "Latest slug status cannot identify a submission"}
        else:
            scenario = ref.rsplit("/", 1)[-1]
            data = dict(fixtures[provider].get(scenario, fixtures[provider]["default"]))
            if "error" in data:
                return Result(account_id, ref, "fixture:" + provider, error=data["error"]).payload()
            if provider == "wandb" and data.get("last_iteration") is not None:
                data["last_telemetry_at"] = now()
                data["progress_sample_at"] = now()
        return Result(account_id, ref, "fixture:" + provider, data=data,
                      warnings=["Synthetic fixture; no online compatibility evidence"]).payload()
