# ResearchPortal implementation instructions

- Read README.md, docs/design/poc-first.md, docs/design/kaggle-operations-spec.md and docs/design/provider-capabilities.md before implementation.
- User instructions take precedence. Default to the simple Streamlit/Python PoC profile. Do not provision cloud services or introduce React/FastAPI/Supabase/Trigger.dev just because they appear in design alternatives.
- For a full implementation request, deliver working increments in order: fixtures/read-only monitor, account UI, build preview, controlled submit, then broader registry/hosting as needed. PoC-first orders delivery; it is not a reason to stop a task explicitly authorizing the full scope.
- Long-term architecture docs are reference. Implement only relevant layers; avoid empty microservice scaffolding.
- BHSD checkout path is configurable. Keep training ownership there; do not copy its secret profiles, datasets, checkpoints, generated bundles or dependencies wholesale.
- Existing tools are CLI-oriented references, not concurrency-safe web adapters. Isolate subprocess environments and account credentials, use allowlisted argument lists, avoid shell=True and secrets in command args/logs.
- Runtime state and secrets live outside Git. Never expose credentials in UI responses, downloadable notebooks or fixtures. Metadata edit with an empty secret field preserves the existing secret.
- No provider calls at import/render time. Distinguish fixture/live data; use manual refresh and timestamps first. Provider status, tracking heartbeat and iteration progress are distinct signals.
- Before enabling submit, persist operations, protect against duplicate dispatch and reconcile ambiguous timeouts. Streamlit session state alone is insufficient. Do not launch live training without user authorization.
- Verify meaningful contracts using synthetic fixtures. Online checks need provisioned credentials and appropriate scope. Never describe fixture tests as online compatibility evidence.
- New repository is a seed, not a runnable app. Verify installed versions/provider capabilities when implementing. No Git initialization, remote publication or cloud resources are implied by this handoff.
