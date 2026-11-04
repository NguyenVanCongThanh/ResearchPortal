"""FastAPI application entrypoint for ResearchPortal.

Run with:
    python -m uvicorn server:app --host 127.0.0.1 --port 8000
"""
from research_portal.api import create_app
from research_portal.settings import load_settings

settings = load_settings()
app = create_app(settings)
