"""Import Kaggle and W&B accounts and notebooks from BHSD_SSL into ResearchPortal runtime store."""
import json
import os
from pathlib import Path
import subprocess

from research_portal.settings import load_settings
from research_portal.storage import Store

DEFAULT_REVISION = "e5b3cbf4479c575d088f9836a059055c7badd8d9"


def resolve_bhsd_revision(bhsd_dir: Path) -> str:
    try:
        res = subprocess.run(["git", "-C", str(bhsd_dir), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=10, check=True)
        rev = res.stdout.strip()
        if len(rev) == 40:
            return rev
    except Exception:
        pass
    return DEFAULT_REVISION


def setup_live_config():
    portal_root = Path(__file__).resolve().parents[1]
    config_file = portal_root / "config" / "settings.toml"
    runtime_dir = Path.home() / ".research_portal" / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(runtime_dir, 0o700)

    bhsd_dir = Path.home() / "BHSD_SSL"
    revision = resolve_bhsd_revision(bhsd_dir)
    content = f"""[app]
mode = "live"
allow_live_submit = false
provider_timeout_seconds = 40
cooldown_seconds = 10
stale_seconds = 180
stall_seconds = 1200

[bhsd]
checkout = "{bhsd_dir}"
revision = "{revision}"

[runtime]
root = "{runtime_dir}"
local_filesystem_confirmed = true
"""
    config_file.write_text(content)
    os.chmod(config_file, 0o600)
    print(f"Configured {config_file} with runtime={runtime_dir} (mode=live, revision={revision[:12]})")
    return runtime_dir


def import_accounts():
    setup_live_config()
    settings = load_settings()
    store = Store(settings.runtime, settings.mode)

    bhsd_root = Path(settings.bhsd)
    accounts_file = bhsd_root / "configs" / "kaggle" / "accounts.json"
    if not accounts_file.is_file():
        raise FileNotFoundError(f"Accounts file not found at {accounts_file}")

    data = json.loads(accounts_file.read_text())
    existing = {a["slug"]: a for a in store.accounts()}

    # 1. Import W&B account if available
    wandb_key = data.get("default_wandb_key", "")
    wandb_account_id = None
    wandb_principal = "thanhnguyen2005243-ho-chi-minh-city-university-of-technology"
    if wandb_key:
        wandb_slug = "thanh-wandb"
        old = existing.get(wandb_slug)
        saved = store.save_account(
            provider="wandb",
            name="Thành Nguyễn (W&B)",
            slug=wandb_slug,
            principal=wandb_principal,
            description="W&B experiment tracking for MedSSL-BHSD",
            enabled=True,
            is_default=True,
            secret=wandb_key,
            account_id=old["id"] if old else None,
            revision=old["revision"] if old else None,
        )
        wandb_account_id = saved["id"]
        print(f"Saved W&B account: {saved['name']} ({wandb_principal}) [ID: {saved['id']}]")

    # 2. Import Kaggle accounts
    kaggle_accounts = data.get("accounts", {})
    default_acc_id = str(data.get("default_account", "1"))
    kaggle_acc_map = {}

    for acc_id, acc_info in kaggle_accounts.items():
        slug = acc_info.get("slug")
        username = acc_info.get("username")
        key = acc_info.get("key", "")
        name = acc_info.get("name", f"Kaggle {slug}")
        desc = acc_info.get("description", "")
        is_default = str(acc_id) == default_acc_id

        old = existing.get(slug)
        saved = store.save_account(
            provider="kaggle",
            name=name,
            slug=slug,
            principal=username,
            description=desc,
            enabled=True,
            is_default=is_default,
            secret=key,
            account_id=old["id"] if old else None,
            revision=old["revision"] if old else None,
        )
        kaggle_acc_map[str(acc_id)] = saved
        print(f"Saved Kaggle account: {saved['name']} ({username}) [ID: {saved['id']}]")

    # 3. Import notebooks from notebooks.json
    notebooks_file = bhsd_root / "configs" / "kaggle" / "notebooks.json"
    if notebooks_file.is_file() and kaggle_acc_map:
        nb_data = json.loads(notebooks_file.read_text()).get("notebooks", {})
        default_kaggle = kaggle_acc_map.get(default_acc_id) or next(iter(kaggle_acc_map.values()))
        attached_kernels = {n["kernel"] for n in store.notebooks()}

        for nb_key, nb_info in nb_data.items():
            slug = nb_info.get("slug")
            if not slug:
                continue
            kernel_ref = f"{default_kaggle['principal']}/{slug}"
            wandb_project = "BHSD_MeanTeacher" if nb_key == "mean_teacher" else "PICK_BHSD"
            if kernel_ref not in attached_kernels:
                store.attach(
                    account_id=default_kaggle["id"],
                    kernel=kernel_ref,
                    wandb_account_id=wandb_account_id,
                    run_ref=f"{wandb_principal}/{wandb_project}/{slug}" if wandb_account_id else "",
                )
                print(f"Attached notebook: {kernel_ref}")
            else:
                print(f"Notebook already attached: {kernel_ref}")

    print("\n✅ Hoàn tất import tài khoản vào Store LIVE của ResearchPortal!")
    print(f"Vị trí cơ sở dữ liệu: {settings.runtime / 'portal.sqlite3'}")
    print(f"Vị trí secrets an toàn (chmod 0600): {settings.runtime / 'secrets'}")


if __name__ == "__main__":
    import_accounts()
