"""Explicit session worker: python -m research_portal.worker [--once]."""
import argparse
import fcntl
import os
import sqlite3
import threading
import time

from .domain import PortalError
from .service import Service
from .settings import load_settings
from .storage import Store, uid


def process_one(settings, store, worker_id, providers=None):
    operation = store.claim(worker_id)
    if not operation:
        return False
    try:
        result = Service(settings, store, providers).execute(operation)
        if store.operation(operation["id"])["state"] == "running":
            store.finish(operation["id"], result=result, error=result.get("error") if isinstance(result, dict) else None)
    except Exception as exc:
        # Raw SDK/subprocess exception messages are never persisted or shown.
        op = store.operation(operation["id"])
        message = str(exc) if isinstance(exc, PortalError) else "Operation failed; see offline compatibility checks"
        store.finish(op["id"], error=message, state="unknown" if op["kind"] == "submit" and op["dispatched_at"] else "failed")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Process at most one queued operation")
    args = parser.parse_args()
    settings = load_settings()
    store = Store(settings.runtime, settings.mode)
    with open(store.root / "worker.lock", "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("A worker already owns this runtime")
        store.recover()
        worker_id = uid()
        stopping = threading.Event()
        store.heartbeat()

        def heartbeat():
            while not stopping.wait(5):
                try:
                    store.heartbeat()
                except (sqlite3.Error, OSError):
                    pass  # A failed local heartbeat must not repeat a dispatch.

        ticker = threading.Thread(target=heartbeat, daemon=True)
        ticker.start()
        try:
            while True:
                store.heartbeat()
                worked = process_one(settings, store, worker_id)
                if args.once:
                    break
                if not worked:
                    time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            stopping.set()
            ticker.join(timeout=12)
            with store.tx() as db:
                db.execute("DELETE FROM worker WHERE mode=? AND pid=?", (settings.mode, os.getpid()))


if __name__ == "__main__":
    main()
