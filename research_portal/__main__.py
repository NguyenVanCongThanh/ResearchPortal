"""Main executable entrypoint for research_portal module.

Usage:
    python -m research_portal [--dev] [--host HOST] [--port PORT]
"""
import argparse
import uvicorn

from .settings import load_settings


def main():
    parser = argparse.ArgumentParser(description="ResearchPortal Control Plane")
    parser.add_argument("--dev", action="store_true", help="Run with auto-reload enabled")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Bind port (default: 8080)")

    args = parser.parse_args()

    settings = load_settings()
    uvicorn.run("server:app", host=args.host, port=args.port, reload=args.dev)


if __name__ == "__main__":
    main()
