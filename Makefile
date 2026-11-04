.PHONY: help run dev streamlit frontend-dev build-frontend test doctor verify clean

PYTHON := .venv/bin/python
PYTEST := .venv/bin/pytest

help:
	@echo "ResearchPortal - Command Center"
	@echo "==============================="
	@echo "  make run             Khởi động Web Service (FastAPI + React Web UI)"
	@echo "  make dev             Khởi động Web Service chế độ Dev (--reload)"
	@echo "  make streamlit       Khởi động chế độ Streamlit cũ (app.py + worker)"
	@echo "  make frontend-dev    Khởi động Vite HMR Dev Server (http://localhost:3000)"
	@echo "  make build-frontend  Build Frontend React sang thư mục static/"
	@echo "  make test            Chạy toàn bộ 61 unit/integration/UI tests"
	@echo "  make doctor          Kiểm tra tính toàn vẹn hệ thống & runtime"
	@echo "  make verify          Xác minh môi trường, pip check & cập nhật requirements.lock"
	@echo "  make clean           Dọn dẹp cache và build artifacts"

run:
	./run.sh

dev:
	./run.sh --dev

streamlit:
	./run.sh --streamlit

frontend-dev:
	./run.sh --frontend-dev

build-frontend:
	./run.sh --build-frontend

test:
	$(PYTEST) -q

doctor:
	$(PYTHON) -m research_portal.maintenance doctor

verify:
	$(PYTHON) tools/verify_environment.py

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	rm -rf frontend/tsconfig.tsbuildinfo

