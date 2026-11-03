"""API endpoint tests for FastAPI server using TestClient."""
from pathlib import Path
import tempfile
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

    def test_accounts_crud(self):
        # Create
        res = self.client.post("/api/accounts", json={
            "provider": "kaggle",
            "name": "Test Kaggle",
            "slug": "test-kaggle",
            "principal": "test-user",
            "secret": "test-key-123",
            "enabled": True,
            "is_default": True,
        })
        self.assertEqual(res.status_code, 200)
        acc = res.json()["account"]
        self.assertEqual(acc["name"], "Test Kaggle")

        # List
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

        # List notebooks
        res = self.client.get("/api/notebooks")
        self.assertEqual(res.status_code, 200)
        nbs = res.json()
        self.assertEqual(len(nbs), 1)
        self.assertEqual(nbs[0]["kernel"], "attach-principal/demo-run")

        # Check notebook
        res = self.client.post(f"/api/notebooks/{nb_id}/check")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])

        # Fetch logs
        res = self.client.get(f"/api/notebooks/{nb_id}/logs")
        self.assertEqual(res.status_code, 200)
        log_data = res.json()
        self.assertIn("availability", log_data)

    def test_previews_and_operations(self):
        acc = self.store.save_account(provider="kaggle", name="BuildTest", slug="build-test", principal="build-principal")
        options = BuildOptions(task="multiclass").payload()
        res = self.client.post("/api/previews", json={
            "account_id": acc["id"],
            "options": options,
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])

        # Check operations
        res = self.client.get("/api/operations")
        self.assertEqual(res.status_code, 200)
        ops = res.json()
        self.assertGreaterEqual(len(ops), 1)


if __name__ == "__main__":
    unittest.main()

