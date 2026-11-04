# ResearchPortal Architecture Specification (v2.0)

## 1. Overview & System Topology

ResearchPortal is an operator-focused control plane and session manager designed for Kaggle notebooks and Weights & Biases telemetry tracking. It serves as an isolated bridge between local research workflows (e.g., BHSD) and remote execution providers.

The platform provides a modern single-page application (SPA) built on **React 19 + TypeScript + TailwindCSS** served via **FastAPI** (`server.py` or `./run.sh`).

```
+-------------------------------------------------------------------------+
|                              Client Layer                               |
|   +-----------------------------------------------------------------+   |
|   |  React 19 SPA (Vite / TailwindCSS / Lucide / TanStack Query)   |   |
|   |  http://127.0.0.1:8080                                          |   |
|   +--------------------------------+--------------------------------+   |
+------------------------------------|------------------------------------+
                                     | REST API (/api/*)
+------------------------------------v------------------------------------+
|                              Service Layer                              |
|   FastAPI Application Factory (`research_portal.web / api.py`)           |
|     ├── routes/system.py       (Status & capabilities)                  |
|     ├── routes/accounts.py     (Credential & profile management)        |
|     ├── routes/notebooks.py    (Monitor & logs telemetry)               |
|     ├── routes/previews.py     (Build bundle generation & downloads)    |
|     └── routes/operations.py   (Idempotent ledger & operator resolution)|
|                                                                         |
|   Portal Service Coordinator (`research_portal.service.Service`)        |
|     ├── Operation Ledger & Fencing Guard (`Store.enqueue / claim`)      |
|     ├── Health Evaluator (`monitor_health`)                             |
|     └── In-Process / CLI Worker (`worker.lock` flock single owner)      |
+---------------------+----------------------------------+----------------+
                      |                                  |
+---------------------v------------------+  +------------v----------------+
|          Persistence & Runtime         |  |      External Providers     |
|   SQLite Ledger (outside git)          |  |   Isolated Subprocesses     |
|   Encrypted Credentials Storage        |  |     ├── Kaggle CLI Adapter  |
|   Preview Bundles Directory            |  |     ├── W&B SDK Adapter     |
|   Worker Heartbeat & Mutex             |  |     └── Synthetic Fixtures  |
+----------------------------------------+  +-----------------------------+
```

## 2. Directory Structure Conventions

The repository is organized following clean separation of concerns:

- `frontend/`: Standalone Vite project for the React 19 UI.
  - `src/features/monitor/`: Live notebook status cards, charts, and attach workflow.
  - `src/features/accounts/`: Connection profiles (Kaggle/W&B credentials).
  - `src/features/build/`: Hyperparameter studio, bundle preview generation, and submit.
  - `src/features/operations/`: Operation queue, audit history, and ambiguity reconciliation.
- `static/`: Production build artifacts of the frontend (`index.html` + `assets/`), served by FastAPI.
- `research_portal/`: Python backend and worker package.
  - `routes/`: Modular FastAPI routers partitioned by resource domain.
  - `domain.py`: Typed data transfer models and validation schemas.
  - `storage.py`: SQLite repository, secret isolation, and filesystem mutexes.
  - `providers.py`: Provider bridge and synthetic fixture dispatch.
  - `provider_child.py`: Subprocess execution sandbox preventing environment contamination.
  - `builder.py`: BHSD bundle assembly and notebook compilation.
  - `worker.py`: Background worker consuming queued ledger operations.
  - `maintenance.py`: Administrative tasks (doctor, backup, restore, secret cleanup).
- `tests/`: 61 unit, integration, and UI tests validating contracts offline.
- `Makefile`: Standard developer command center (`make run`, `make dev`, `make test`, `make build-frontend`).

## 3. Concurrency & Security Model

- **Credential Redaction:** API keys are never rendered in logs, UI responses, or downloadable bundles.
- **Flock Concurrency:** Background operations use an OS-level file lock (`worker.lock`) ensuring strictly one worker consumes the queue.
- **Subprocess Isolation:** Provider commands run with sanitized environment variables; no credentials or host proxy configurations leak.
- **Fail-Safe Dispatch:** Ambiguous network timeouts hold the target lock until an operator verifies remote status and records explicit evidence.

