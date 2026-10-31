# Implementation handoff

## Delivery order

| Increment | Deliverable | Validation |
|---|---|---|
| P0 | Streamlit entrypoint, settings loader, typed adapter result, fixture mode | Starts without credential/GPU/network; demo labeled |
| P1 | Account selection/test, Kaggle status/log availability, W&B config/summary/progress | Isolated identities, manual refresh, timestamps and source-specific errors |
| P2 | Account editor and private runtime storage | Secret write-only, optimistic revision, no global fallback |
| P3 | Options form and safe bundle preview | Match current CLI flags and actual generated metadata; no push |
| P4 | Submit operation ledger and monitor integration | Double-click/restart safety, ambiguous timeout reconciliation |
| Expansion | Incremental sync, output/media/artifact browser, registry; managed hosting if chosen | Follow operations/capability specs, same provenance/security contracts |

Start with app.py and adapters; shared storage helpers may be added as needed. requirements-poc.in is an input inventory only: resolve compatible versions and create a tested lockfile during implementation. Do not install BHSD requirements to run a basic UI.

## BHSD integration inventory

Read the configurable source checkout at its supported revision. Consult:

- tools/kaggle/accounts_manager.py: legacy account lookup/import semantics; replace plaintext storage/global fallback in web flow.
- tools/kaggle/kaggle_executor.py: account-scoped CLI execution, status/log/push; normalize responses and avoid treating stderr as provider state.
- tools/kaggle/kaggle_ctl.py: actual build/push/status/log flags and defaults.
- tools/kaggle/notebook_builder.py and resume.py: templates/bundle/resume restrictions; isolate workspace and prevent credential injection into downloadable code.
- tools/crawl_run.py, crawl_kaggle.py, crawl_storage.py, fetch_wandb.py, export_wandb_history.py: observations/export references, not a durable multi-user backend.
- configs/kaggle/notebooks.json, scripts/ notebook templates, core/config_parser.py: keep together with BHSD revision.

Do not execute CLI account creation just to import its implementation: imports/constructors may create files. Use synthetic fixtures for first integration tests. Respect the source checkout's own instructions before editing it.

## Runtime and hosting

settings.example.toml is a proposed schema, not a functioning loader. Create a user-owned runtime directory outside checkout for metadata/private secrets/cache and operation ledger; confirm local filesystem semantics for SQLite. Live credentials are supplied separately by the operator. Paths and cloud hosting are configurable, not inferred from this seed.

The full-platform folder tree and free managed options are deployment alternatives. First prove adapters/read-only UI. A complete authorized task continues through requested increments; it does not require creating every researched service. Source links in reference guides may point to the original BHSD checkout and require updating when relocated.
