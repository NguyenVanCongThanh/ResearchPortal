"""Run with: python -m streamlit run app.py"""
import json

import streamlit as st

from research_portal.builder import download_bundle, validated_bundle
from research_portal.domain import BuildOptions, PortalError
from research_portal.providers import capabilities
from research_portal.service import Service, monitor_health
from research_portal.settings import load_settings
from research_portal.storage import Store, uid


def guard(action):
    try:
        return action()
    except PortalError as exc:
        st.error(str(exc))
    except Exception:
        st.error("Local operation failed. Check runtime permissions and configuration; no credentials are displayed.")
    return None


def seed_demo(store):
    if store.mode != "fixture" or store.rows("SELECT id FROM accounts WHERE mode='fixture' LIMIT 1"):
        return
    account = store.save_account(provider="kaggle", name="Demo Kaggle", slug="demo-kaggle", principal="demo-owner", is_default=True)
    tracking = store.save_account(provider="wandb", name="Demo W&B", slug="demo-wandb", principal="demo-team")
    store.attach(account["id"], "demo-owner/running", tracking["id"], "demo-team/demo-project/default")


def account_ui(store, service):
    accounts = store.accounts()
    mapping = {a["id"]: a for a in accounts}
    st.subheader("Connections")
    st.caption("Kaggle: legacy username/API key only. W&B: explicit API key and entity. Tokens/OAuth are not supported in v1.")
    if accounts:
        st.dataframe([{k: a[k] for k in ("name", "provider", "principal", "enabled", "configured", "revision", "tested_at", "test_result")}
                      for a in accounts], use_container_width=True)
    selected = st.selectbox("Edit connection", ["new"] + list(mapping), format_func=lambda k: "New connection" if k == "new" else mapping[k]["name"])
    if st.session_state.get("editing_id") != selected:
        st.session_state["editing_id"] = selected
        st.session_state["editing_snapshot"] = mapping.get(selected, {}).copy()
    if st.button("Reload connection metadata"):
        st.session_state["editing_snapshot"] = mapping.get(selected, {}).copy()
        st.rerun()
    old = st.session_state["editing_snapshot"]
    with st.form("account_" + selected, clear_on_submit=True):
        provider = st.selectbox("Provider", ["kaggle", "wandb"], index=0 if old.get("provider", "kaggle") == "kaggle" else 1, disabled=bool(old))
        name = st.text_input("Display name", value=old.get("name", ""))
        slug = st.text_input("Profile slug", value=old.get("slug", ""))
        principal = st.text_input("Username / W&B entity", value=old.get("principal", ""))
        description = st.text_area("Description", value=old.get("description", ""))
        secret = st.text_input("New credential (blank preserves existing credential)", type="password")
        enabled = st.checkbox("Enabled", value=bool(old.get("enabled", True)))
        default = st.checkbox("Default for this provider", value=bool(old.get("is_default", False)))
        if old:
            st.caption(f"Editing revision {old['revision']}; rotated {old.get('rotated_at') or 'never'}")
        save = st.form_submit_button("Save connection")
    if save:
        saved = guard(lambda: store.save_account(provider=provider, name=name, slug=slug, principal=principal,
                    description=description, enabled=enabled, is_default=default, secret=secret,
                    account_id=old.get("id"), revision=old.get("revision")))
        if saved:
            st.session_state["editing_snapshot"] = saved
            st.success("Saved. Credential verification is a separate operation.")
    if selected != "new":
        if st.button("Test selected connection"):
            op = guard(lambda: service.test_connection(selected))
            if op:
                st.success("Queued: " + op)
        if st.button("Archive selected connection"):
            guard(lambda: store.archive_account(selected, old["revision"]))
            st.info("Connection archived; references and cached history are preserved. Reload to update the list.")
    with st.expander("Local capability inventory"):
        st.json(capabilities())


