"""API endpoint, security, and end-to-end background worker tests for FastAPI server."""
from pathlib import Path
import tempfile
import time
import unittest

from fastapi.testclient import TestClient

from research_portal.api import create_app
from research_portal.domain import BuildOptions
from research_portal.settings import Settings
from research_portal.storage import Store


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="research-portal-api-test-")
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings(runtime=Path(self.temp.name), mode="fixture", cooldown=0)
        self.store = Store(self.settings.runtime, self.settings.mode)
        self.app = create_app(self.settings, self.store)
        self.client = TestClient(self.app)

    def test_system_status(self):
        res = self.client.get("/api/system/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["mode"], "fixture")
        self.assertIn("capabilities", data)
        self.assertEqual(data["capabilities"]["kaggle_logs"], "kernels_logs")

    def test_path_traversal_and_cors_hardening(self):
        for probe in (
            "/..%2fconfig/settings.example.toml",
            "/..%2f..%2f..%2f..%2fetc/hostname",
            "/../config/settings.example.toml",
            "/static/..%2fserver.py",
        ):
            res = self.client.get(probe)
            self.assertNotIn("allow_live_submit", res.text)
            self.assertNotIn("create_app", res.text)
            self.assertIn(res.status_code, (404, 200))
            if res.status_code == 200:
                self.assertIn("<title>ResearchPortal", res.text)
        cors = self.client.get("/api/accounts", headers={"Origin": "https://evil.example"})
        self.assertIsNone(cors.headers.get("access-control-allow-origin"))

    def test_accounts_crud_preserves_description_and_returns_409_on_conflict(self):
        res = self.client.post("/api/accounts", json={
            "provider": "kaggle",
            "name": "Test Kaggle",
            "slug": "test-kaggle",
            "principal": "test-user",
            "description": "Initial description",
            "secret": "test-key-123",
            "enabled": True,
            "is_default": True,
        })
        self.assertEqual(res.status_code, 200)
        acc = res.json()["account"]
        self.assertEqual(acc["name"], "Test Kaggle")
        self.assertEqual(acc["description"], "Initial description")

        # Edit without description field (legacy payload) preserves existing description
        res_edit = self.client.post("/api/accounts", json={
            "account_id": acc["id"],
            "revision": acc["revision"],
            "provider": "kaggle",
            "name": "Test Kaggle Renamed",
            "slug": "test-kaggle",
            "principal": "test-user",
            "secret": "",
            "enabled": True,
            "is_default": True,
        })
        self.assertEqual(res_edit.status_code, 200)
        self.assertEqual(res_edit.json()["account"]["description"], "Initial description")

        # Stale revision returns 409 Conflict
        res_stale = self.client.post("/api/accounts", json={
            "account_id": acc["id"],
            "revision": acc["revision"],
            "provider": "kaggle",
            "name": "Stale Edit",
            "slug": "test-kaggle",
            "principal": "test-user",
        })
        self.assertEqual(res_stale.status_code, 409)

        # Archive with stale revision returns 409 Conflict
        res_arch_stale = self.client.delete(f"/api/accounts/{acc['id']}?revision={acc['revision']}")
        self.assertEqual(res_arch_stale.status_code, 409)

        # List accounts
        res = self.client.get("/api/accounts")
        self.assertEqual(res.status_code, 200)
        accounts = res.json()
        self.assertEqual(len(accounts), 1)
        self.assertNotIn("secret", accounts[0])
        self.assertEqual(accounts[0]["principal"], "test-user")

        # Test connection
        res = self.client.post(f"/api/accounts/{acc['id']}/test")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])

    def test_notebook_attach_and_check(self):
        acc = self.store.save_account(provider="kaggle", name="AttachTest", slug="attach-test", principal="attach-principal")
        res = self.client.post("/api/notebooks", json={
            "account_id": acc["id"],
            "kernel": "attach-principal/demo-run",
            "new_attempt": False,
        })
        self.assertEqual(res.status_code, 200)
        nb_id = res.json()["notebook_id"]

        res = self.client.get("/api/notebooks")
        self.assertEqual(res.status_code, 200)
        nbs = res.json()
        self.assertEqual(len(nbs), 1)
        self.assertEqual(nbs[0]["kernel"], "attach-principal/demo-run")

        res = self.client.post(f"/api/notebooks/{nb_id}/check")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])

        res = self.client.get(f"/api/notebooks/{nb_id}/logs")
        self.assertEqual(res.status_code, 200)
        log_data = res.json()
        self.assertIn("availability", log_data)
        self.assertIn("wandb_live_text", log_data)

        self.assertEqual(self.client.get("/api/notebooks/missing-id/logs").status_code, 404)

    def test_in_process_worker_executes_build_submit_and_reconcile_end_to_end(self):
        with TestClient(self.app) as client:
            status_res = client.get("/api/system/status").json()
            self.assertTrue(status_res["worker_online"])

            kag = [a for a in client.get("/api/accounts").json() if a["provider"] == "kaggle"][0]

            # Enqueue build with Web UI payload shape (no 'template' key)
            ui_options = {
                "task": "binary",
                "slug": "",
                "title": "",
                "dataset": "",
                "gpu": True,
                "tracking": "offline",
                "resume_run": "",
                "resume_mode": "",
                "checkpoint": "",
            }
            build_res = client.post("/api/previews", json={"account_id": kag["id"], "options": ui_options})
            self.assertEqual(build_res.status_code, 200)
            build_op_id = build_res.json()["operation_id"]

            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                ops = {o["id"]: o for o in client.get("/api/operations").json()}
                if ops[build_op_id]["state"] == "succeeded":
                    break
                time.sleep(0.05)
            self.assertEqual(ops[build_op_id]["state"], "succeeded")

            # GET /api/previews returns parsed manifest and options dicts
            previews = client.get("/api/previews").json()
            self.assertEqual(len(previews), 1)
            self.assertIsInstance(previews[0]["manifest"], dict)
            self.assertIsInstance(previews[0]["options"], dict)
            preview_id = previews[0]["id"]

            # GET /api/previews/{id} includes safe notebook code
            detail = client.get(f"/api/previews/{preview_id}").json()
            self.assertIn("notebook", detail)
            self.assertIn("binary", detail["notebook"])
            self.assertEqual(client.get("/api/previews/missing/download").status_code, 404)

            # Submit with Web UI payload shape (without 'template' key) succeeds
            sub_res = client.post("/api/submissions", json={"preview_id": preview_id, "options": ui_options})
            self.assertEqual(sub_res.status_code, 200)
            sub_op_id = sub_res.json()["operation_id"]

            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                ops = {o["id"]: o for o in client.get("/api/operations").json()}
                if ops[sub_op_id]["state"] == "succeeded":
                    break
                time.sleep(0.05)
            self.assertEqual(ops[sub_op_id]["state"], "succeeded")

            # Force operation into 'unknown' state to verify reconcile + resolve endpoints
            self.store.finish(sub_op_id, error="Dispatch outcome unknown", state="unknown")
            rec_res = client.post(f"/api/operations/{sub_op_id}/reconcile")
            self.assertEqual(rec_res.status_code, 200)

            res_resolve = client.post(f"/api/operations/{sub_op_id}/resolve", json={
                "accepted": True,
                "evidence": "Verified remote kernel version matches preview digest",
                "remote_version": "v2",
            })
            self.assertEqual(res_resolve.status_code, 200)
            self.assertEqual(self.store.operation(sub_op_id)["state"], "succeeded")


if __name__ == "__main__":
    unittest.main()
