"""Offline behavior contracts. Runs with pytest or stdlib unittest."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
import signal
import sys
import time
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import io

from research_portal.builder import build, download_bundle, source_inventory
from research_portal.domain import BuildOptions, Conflict, PortalError, Result, now, scrub, sampled_progress
from research_portal.providers import Providers, isolated_env
from research_portal.service import Service, monitor_health
from research_portal.settings import Settings, load_settings
from research_portal.storage import Store
from research_portal.worker import process_one
from research_portal.maintenance import backup, restore


class PortalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="research-portal-test-")
        self.addCleanup(self.temp.cleanup)
        self.settings = replace(Settings(), runtime=Path(self.temp.name), cooldown=0)
        self.store = Store(self.settings.runtime)
        self.a = self.account("first")
        self.b = self.account("second")
        self.service = Service(self.settings, self.store)

    def account(self, name, provider="kaggle", secret=""):
        return self.store.save_account(provider=provider, name=name, slug=name, principal=name, secret=secret)

    def preview(self, **kwargs):
        options = BuildOptions(**kwargs).payload()
        result = build(self.settings, self.store, self.a, options)
        return self.store.preview(result["preview_id"]), options

    def run_all(self, providers=None):
        while process_one(self.settings, self.store, "test-worker", providers):
            pass

    def test_empty_secret_preserves_and_rotation_invalidates(self):
        a = self.account("private", secret="synthetic-credential-123456")
        updated = self.store.save_account(provider="kaggle", name="Renamed", slug=a["slug"], principal=a["principal"],
                    account_id=a["id"], revision=a["revision"], secret="")
        self.assertEqual(self.store.credential(a["id"]), "synthetic-credential-123456")
        self.assertEqual(updated["credential_revision"], a["credential_revision"])
        rotated = self.store.save_account(provider="kaggle", name="Renamed", slug=a["slug"], principal=a["principal"],
                    account_id=a["id"], revision=updated["revision"], secret="different-synthetic-secret")
        self.assertEqual(rotated["credential_revision"], 2)
        self.assertIsNone(rotated["tested_at"])
        self.assertNotIn("secret_ref", rotated)

    def test_optimistic_edit_conflict(self):
        def update():
            return self.store.save_account(provider="kaggle", name="Edited", slug="first", principal="first",
                    account_id=self.a["id"], revision=1)
        update()
        with self.assertRaises(Conflict):
            update()

    def test_unique_slug_is_case_insensitive(self):
        with self.assertRaises(Conflict):
            self.account("FIRST")

    def test_default_replacement_revises_previous(self):
        self.store.save_account(provider="kaggle", name="First", slug="first", principal="first", is_default=True,
                                account_id=self.a["id"], revision=1)
        self.store.save_account(provider="kaggle", name="Second", slug="second", principal="second", is_default=True,
                                account_id=self.b["id"], revision=1)
        self.assertEqual(sum(a["is_default"] for a in self.store.accounts()), 1)
        self.assertEqual(self.store.account(self.a["id"])["revision"], 3)

    def test_disabled_default_rejected(self):
        with self.assertRaises(PortalError):
            self.store.save_account(provider="kaggle", name="Bad", slug="bad", principal="bad", enabled=False, is_default=True)

    def test_used_identity_cannot_change(self):
        self.store.attach(self.a["id"], "owner/kernel")
        with self.assertRaises(PortalError):
            self.store.save_account(provider="kaggle", name="First", slug="first", principal="someone-else",
                                    account_id=self.a["id"], revision=1)

    def test_secret_permissions_and_no_global_fallback(self):
        a = self.account("private", secret="synthetic-key-only")
        with patch.dict(os.environ, {"KAGGLE_KEY": "server-token"}):
            with self.assertRaises(PortalError):
                self.store.credential(self.a["id"])
            self.assertEqual(self.store.credential(a["id"]), "synthetic-key-only")
        self.assertEqual(self.store.root.stat().st_mode & 0o777, 0o700)
        for path in (self.store.root / "secrets").iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_secret_write_rollback(self):
        before = list((self.store.root / "secrets").iterdir())
        with self.assertRaises(Conflict):
            self.store.save_account(provider="kaggle", name="Duplicate", slug="first", principal="new", secret="synthetic-new-key")
        self.assertEqual(list((self.store.root / "secrets").iterdir()), before)

    def test_offline_cleanup_keeps_references(self):
        a = self.account("private", secret="synthetic-key")
        (self.store.root / "secrets" / "orphan").write_text("unused")
        self.store.cleanup_secrets()
        self.assertEqual(self.store.credential(a["id"]), "synthetic-key")
        self.assertFalse((self.store.root / "secrets/orphan").exists())

    def test_modes_isolated(self):
        live = Store(self.settings.runtime, "live")
        self.assertEqual(live.accounts(), [])
        with self.assertRaises(PortalError):
            live.account(self.a["id"])

    def test_backup_restore_preserves_secrets_previews_and_dispatch_fence(self):
        private = self.account("private", secret="synthetic-backup-key")
        p, options = self.preview()
        op = self.service.request_submit(p["id"], options, "backup-submit")
        self.store.claim("interrupted")
        with self.store.tx() as db:
            db.execute("UPDATE operations SET dispatched_at=? WHERE id=?", (now(), op))
        with tempfile.TemporaryDirectory() as parent:
            target = Path(parent) / "backup"
            recovered = Path(parent) / "restored"
            backup(self.store, target)
            restore(target, recovered)
            new = Store(recovered)
            self.assertEqual(new.credential(private["id"]), "synthetic-backup-key")
            self.assertEqual(new.operation(op)["state"], "unknown")
            self.assertEqual(new.preview(p["id"])["manifest"], p["manifest"])
            self.assertTrue(download_bundle(new, new.preview(p["id"])))

    def test_corrupt_backup_and_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as parent:
            target = Path(parent) / "backup"
            backup(self.store, target)
            (target / "portal.sqlite3").write_bytes(b"changed")
            with self.assertRaises(PortalError):
                restore(target, Path(parent) / "restored")
            (target / "backup-manifest.json").write_text(json.dumps({"portal.sqlite3": "", "../escape": ""}))
            with self.assertRaises(PortalError):
                restore(target, Path(parent) / "restored")

    def test_progress_clock_survives_many_unchanged_refreshes(self):
        w = self.account("tracking", "wandb")
        n = self.store.attach(self.a["id"], "owner/running", w["id"], "team/project/run")
        first = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        second = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        def row(i, when):
            return Result(w["id"], "team/project/run", "fixture", {"last_iteration": i, "progress_sample_at": when}).payload()
        self.store.observe(n, "wandb", row(100, first))
        self.store.observe(n, "wandb", row(200, second))
        for _ in range(25):
            self.store.observe(n, "wandb", row(200, second))
        observations = self.store.observations(n, "wandb")
        self.assertEqual(len(observations), 20)
        k = [Result("a", "o/k", "fixture", {"provider_state_normalized": "running"}).payload()]
        health = monitor_health(k, observations)
        self.assertEqual(health["health"], "suspected_stall")
        self.assertEqual(health["last_progress_at"], second)

    def test_different_tracking_binding_cannot_silently_replace(self):
        w = self.account("tracking", "wandb")
        self.store.attach(self.a["id"], "owner/running", w["id"], "team/project/run-a")
        with self.assertRaises(Conflict):
            self.store.attach(self.a["id"], "owner/running", w["id"], "team/project/run-b")
        self.store.attach(self.a["id"], "owner/running", w["id"], "team/project/run-b", "attempt-b")
        self.assertEqual(len(self.store.notebooks()), 2)

    def test_expired_preview_requires_rebuild(self):
        p, options = self.preview()
        with self.store.tx() as db:
            db.execute("UPDATE previews SET created_at=? WHERE id=?", ((datetime.now(timezone.utc)-timedelta(days=2)).isoformat(), p["id"]))
        with self.assertRaises(Conflict):
            self.service.request_submit(p["id"], options, "expired")

    def test_provider_subprocesses_isolate_two_accounts_and_redact_all_keys(self):
        a = self.account("private-a", secret="synthetic-key-account-a")
        b = self.account("private-b", secret="synthetic-key-account-b")
        live = replace(self.settings, mode="live")
        provider = Providers(live, self.store)
        calls = []
        def runner(argv, **kwargs):
            request = json.loads(kwargs["input"])
            calls.append((request["principal"], request["secret"], kwargs["env"]["HOME"]))
            self.assertNotIn(request["secret"], str(argv))
            self.assertNotIn(request["secret"], str(kwargs["env"]))
            return subprocess.CompletedProcess(argv, 0, json.dumps({"data": {"log": "synthetic-key-account-a synthetic-key-account-b"}}), "")
        with patch.object(provider, "preflight"), patch("research_portal.providers.subprocess.run", side_effect=runner), ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda acc: provider.call(acc["id"], "check", "owner/kernel"), [a, b]))
        self.assertEqual({(p, k) for p, k, _ in calls}, {("private-a", "synthetic-key-account-a"), ("private-b", "synthetic-key-account-b")})
        self.assertNotEqual(calls[0][2], calls[1][2])
        self.assertNotIn("synthetic-key-account", json.dumps(results))

    def test_future_schema_rejected(self):
        with self.store.tx() as db:
            db.execute("PRAGMA user_version=99")
        with self.assertRaises(PortalError):
            Store(self.settings.runtime)

    def test_attach_idempotent_and_explicit_wandb(self):
        n = self.store.attach(self.a["id"], "owner/kernel")
        self.assertEqual(n, self.store.attach(self.a["id"], "owner/kernel"))
        with self.assertRaises(PortalError):
            self.store.attach(self.a["id"], "owner/other", run_ref="team/project/run")

    def test_archive_preserves_cache(self):
        n = self.store.attach(self.a["id"], "owner/kernel")
        self.service.check(n)
        self.run_all()
        self.store.archive_account(self.a["id"], 1)
        self.assertEqual(self.service.check(n), [])
        self.assertEqual(len(self.store.observations(n, "kaggle")), 1)

    def test_read_error_preserves_previous_state(self):
        n = self.store.attach(self.a["id"], "owner/kernel")
        self.store.observe(n, "kaggle", Result(self.a["id"], "owner/kernel", "fixture:kaggle", {"provider_state_normalized": "running"}).payload())
        self.store.observe(n, "kaggle", Result(self.a["id"], "owner/kernel", "fixture:kaggle", error="network_error").payload())
        health = monitor_health(self.store.observations(n, "kaggle"), [])
        self.assertEqual(health["provider_state"], "running")
        self.assertEqual(health["last_check_error"], "network_error")
        self.assertEqual(health["health"], "unknown")

    def test_independent_source_errors(self):
        w = self.account("tracking", "wandb")
        n = self.store.attach(self.a["id"], "owner/running", w["id"], "team/project/forbidden")
        self.service.check(n)
        self.run_all()
        self.assertIsNone(self.store.observations(n, "kaggle")[0]["error"])
        self.assertEqual(self.store.observations(n, "wandb")[0]["error"], "forbidden")

    def test_read_request_cooldown(self):
        service = Service(replace(self.settings, cooldown=10), self.store)
        self.assertEqual(service.test_connection(self.a["id"]), service.test_connection(self.a["id"]))

    def test_build_cooldown_does_not_drop_changed_options(self):
        service = Service(replace(self.settings, cooldown=10), self.store)
        first = service.request_build(self.a["id"], BuildOptions().payload())
        changed = service.request_build(self.a["id"], BuildOptions(task="binary").payload())
        self.assertNotEqual(first, changed)
        self.assertEqual(changed, service.request_build(self.a["id"], BuildOptions(task="binary").payload()))

    def test_idempotency_survives_rotation_after_completed_submit(self):
        p, options = self.preview()
        op = self.service.request_submit(p["id"], options, "once")
        self.run_all()
        self.store.save_account(provider="kaggle", name="First", slug="first", principal="first", secret="rotated-test-key",
                                account_id=self.a["id"], revision=1)
        self.assertEqual(op, self.service.request_submit(p["id"], options, "once"))
        self.assertEqual(len([o for o in self.store.operations() if o["kind"] == "submit"]), 1)

    def test_progress_requires_increase_and_timestamp(self):
        k = [Result("a", "o/k", "fixture", {"provider_state_normalized": "running"}).payload()]
        def row(i, when):
            return Result("w", "t/p/r", "fixture", {"last_iteration": i, "progress_sample_at": when, "last_telemetry_at": now()}).payload()
        old = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        self.assertEqual(monitor_health(k, [row(100, now()), row(100, old)])["health"], "unknown")
        self.assertEqual(monitor_health(k, [row(200, now()), row(100, old)])["health"], "progressing")
        self.assertEqual(monitor_health(k, [row(200, old), row(100, old)])["health"], "suspected_stall")
        self.assertEqual(monitor_health(k, [row(200, None), row(100, None)])["health"], "unknown")

    def test_bhsd_mean_teacher_global_step_is_a_verified_training_axis(self):
        sample = sampled_progress([{"global_step": 250, "_timestamp": 1700000000, "_step": 900}], "mean_teacher")
        self.assertEqual(sample["last_iteration"], 250)
        self.assertEqual(sample["iteration_axis"], "global_step")

    def test_sdk_step_and_unknown_phase_global_step_are_not_iterations(self):
        self.assertIsNone(sampled_progress([{"_step": 900, "_timestamp": 1700000000}])["last_iteration"])
        self.assertIsNone(sampled_progress([{"global_step": 900, "_timestamp": 1700000000}], "pick")["last_iteration"])

    def test_progress_samples_without_timestamps_are_unavailable(self):
        self.assertIsNone(sampled_progress([{"iteration": 100}, {"iteration": 200, "_timestamp": None}])["last_iteration"])

    def test_terminal_and_stale_are_independent(self):
        k = Result("a", "o/k", "fixture", {"provider_state_normalized": "complete"}).payload()
        k["fetched_at"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        health = monitor_health([k], [])
        self.assertEqual(health["health"], "terminal")
        self.assertTrue(health["status_stale"])

    def test_build_without_push_and_bundle_options(self):
        p, options = self.preview(task="binary", dataset="owner/dataset", gpu=False, title="Custom title", slug="custom-kernel")
        self.assertEqual(self.store.operations(), [])
        self.assertEqual(p["manifest"]["metadata"]["id"], "first/custom-kernel")
        self.assertEqual(p["manifest"]["metadata"]["dataset_sources"], ["owner/dataset"])
        self.assertFalse(p["manifest"]["metadata"]["enable_gpu"])
        with zipfile.ZipFile(io.BytesIO(download_bundle(self.store, p))) as archive:
            self.assertEqual(set(archive.namelist()), {"notebook.ipynb", "kernel-metadata.json", "portal-manifest.json"})
            self.assertIn("binary", archive.read("notebook.ipynb").decode())

    def test_invalid_resume_and_template_rejected(self):
        for kwargs in ({"template": "pick"}, {"checkpoint": "best"}, {"resume_run": "bare"},
                       {"resume_run": "team/project/run", "tracking": "offline"}, {"dataset": "../../etc"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(PortalError):
                BuildOptions(**kwargs).validate()

    def test_unique_workspaces(self):
        a, _ = self.preview()
        b, _ = self.preview(task="binary")
        self.assertNotEqual(a["id"], b["id"])
        self.assertNotEqual(a["manifest"]["bundle_digest"], b["manifest"]["bundle_digest"])

    def test_tampered_preview_blocked(self):
        p, options = self.preview()
        (self.store.root / "previews" / p["id"] / "notebook.ipynb").write_text("changed")
        with self.assertRaises(PortalError):
            self.service.request_submit(p["id"], options, "key")

    def test_changed_options_and_rotated_account_block_submit(self):
        p, options = self.preview()
        with self.assertRaises(Conflict):
            self.service.request_submit(p["id"], BuildOptions(task="binary").payload(), "key")
        self.store.save_account(provider="kaggle", name="First", slug="first", principal="first", secret="rotated-test-key",
                                account_id=self.a["id"], revision=1)
        with self.assertRaises(Conflict):
            self.service.request_submit(p["id"], options, "key")

    def test_duplicate_idempotency_and_target_lock(self):
        p, options = self.preview()
        op = self.service.request_submit(p["id"], options, "same")
        self.assertEqual(op, self.service.request_submit(p["id"], options, "same"))
        with self.assertRaises(Conflict):
            self.store.enqueue("submit", {"different": True}, self.a["id"], "first/new", idem="same")
        p2, opts2 = self.preview()
        with self.assertRaises(Conflict):
            self.service.request_submit(p2["id"], opts2, "other")

    def test_two_claims_only_one_dispatch(self):
        p, options = self.preview()
        self.service.request_submit(p["id"], options, "key")
        with ThreadPoolExecutor(2) as pool:
            claims = list(pool.map(self.store.claim, ["worker-a", "worker-b"]))
        self.assertEqual(sum(c is not None for c in claims), 1)

    def test_disable_after_queue_prevents_dispatch(self):
        p, options = self.preview()
        op = self.service.request_submit(p["id"], options, "key")
        self.store.save_account(provider="kaggle", name="First", slug="first", principal="first", enabled=False,
                                account_id=self.a["id"], revision=1)
        self.run_all()
        self.assertEqual(self.store.operation(op)["state"], "failed")
        self.assertIsNone(self.store.operation(op)["dispatched_at"])

    def test_submit_success_attaches_attempt(self):
        p, options = self.preview()
        op = self.service.request_submit(p["id"], options, "key")
        self.run_all()
        self.assertEqual(self.store.operation(op)["state"], "succeeded")
        self.assertEqual(self.store.notebooks()[0]["attempt_id"], op)

    def test_timeout_blocks_target_and_never_retries(self):
        p, options = self.preview()
        op = self.service.request_submit(p["id"], options, "key")
        class TimeoutProvider:
            calls = 0
            def call(self, *args, **kwargs):
                self.calls += 1
                raise TimeoutError("synthetic-secret-must-not-leak")
        provider = TimeoutProvider()
        self.run_all(provider)
        self.store.recover()
        self.run_all(provider)
        self.assertEqual(provider.calls, 1)
        row = self.store.operation(op)
        self.assertEqual(row["state"], "unknown")
        self.assertNotIn("synthetic-secret", str(row))
        other, options2 = self.preview()
        with self.assertRaises(Conflict):
            self.service.request_submit(other["id"], options2, "new")

    def test_recover_before_and_after_fence(self):
        p, options = self.preview()
        op = self.service.request_submit(p["id"], options, "key")
        self.store.claim("dead-worker")
        self.store.recover()
        self.assertEqual(self.store.operation(op)["state"], "failed")
        with self.store.tx() as db:
            db.execute("UPDATE operations SET state='running',dispatched_at=? WHERE id=?", (now(), op))
        self.store.recover()
        self.assertEqual(self.store.operation(op)["state"], "unknown")

    def test_operator_resolution_and_no_latest_status_guess(self):
        p, options = self.preview()
        op = self.service.request_submit(p["id"], options, "key")
        self.store.finish(op, state="unknown")
        probe = self.store.enqueue("reconcile", {"operation_id": op}, self.a["id"], "first/research-portal-demo")
        self.run_all()
        self.assertEqual(self.store.operation(op)["state"], "unknown")
        self.assertEqual(json.loads(self.store.operation(probe)["result"])["data"]["evidence"], "insufficient")
        self.service.resolve_unknown(op, True, "Compared uploaded source against reviewed notebook", "v3")
        self.assertEqual(self.store.operation(op)["state"], "succeeded")
        self.assertEqual(self.store.notebooks()[0]["attempt_id"], op)

    def test_scrub_nested_secret_prefix_and_signed_url(self):
        token = "synthetic-token-123456789"
        value = {"config": {"api_key": token}, "log": token + " " + token[:12] + " https://host/file?signature=x"}
        output = json.dumps(scrub(value, [token]))
        self.assertNotIn(token[:12], output)
        self.assertNotIn("signature", output)

    def test_subprocess_env_does_not_inherit_credentials(self):
        with patch.dict(os.environ, {"KAGGLE_KEY": "global", "WANDB_API_KEY": "global", "PYTHONPATH": "/unsafe", "HTTP_PROXY": "http://user:secret@host"}):
            env = isolated_env(self.store.root)
        self.assertNotIn("KAGGLE_KEY", env)
        self.assertNotIn("WANDB_API_KEY", env)
        self.assertNotIn("HTTP_PROXY", env)
        self.assertNotIn("PYTHONPATH", env)
        self.assertEqual(env["HOME"], str(self.store.root))

    def test_live_disabled_without_dispatch(self):
        p, options = self.preview()
        live_service = Service(replace(self.settings, mode="live"), self.store)
        with self.assertRaises(PortalError):
            live_service.request_submit(p["id"], options, "key")

    def test_live_settings_require_local_runtime_confirmation(self):
        with patch.dict(os.environ, {"RESEARCH_PORTAL_MODE": "live", "RESEARCH_PORTAL_SETTINGS": str(self.store.root / "absent.toml")}, clear=True):
            with self.assertRaises(PortalError):
                load_settings()

    def test_provider_child_timeout_does_not_leak(self):
        a = self.account("private", secret="synthetic-only-key")
        live = replace(self.settings, mode="live")
        providers = Providers(live, self.store)
        with patch.object(providers, "preflight"), patch("research_portal.providers.subprocess.run", side_effect=subprocess.TimeoutExpired("safe", 40)):
            result = providers.call(a["id"], "push", "owner/kernel", bundle=self.store.root)
        self.assertEqual(result["error"], "ambiguous_timeout")
        self.assertNotIn("synthetic-only-key", json.dumps(result))

    def test_parse_log_progress(self):
        from research_portal.provider_child import parse_log_progress
        log = """
        [2026-11-03 12:00:00] Starting training on GPU
        Epoch 1/50 - Iteration 50 - loss: 0.8921
        Epoch 2/50 - Iteration 100 - loss: 0.4532
        Validation score: 0.88
        """
        parsed = parse_log_progress(log)
        self.assertEqual(parsed.get("epoch"), "2/50")
        self.assertEqual(parsed.get("iteration"), 100)
        self.assertAlmostEqual(parsed.get("loss"), 0.4532)
        self.assertIn("Validation score", parsed.get("recent_line", ""))

        self.assertEqual(parse_log_progress(""), {})
        self.assertEqual(parse_log_progress("Random unformatted output"), {"recent_line": "Random unformatted output"})

    def test_monitor_health_with_kaggle_log_progress(self):
        t1 = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        t2 = datetime.now(timezone.utc).isoformat()
        obs1 = {
            "fetched_at": t1,
            "data": {
                "provider_state_normalized": "running",
                "logs": {"availability": "available", "progress": {"iteration": 100, "epoch": "1/10", "loss": 0.5}},
            },
        }
        obs2 = {
            "fetched_at": t2,
            "data": {
                "provider_state_normalized": "running",
                "logs": {"availability": "available", "progress": {"iteration": 200, "epoch": "2/10", "loss": 0.3}},
            },
        }
        health = monitor_health([obs2, obs1], [])
        self.assertEqual(health["provider_state"], "running")
        self.assertEqual(health["last_iteration"], 200)
        self.assertEqual(health["last_epoch"], "2/10")
        self.assertEqual(health["last_loss"], 0.3)
        self.assertEqual(health["health"], "progressing")
        self.assertEqual(health["progress_source"], "kaggle_logs")

    def test_capabilities_reflect_kaggle_logs(self):
        from research_portal.providers import capabilities
        caps = capabilities()
        self.assertEqual(caps["kaggle_logs"], "kernels_logs")
        self.assertEqual(caps["logs_follow"], "supported")

    def test_kaggle_push_ref_normalization_and_error_classification(self):
        from research_portal.provider_child import error_code, extract_kernel_ref

        class FakePushResponse:
            def __init__(self, ref="", url="", versionNumber=None):
                self.ref = ref
                self.url = url
                self.versionNumber = versionNumber
                self.error = None

        self.assertEqual(extract_kernel_ref(FakePushResponse(ref="/code/owner/my-kernel")), "owner/my-kernel")
        self.assertEqual(extract_kernel_ref(FakePushResponse(ref="", url="https://www.kaggle.com/code/owner/my-kernel")), "owner/my-kernel")
        self.assertEqual(extract_kernel_ref(FakePushResponse(ref="owner/my-kernel")), "owner/my-kernel")

        self.assertEqual(error_code(ValueError("Cannot access kernel 'o/k' (Permission 'kernels.get' was denied).")), "forbidden")
        self.assertEqual(error_code(RuntimeError("401 Client Error: Unauthorized for url")), "invalid_credentials")
        self.assertEqual(error_code(RuntimeError("404 Not Found")), "not_found")
        self.assertEqual(error_code(RuntimeError("429 Too Many Requests: rate limit exceeded")), "rate_limited")

    def test_build_cleans_up_temporary_workspace_and_bind_run_to_submitted_attempt(self):
        p, options = self.preview()
        self.assertEqual(list((self.store.root / "work").iterdir()), [])
        op = self.service.request_submit(p["id"], options, "clean-submit")
        self.run_all()
        nb = self.store.notebooks()[0]
        self.assertEqual(nb["attempt_id"], op)
        self.assertEqual(nb["run_ref"], "")
        w = self.account("tracking", "wandb")
        rebound = self.store.attach(self.a["id"], nb["kernel"], w["id"], "team/project/run-1", attempt_id=op)
        self.assertEqual(rebound, nb["id"])
        self.assertEqual(self.store.notebook(nb["id"])["run_ref"], "team/project/run-1")

    def test_worker_cli_consumes_job_and_enforces_single_owner(self):
        op = self.service.test_connection(self.a["id"])
        env = dict(os.environ, RESEARCH_PORTAL_MODE="fixture", RESEARCH_PORTAL_RUNTIME=str(self.store.root),
                   RESEARCH_PORTAL_SETTINGS=str(self.store.root / "absent.toml"))
        worker = subprocess.Popen([sys.executable, "-m", "research_portal.worker"], env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if self.store.operation(op)["state"] == "succeeded":
                    break
                time.sleep(0.05)
            self.assertEqual(self.store.operation(op)["state"], "succeeded")
            duplicate = subprocess.run([sys.executable, "-m", "research_portal.worker", "--once"],
                                       env=env, capture_output=True, text=True, timeout=5)
            self.assertNotEqual(duplicate.returncode, 0)
            self.assertIn("already owns", duplicate.stderr)
        finally:
            worker.send_signal(signal.SIGINT)
            worker.communicate(timeout=5)
        self.assertFalse(self.store.worker_online())


class BhsdContractTests(unittest.TestCase):
    def test_actual_pinned_generator_builds_both_tasks_and_resume_offline(self):
        settings = Settings()
        if not settings.bhsd.exists():
            self.skipTest("Configured BHSD checkout not available")
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("PyYAML is required for source compatibility checks")
        before = subprocess.check_output(["git", "-C", str(settings.bhsd), "status", "--porcelain"])
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory, "live")
            account = store.save_account(provider="kaggle", name="Contract", slug="contract", principal="contract")
            settings = replace(settings, mode="live", runtime=Path(directory))
            inventory = source_inventory(settings)
            self.assertGreater(len(inventory), 5)
            for task in ("multiclass", "binary"):
                for resume in (False, True):
                    with self.subTest(task=task, resume=resume):
                        options = BuildOptions(task=task, tracking="kaggle_secrets" if resume else "offline",
                                               resume_run="synthetic-team/project/run" if resume else "",
                                               resume_mode="new-run" if resume else "", checkpoint="best" if resume else "")
                        result = build(settings, store, account, options.payload())
                        preview = store.preview(result["preview_id"])
                        notebook = json.loads((store.root / "previews" / preview["id"] / "notebook.ipynb").read_text())
                        text = json.dumps(notebook)
                        self.assertIn(settings.revision, text)
                        self.assertNotIn("reset', '--hard'", text)
                        self.assertEqual(preview["manifest"]["resolved_config"]["base_config"]["experiment"]["task"], task)
                        if resume:
                            self.assertIn("prepare_resume", text)
                            self.assertIn("UserSecretsClient", text)
                        else:
                            self.assertIn("offline", text)
        self.assertEqual(before, subprocess.check_output(["git", "-C", str(settings.bhsd), "status", "--porcelain"]))


if __name__ == "__main__":
    unittest.main()
