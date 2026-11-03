#!/usr/bin/env bash
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

# Kích hoạt virtualenv Python 3.11
if [ -d "$REPO_DIR/.venv" ]; then
    source "$REPO_DIR/.venv/bin/activate"
else
    echo "⚠️  Chưa tìm thấy .venv. Vui lòng tạo virtualenv trước."
    exit 1
fi

PORT="${PORT:-8080}"
HOST="${HOST:-127.0.0.1}"

if [ "$1" == "--streamlit" ]; then
    echo "=================================================="
    echo "🚀 Đang khởi động ResearchPortal (Chế độ Streamlit cũ)..."
    echo "=================================================="
    python -m research_portal.worker &
    WORKER_PID=$!
    trap 'kill $WORKER_PID 2>/dev/null || true; exit 0' SIGINT SIGTERM EXIT
    python -m streamlit run app.py --server.address=127.0.0.1 --server.port=8501
else
    echo "=================================================="
    echo "🚀 Khởi động ResearchPortal Web Service (FastAPI + Modern Web UI)"
    echo "🌐 Truy cập Dashboard tại: http://$HOST:$PORT"
    echo "📚 Swagger API Docs tại:   http://$HOST:$PORT/docs"
    echo "=================================================="
    exec python -m uvicorn server:app --host "$HOST" --port "$PORT" --reload
fi
