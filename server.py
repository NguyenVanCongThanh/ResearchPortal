"""FastAPI application entrypoint for ResearchPortal.

Run with:
    python -m uvicorn server:app --host 127.0.0.1 --port 8000 --reload
"""
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from research_portal.api import create_app
from research_portal.settings import load_settings

settings = load_settings()
app = create_app(settings)

# Ensure index.html fallback
static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    @app.get("/{full_path:path}")
    async def catch_all(full_path: str):
        # Don't intercept API or static routes
        if full_path.startswith("api/") or full_path.startswith("static/") or full_path.startswith("docs") or full_path.startswith("openapi.json"):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not Found")
        file_target = static_dir / full_path
        if file_target.is_file():
            return FileResponse(file_target)
        return FileResponse(static_dir / "index.html")

