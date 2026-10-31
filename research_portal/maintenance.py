"""Operator-only backup, restore, diagnosis and secret cleanup. No provider calls."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from contextlib import contextmanager

from .domain import PortalError, canonical
from .providers import capabilities
from .settings import REPO, load_settings
from .storage import Store


@contextmanager
def offline_lock(root):
    with open(Path(root) / "worker.lock", "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise PortalError("Stop the worker before maintenance") from None
        yield


def private_copy(source, target):
    if source.is_symlink():
        raise PortalError("Symlinks are not allowed in backups")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    shutil.copyfile(source, target)
    target.chmod(0o600)


def backup(store, destination):
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_relative_to(REPO) or destination.is_relative_to(store.root):
        raise PortalError("Backup destination must be new and outside source/runtime")
    with offline_lock(store.root):
        destination.mkdir(mode=0o700, parents=True)
        with sqlite3.connect(store.path) as source, sqlite3.connect(destination / "portal.sqlite3") as target:
            source.backup(target)
        (destination / "portal.sqlite3").chmod(0o600)
        with sqlite3.connect(destination / "portal.sqlite3") as db:
            refs = db.execute("SELECT secret_ref FROM accounts WHERE secret_ref IS NOT NULL").fetchall()
            previews = db.execute("SELECT id FROM previews").fetchall()
        for (ref,) in refs:
            private_copy(store.root / "secrets" / ref, destination / "secrets" / ref)
        for (preview_id,) in previews:
            for name in ("notebook.ipynb", "kernel-metadata.json"):
                private_copy(store.root / "previews" / preview_id / name, destination / "previews" / preview_id / name)
        manifest = {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in destination.rglob("*") if p.is_file()}
        (destination / "backup-manifest.json").write_text(canonical(manifest))
        (destination / "backup-manifest.json").chmod(0o600)


def restore(source, destination):
    source, destination = Path(source).resolve(), Path(destination).absolute()
    if destination.exists() or destination.is_relative_to(REPO):
        raise PortalError("Restore requires a new runtime outside the checkout")
    manifest = json.loads((source / "backup-manifest.json").read_text())
    if "portal.sqlite3" not in manifest:
        raise PortalError("Backup database is missing")
    for name, expected in manifest.items():
        path = source / name
        if Path(name).is_absolute() or ".." in Path(name).parts or path.is_symlink() or not path.resolve().is_relative_to(source):
            raise PortalError("Unsafe backup path")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise PortalError("Backup checksum mismatch")
    destination.mkdir(mode=0o700, parents=True)
    for name in manifest:
        private_copy(source / name, destination / name)
    # Recovering a previously dispatched operation must never resume a push.
    store = Store(destination)
    with offline_lock(destination):
        for mode in ("fixture", "live"):
            store.mode = mode
            store.recover()
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["doctor", "backup", "restore", "cleanup-secrets"])
    parser.add_argument("path", nargs="?")
    args = parser.parse_args()
    if args.command == "doctor":
        print(json.dumps({"python": sys.version.split()[0], **capabilities()}, indent=2))
        return
    settings = load_settings()
    if args.command == "restore":
        if not args.path:
            parser.error("restore requires a backup directory")
        restore(args.path, settings.runtime)
        return
    store = Store(settings.runtime, settings.mode)
    if args.command == "backup":
        if not args.path:
            parser.error("backup requires a destination directory")
        backup(store, args.path)
    else:
        with offline_lock(store.root):
            store.cleanup_secrets()


if __name__ == "__main__":
    main()