def monitor_ui(settings, store, service):
    st.subheader("Notebook monitor")
    kaggle = {a["id"]: a for a in store.accounts("kaggle") if a["enabled"]}
    wandb = {a["id"]: a for a in store.accounts("wandb") if a["enabled"]}
    if kaggle:
        with st.form("attach"):
            account_id = st.selectbox("Kaggle observation connection", list(kaggle), format_func=lambda k: kaggle[k]["name"])
            kernel = st.text_input("Kaggle owner/slug")
            wandb_id = st.selectbox("W&B connection (optional)", [""] + list(wandb), format_func=lambda k: wandb[k]["name"] if k else "None")
            run = st.text_input("W&B entity/project/run-id (optional)")
            new_attempt = st.checkbox("Attach as a new attempt (for a new run/version on an existing slug)")
            attach = st.form_submit_button("Attach notebook")
        if attach and guard(lambda: store.attach(account_id, kernel, wandb_id or None, run, attempt_id=uid() if new_attempt else None)):
            st.success("Notebook attached")
    else:
        st.info("Add an enabled Kaggle connection first.")
    for notebook in store.notebooks():
        with st.expander(notebook["kernel"], expanded=True):
            st.caption(f"Attempt: {notebook['attempt_id'] or 'attached / latest version unverified'} · connection: {store.account(notebook['account_id'])['name']}")
            st.link_button("Open Kaggle notebook", "https://www.kaggle.com/code/" + notebook["kernel"])
            if notebook["run_ref"]:
                st.link_button("Open W&B run", "https://wandb.ai/" + notebook["run_ref"])
            if notebook["attempt_id"]:
                attempts = store.rows("SELECT result FROM operations WHERE id=? AND mode=?", (notebook["attempt_id"], store.mode))
                result = json.loads(attempts[0]["result"]) if attempts and attempts[0]["result"] else {}
                version = result.get("provider", {}).get("remote_version") or result.get("remote_version")
                st.caption("Submitted version: " + (str(version) if version else "unverified") + "; status below refers to latest slug/version unless verified separately.")
            if st.button("Check now", key="check_" + notebook["id"]):
                ids = guard(lambda: service.check(notebook["id"]))
                if ids:
                    st.success("Requested; queued/recent operations are reused. Refresh stored results after the worker completes.")
                else:
                    st.info("No enabled connections; displaying cache.")
            k = store.observations(notebook["id"], "kaggle")
            w = store.observations(notebook["id"], "wandb")
            health = monitor_health(k, w, stall_seconds=settings.stall_seconds, stale_seconds=settings.stale_seconds)
            st.json(health)
            for label, observations in (("Kaggle", k), ("W&B", w)):
                st.markdown("**" + label + "**")
                if not observations:
                    st.caption("Unavailable — no observation fetched yet")
                    continue
                latest = observations[0]
                st.caption(f"Fetched: {latest['fetched_at']} · source: {latest['source']} · version: {latest.get('remote_version') or 'unverified'}")
                if latest.get("error"):
                    st.warning("Last check: " + latest["error"] + "; cached provider state is preserved.")
                good = next((o for o in observations if not o.get("error")), None)
                if good:
                    st.json(good)
                    logs_info = good["data"].get("logs", {})
                    log_text = logs_info.get("text", "")
                    log_prog = logs_info.get("progress", {})
                    if log_prog:
                        cols = st.columns(4)
                        if log_prog.get("epoch"):
                            cols[0].metric("Epoch (Logs)", str(log_prog["epoch"]))
                        if log_prog.get("iteration") is not None:
                            cols[1].metric("Iteration (Logs)", str(log_prog["iteration"]))
                        if log_prog.get("loss") is not None:
                            cols[2].metric("Loss (Logs)", f"{log_prog['loss']:.4f}")
                        if log_prog.get("recent_line"):
                            st.caption(f"Latest log line: `{log_prog['recent_line']}`")
                    if log_text:
                        source_label = logs_info.get("source", "cli_kernels_logs")
                        with st.expander(f"Kaggle Execution Logs ({len(log_text.splitlines())} lines · {source_label})", expanded=False):
                            if logs_info.get("truncated"):
                                st.caption("Log output truncated to latest 64KB for safety.")
                            st.code(log_text, language=None)


