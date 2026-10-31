"""Actual Streamlit rerun smoke checks, conditional on the UI dependency."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_portal.settings import load_settings
from research_portal.storage import Store
from research_portal.worker import process_one

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


@unittest.skipIf(AppTest is None, "Streamlit not installed; AppTest unavailable")
class UiTests(unittest.TestCase):
    def test_fixture_render_and_rerender_make_no_provider_calls(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {
            "RESEARCH_PORTAL_MODE": "fixture", "RESEARCH_PORTAL_RUNTIME": root,
            "RESEARCH_PORTAL_SETTINGS": str(Path(root) / "none.toml")
        }), patch("research_portal.providers.Providers.call", side_effect=AssertionError("Provider called during render")):
            app = AppTest.from_file("app.py").run(timeout=20)
            self.assertEqual(len(app.exception), 0)
            self.assertIn("ResearchPortal", app.title[0].value)
            app.run(timeout=20)
            self.assertEqual(len(app.exception), 0)

    def test_build_preview_and_simulated_submit_through_widgets(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {
            "RESEARCH_PORTAL_MODE": "fixture", "RESEARCH_PORTAL_RUNTIME": root,
            "RESEARCH_PORTAL_SETTINGS": str(Path(root) / "none.toml")
        }):
            app = AppTest.from_file("app.py").run(timeout=20)
            next(b for b in app.button if b.label == "Build preview").click().run(timeout=20)
            settings, store = load_settings(), Store(root)
            while process_one(settings, store, "ui-test"):
                pass
            app.run(timeout=20)
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(store.previews()), 1)
            next(c for c in app.checkbox if c.label.startswith("I reviewed the target")).check().run(timeout=20)
            next(b for b in app.button if b.label == "Simulate submit").click().run(timeout=20)
            while process_one(settings, store, "ui-test"):
                pass
            app.run(timeout=20)
            self.assertEqual(len(app.exception), 0)
            submits = [o for o in store.operations() if o["kind"] == "submit"]
            self.assertEqual(len(submits), 1)
            self.assertEqual(submits[0]["state"], "succeeded")
            self.assertIn("ResearchPortal", app.title[0].value)
            app.run(timeout=20)
            self.assertEqual(len(app.exception), 0)


if __name__ == "__main__":
    unittest.main()
