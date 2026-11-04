# Implementation status

Implementation follows PoC-first: one operator, session-based Streamlit and an explicit worker. This replaces the seed-only handoff; original design documents remain requirements/reference, not proof of online compatibility.

## Delivery status

| Increment | Implemented | Validation boundary |
|---|---|---|
| P0 | Fixture/live settings, Streamlit entrypoint, SQLite migrations, typed results, demo seed and worker | Core fixture workflows exercised offline; actual UI/AppTest awaits Streamlit installation |
| P1 | Explicit connections, connection test, notebook attachment, independent manual refresh jobs, status/log availability, bounded W&B config/summary/system/progress | Synthetic failures/isolation covered; authenticated endpoints have not been probed |
| P2 | Write-only account editor, optimistic revisions, rotation, defaults, disable/archive, private secret references | Storage contracts tested; UI interactions await AppTest |
| P3 | Mean Teacher task/options, safe immutable preview/download, pinned source export, isolated generator/config parser, resume injection | Actual baseline BHSD generator tested offline for multiclass/binary and resume; no notebook executed |
| P4 | Durable queue, unique idempotency, target lock, pre-dispatch fence, restart recovery, operator reconciliation, monitor attachment | Fake dispatch/timeout/crash contracts; no live submission or training |

## Runtime contracts

- Python 3.11; dependencies separate from BHSD training. Direct selected versions are in `requirements.txt`, test dependencies in `requirements-dev.txt`.
- Package installation from this execution environment failed with DNS/network errors. Python 3.11 was already present; PyYAML 6.0.3 was available from local cache. A fully resolved/tested lockfile cannot be produced here yet. `tools/verify_environment.py` produces it only after installed dependencies and tests pass.
- SQLite schema version 2 stores account metadata, immutable observations, persistent progress clocks, previews, operations and audit events. Live mode requires explicit confirmation of local filesystem semantics. Secret files are private and outside Git; orphan cleanup is offline maintenance.
- One worker owns a runtime via an exclusive process lock. UI queues jobs; rendering only reads local state. Timeout is 40 seconds for provider subprocesses, build timeout 60 seconds; manual reads have a 10-second cooldown. No scheduler or provider auto-polling.
- A successful account test means connectivity with the selected credential; provider principal ownership remains unverified when the endpoint cannot establish it.
- Health uses observed iteration increases with sample timestamps. Sampled W&B history is not an exact history export. Progress clocks survive subsequent unchanged observations. A connection error preserves previous provider state.
- The BHSD Mean Teacher logger explicitly records its training axis as `global_step`; the adapter recognizes this contract for that method. SDK `_step` and arbitrary phase-dependent `global_step` values are not treated as training iterations.
- Previews expire after 24 hours. Account revision, credential revision, source fingerprint, options and bundle bytes are checked before dispatch. Built notebook code checkouts are pinned to the training SHA.
- Binary mapping explicitly supplies `experiment.num_classes=2`: the baseline method YAML otherwise retains six classes. This is a portal bundle override; the BHSD checkout is not modified.
- Resume delegates to the pinned BHSD helper. Source run config and checkpoint selection are resolved on Kaggle, not claimed to be fully resolved in the local preview; the preview records this limitation. GPU/world-size and source-run checks run before training in that helper.
- Notebook online tracking requires an operator-attached Kaggle Secret `WANDB_API_KEY`. Private Git cloning, OAuth/access-token flows, PICK, quota and log-follow are unsupported in this version.
- Provider versions are gated against the selected baseline before live dispatch. Missing/incompatible dependencies fail before the dispatch fence. Read checks report unsupported dependencies explicitly.

## Offline verification in this workspace

Executed with Python 3.11.16 in `.venv`: `python -m pytest -q` (60 passed, 0 failed, 0 skipped) and `python tools/verify_environment.py` (all checks passed, generated `requirements.lock`). This includes actual BHSD generator/config compatibility for four task/resume combinations against commit `e5b3cbf4479c575d088f9836a059055c7badd8d9`, isolated account subprocess contracts, FastAPI + in-process worker end-to-end workflows, path traversal and CORS hardening, Streamlit `AppTest` widget workflows, training-axis mapping/progress persistence, idempotency, ambiguous dispatch recovery and backup/restore.

No live provider submission or notebook execution on cloud GPUs was performed during automated testing.

## Submission safety and recovery

Live submit is disabled by default. Enabling its configuration flag is an operator decision, not an action performed during implementation/testing. Provider push is invoked once without fallback; its SDK `timeout` argument is deliberately not used because it represents training session duration.

Before push, the worker persists a dispatch fence. Errors after this boundary retain `unknown` and the target lock, even if a local error might mean nothing was sent. Restart marks interrupted dispatches unknown and never retries them. Read-only reconciliation can collect current status but does not treat latest slug status as a version/digest match. Operators record remote-version evidence or confirm nothing was sent. Operator-reported evidence is distinguished from provider verification.

Source credentials are snapshotted for dispatch; rotation preserves old private files until offline cleanup. All retained credential values and prefixes are redacted from provider observations before persistence. Downloaded previews include no local secrets or provider workspaces.

## Remaining acceptance work

1. On a network-enabled development machine, install `requirements-dev.txt`, run `tools/verify_environment.py`, review and retain its generated lockfile.
2. Run Streamlit AppTest and manually exercise Accounts/Monitor/Submit using fixture mode. Validate actual browser layout and secret input clearing.
3. Provision connections and run authorized read probes against Kaggle/W&B. Verify auth/error classification, progress keys, SDK compatibility and the experimental bounded Kaggle output-log endpoint. Unsupported/missing data must remain explicit.
4. Verify local storage locking, backup/restore, source availability from Kaggle and Kaggle Secrets attachment. Only then authorize a controlled live submit separately if desired.

See the repository README for start/stop, configuration, backup/restore and recovery commands. Do not label the offline suite as online compatibility evidence.
