"""Import Kaggle and W&B accounts and notebooks from BHSD_SSL into ResearchPortal runtime store."""
import json
import os
from pathlib import Path

from research_portal.domain import PortalError
from research_portal.settings import load_settings
from research_portal.storage import Store


def setup_live_config():
    portal_root = Path(__file__).resolve().parents[1]
    config_file = portal_root / "config" / "settings.toml"
    runtime_dir = Path.home() / ".research_portal" / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(runtime_dir, 0o700)

    bhsd_dir = Path.home() / "BHSD_SSL"
    content = f"""[app]
mode = "live"
allow_live_submit = false
provider_timeout_seconds = 40
cooldown_seconds = 10
stale_seconds = 180
stall_seconds = 1200

[bhsd]
checkout = "{bhsd_dir}"
revision = "8d4a78e96400eb94d3c07fce810e495845df3783"

[runtime]
root = "{runtime_dir}"
local_filesystem_confirmed = true
"""
    config_file.write_text(content)
    os.chmod(config_file, 0o600)
    print(f"Configured {config_file} with runtime={runtime_dir} (mode=live)")
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
    default_acc_id = data.get("default_account", "1")
    kaggle_acc_map = {}

    for acc_id, acc_info in kaggle_accounts.items():
        slug = acc_info.get("slug")
        username = acc_info.get("username")
        key = acc_info.get("key", "")
        name = acc_info.get("name", f"Kaggle {slug}")
        desc = acc_info.get("description", "")
        is_default = (acc_id == default_acc_id or slug == "thanh")

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
        kaggle_acc_map[acc_id] = saved
        print(f"Saved Kaggle account: {saved['name']} ({username}) [ID: {saved['id']}]")

    # 3. Import notebooks from notebooks.json
    notebooks_file = bhsd_root / "configs" / "kaggle" / "notebooks.json"
    if notebooks_file.is_file():
        nb_data = json.loads(notebooks_file.read_text()).get("notebooks", {})
        default_kaggle = kaggle_acc_map.get(default_acc_id) or list(kaggle_acc_map.values())[0]
        attached_kernels = {n["kernel"] for n in store.notebooks()}

        for nb_key, nb_info in nb_data.items():
            slug = nb_info.get("slug")
            kernel_ref = f"{default_kaggle['principal']}/{slug}"
            if kernel_ref not in attached_kernels:
                store.attach(
                    account_id=default_kaggle["id"],
                    kernel=kernel_ref,
                    wandb_account_id=wandb_account_id,
                    run_ref=f"{wandb_principal}/PICK_BHSD/{slug}" if wandb_account_id else "",
                )
                print(f"Attached notebook: {kernel_ref}")
            else:
                print(f"Notebook already attached: {kernel_ref}")

    print("\n✅ Hoàn tất import tài khoản vào Store LIVE của ResearchPortal!")
    print(f"Vị trí cơ sở dữ liệu: {settings.runtime / 'storage.db'}")
    print(f"Vị trí secrets an toàn (chmod 0600): {settings.runtime / 'secrets'}")


if __name__ == "__main__":
    import_accounts()

