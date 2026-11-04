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
    echo "⚠️  Chế độ Streamlit cũ đã được loại bỏ."
    echo "💡 ResearchPortal hiện sử dụng FastAPI + Modern React Web UI."
    echo "👉 Vui lòng chạy './run.sh' hoặc 'make run' để truy cập Dashboard tại http://$HOST:$PORT"
    exit 1
elif [ "$1" == "--frontend-dev" ]; then
    echo "=================================================="
    echo "🚀 Khởi động Frontend Dev Server (Vite + React HMR)"
    echo "🌐 Truy cập Dev UI tại: http://localhost:3000"
    echo "🔗 Proxy sang API:     http://127.0.0.1:8080"
    echo "=================================================="
    export PATH="$HOME/.local/nodejs/bin:$PATH"
    cd "$REPO_DIR/frontend"
    exec npm run dev
elif [ "$1" == "--build-frontend" ]; then
    echo "=================================================="
    echo "📦 Đang build Frontend React 19 sang thư mục static/..."
    echo "=================================================="
    export PATH="$HOME/.local/nodejs/bin:$PATH"
    cd "$REPO_DIR/frontend"
    npm run build
    echo "✅ Build hoàn tất!"
    exit 0
elif [ "$1" == "--dev" ]; then
    echo "=================================================="
    echo "🚀 Khởi động ResearchPortal Web Service (Dev Reload Mode)"
    echo "🌐 Truy cập Dashboard tại: http://$HOST:$PORT"
    echo "📚 Swagger API Docs tại:   http://$HOST:$PORT/docs"
    echo "=================================================="
    exec python -m uvicorn server:app --host "$HOST" --port "$PORT" --reload
else
    echo "=================================================="
    echo "🚀 Khởi động ResearchPortal Web Service (FastAPI + Modern Web UI)"
    echo "🌐 Truy cập Dashboard tại: http://$HOST:$PORT"
    echo "📚 Swagger API Docs tại:   http://$HOST:$PORT/docs"
    echo "=================================================="
    exec python -m uvicorn server:app --host "$HOST" --port "$PORT"
fi