def submit_ui(settings, store, service):
    st.subheader("Build → Preview → Submit")
    st.caption("Mean Teacher only. PICK, arbitrary extra flags, quota and log-follow are unsupported.")
    accounts = {a["id"]: a for a in store.accounts("kaggle") if a["enabled"]}
    if not accounts:
        st.info("Add an enabled Kaggle connection to build a preview.")
        return
    account_ids = list(accounts)
    default_index = next((i for i, k in enumerate(account_ids) if accounts[k]["is_default"]), 0)
    account_id = st.selectbox("Target account", account_ids, index=default_index,
                              format_func=lambda k: accounts[k]["name"], key="submit_account")
    task = st.selectbox("Task", ["multiclass", "binary"])
    slug = st.text_input("Kernel slug override")
    title = st.text_input("Title override")
    dataset = st.text_input("Dataset owner/slug override (one source)")
    gpu = st.checkbox("Enable GPU", value=True)
    tracking = st.selectbox("Notebook tracking", ["offline", "kaggle_secrets"])
    st.caption("Kaggle Secrets mode requires WANDB_API_KEY attached to the notebook on Kaggle. Portal W&B connections are used for monitoring, not embedded into notebooks.")
    resume = st.checkbox("Resume Mean Teacher")
    run = st.text_input("Resume source entity/project/run-id", disabled=not resume)
    mode = st.selectbox("Resume tracking", ["same-run", "new-run"], disabled=not resume)
    checkpoint = st.selectbox("Checkpoint policy", ["latest", "best"], disabled=not resume)
    options = BuildOptions(task=task, slug=slug, title=title, dataset=dataset, gpu=gpu, tracking=tracking,
                           resume_run=run if resume else "", resume_mode=mode if resume else "", checkpoint=checkpoint if resume else "").payload()
    if st.button("Build preview"):
        op = guard(lambda: service.request_build(account_id, options))
        if op:
            st.success("Build queued: " + op)
    previews = [p for p in store.previews() if p["account_id"] == account_id]
    if not previews:
        st.info("No completed previews for this account. Run the worker and refresh stored results.")
        return
    preview_id = st.selectbox("Completed preview", [p["id"] for p in previews])
    preview = store.preview(preview_id)
    st.json(preview["manifest"])
    if preview["options"] != options:
        st.warning("Current options differ from this preview. Build again before submitting.")
    data = guard(lambda: download_bundle(store, preview))
    if data:
        with st.expander("Safe notebook preview"):
            notebook = guard(lambda: (validated_bundle(store, preview) / "notebook.ipynb").read_text())
            if notebook:
                st.code(notebook, language="json")
        st.download_button("Download safe bundle", data=data, file_name="research-portal-preview.zip", mime="application/zip")
    if settings.mode == "live" and not settings.allow_live_submit:
        st.info("Live submit is disabled. Enable it in settings only after reviewing the preview and offline checks.")
    confirmed = st.checkbox("I reviewed the target account, datasets, source revision and GPU/tracking options")
    allowed = settings.mode == "fixture" or settings.allow_live_submit
    if st.button("Simulate submit" if settings.mode == "fixture" else "Submit to Kaggle", disabled=not (confirmed and allowed)):
        op = guard(lambda: service.request_submit(preview_id, options, "submit:" + preview_id))
        if op:
            st.success("Submission operation: " + op)


def operations_ui(store, service):
    st.subheader("Operations")
    st.caption("Accepted submission, notebook running and successful training are separate outcomes.")
    operations = store.operations()
    st.dataframe([{k: o[k] for k in ("id", "kind", "target", "state", "created_at", "updated_at", "error")} for o in operations], use_container_width=True)
    for op in operations:
        with st.expander(op["kind"] + " · " + op["id"] + " · " + op["state"]):
            if op["result"]:
                st.json(json.loads(op["result"]))
            if op["kind"] == "submit" and op["state"] in ("unknown", "reconciling"):
                st.warning("Do not retry push. Inspect the remote version and record evidence before releasing this target.")
                if st.button("Read remote reconciliation evidence", key="reconcile_" + op["id"]):
                    guard(lambda: store.enqueue("reconcile", {"operation_id": op["id"]}, op["account_id"], op["target"], cooldown=10))
                with st.form("resolve_" + op["id"]):
                    accepted = st.selectbox("Operator finding", ["accepted", "not_sent"], key="finding_" + op["id"])
                    version = st.text_input("Observed remote version", key="version_" + op["id"])
                    evidence = st.text_area("Evidence (no tokens or signed URLs)", key="evidence_" + op["id"])
                    verified = st.checkbox("I checked the remote version against this preview", key="verified_" + op["id"])
                    resolve = st.form_submit_button("Record operator resolution", disabled=not verified)
                if resolve:
                    guard(lambda: service.resolve_unknown(op["id"], accepted == "accepted", evidence, version))


def main():
    st.set_page_config(page_title="ResearchPortal", layout="wide")
    st.title("ResearchPortal")
    settings = guard(load_settings)
    if settings is None:
        st.stop()
    store = guard(lambda: Store(settings.runtime, settings.mode))
    if store is None:
        st.stop()
    guard(lambda: seed_demo(store))
    service = Service(settings, store)
    if settings.mode == "fixture":
        st.warning("FIXTURE / DEMO — synthetic data, no provider calls or live training")
    else:
        st.info("LIVE — calls occur only for explicitly queued operations")
    st.caption("Worker: " + ("online" if store.worker_online() else "offline — start python -m research_portal.worker"))
    st.button("Refresh stored results")
    tabs = st.tabs(["Accounts", "Monitor", "Submit", "Operations"])
    with tabs[0]:
        account_ui(store, service)
    with tabs[1]:
        monitor_ui(settings, store, service)
    with tabs[2]:
        submit_ui(settings, store, service)
    with tabs[3]:
        operations_ui(store, service)


if __name__ == "__main__":
    main()
