"""Private SQLite state, optimistic updates and durable dispatch fences."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
import random
from pathlib import Path
import sqlite3
import time
import uuid

from .domain import Conflict, PortalError, canonical, digest, now, reference


def uid():
    return uuid.uuid4().hex


class Store:
    def __init__(self, root, mode="fixture"):
        original = Path(root).absolute()
        if original.is_symlink():
            raise PortalError("Runtime cannot be a symlink")
        self.root = original.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.stat().st_uid != os.getuid():
            raise PortalError("Runtime must be owned by the current user")
        os.chmod(self.root, 0o700)
        self.mode = mode
        for name in ("secrets", "work", "previews"):
            p = self.root / name
            if p.is_symlink():
                raise PortalError("Runtime child cannot be a symlink")
            p.mkdir(mode=0o700, exist_ok=True)
            os.chmod(p, 0o700)
        self.path = self.root / "portal.sqlite3"
        if self.path.is_symlink():
            raise PortalError("Database cannot be a symlink")
        with self.tx() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 2:
                raise PortalError("Database schema is newer than this application")
            db.executescript("""
            CREATE TABLE IF NOT EXISTS accounts (
              id TEXT PRIMARY KEY, mode TEXT NOT NULL, provider TEXT NOT NULL,
              name TEXT NOT NULL, slug TEXT NOT NULL COLLATE NOCASE,
              principal TEXT NOT NULL, description TEXT NOT NULL, enabled INTEGER NOT NULL,
              is_default INTEGER NOT NULL, archived INTEGER NOT NULL DEFAULT 0,
              revision INTEGER NOT NULL, secret_ref TEXT, credential_revision INTEGER NOT NULL,
              rotated_at TEXT, tested_at TEXT, test_result TEXT,
              UNIQUE(mode, provider, slug));
            CREATE UNIQUE INDEX IF NOT EXISTS one_default
              ON accounts(mode, provider) WHERE is_default=1;
            CREATE TABLE IF NOT EXISTS notebooks (
              id TEXT PRIMARY KEY, mode TEXT NOT NULL, account_id TEXT NOT NULL REFERENCES accounts(id),
              kernel TEXT NOT NULL, wandb_account_id TEXT REFERENCES accounts(id), run_ref TEXT,
              attempt_id TEXT, created_at TEXT NOT NULL,
              UNIQUE(mode, account_id, kernel, attempt_id));
            CREATE TABLE IF NOT EXISTS observations (
              id INTEGER PRIMARY KEY, notebook_id TEXT NOT NULL REFERENCES notebooks(id),
              source TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS obs_lookup
              ON observations(notebook_id, source, id DESC);
            CREATE TABLE IF NOT EXISTS progress (
              notebook_id TEXT PRIMARY KEY REFERENCES notebooks(id), iteration REAL,
              sample_at TEXT, progress_at TEXT);
            CREATE TABLE IF NOT EXISTS previews (
              id TEXT PRIMARY KEY, mode TEXT NOT NULL, account_id TEXT NOT NULL REFERENCES accounts(id),
              account_revision INTEGER NOT NULL, credential_revision INTEGER NOT NULL,
              options TEXT NOT NULL, manifest TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS operations (
              id TEXT PRIMARY KEY, mode TEXT NOT NULL, kind TEXT NOT NULL,
              account_id TEXT REFERENCES accounts(id), target TEXT, payload TEXT NOT NULL,
              request_hash TEXT NOT NULL, idem TEXT, state TEXT NOT NULL,
              result TEXT, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              claimed_by TEXT, dispatched_at TEXT, UNIQUE(mode, idem));
            CREATE UNIQUE INDEX IF NOT EXISTS submit_target_lock ON operations(mode, account_id, target)
              WHERE kind='submit' AND state IN ('queued','running','reconciling','unknown');
            CREATE TABLE IF NOT EXISTS worker (mode TEXT PRIMARY KEY, pid INTEGER, heartbeat REAL);
            CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, mode TEXT, event TEXT, detail TEXT, at TEXT);
            PRAGMA user_version=2;
            """)
        os.chmod(self.path, 0o600)

    @contextmanager
    def tx(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("BEGIN IMMEDIATE")
        try:
            yield db
            if db.in_transaction:
                db.commit()
        except Exception:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

    def rows(self, sql, args=()):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            return [dict(row) for row in db.execute(sql, args)]
        finally:
            db.close()

    def audit(self, event, detail):
        with self.tx() as db:
            db.execute("INSERT INTO audit(mode,event,detail,at) VALUES(?,?,?,?)",
                       (self.mode, event, canonical(detail), now()))

    @staticmethod
    def public_account(row):
        if row is None:
            return None
        row = dict(row)
        row["configured"] = bool(row.pop("secret_ref"))
        return row

    def accounts(self, provider=None):
        rows = self.rows("SELECT * FROM accounts WHERE mode=? AND archived=0 ORDER BY name", (self.mode,))
        return [self.public_account(r) for r in rows if provider is None or r["provider"] == provider]

    def account(self, account_id):
        rows = self.rows("SELECT * FROM accounts WHERE id=? AND mode=?", (account_id, self.mode))
        if not rows:
            raise PortalError("Account not found in this mode")
        return self.public_account(rows[0])

    def credential(self, account_id):
        rows = self.rows("SELECT secret_ref FROM accounts WHERE id=? AND mode=?", (account_id, self.mode))
        if not rows or not rows[0]["secret_ref"]:
            raise PortalError("Credential not configured; no global fallback")
        path = self.root / "secrets" / rows[0]["secret_ref"]
        if path.is_symlink() or path.stat().st_mode & 0o077:
            raise PortalError("Unsafe credential file permissions")
        return path.read_text()

    def redaction_values(self):
        """Includes retained rotated credentials; never return this list to the UI."""
        values = []
        for path in (self.root / "secrets").iterdir():
            if path.is_file() and not path.is_symlink() and path.stat().st_size <= 4096:
                values.append(path.read_text())
        return values

    def save_account(self, *, provider, name, slug, principal, description="", enabled=True,
                     is_default=False, secret="", account_id=None, revision=None):
        if provider not in ("kaggle", "wandb"):
            raise PortalError("Unsupported provider")
        reference("owner/" + slug)
        reference("owner/" + principal)
        if not name.strip() or len(name) > 120:
            raise PortalError("A display name is required (max 120 characters)")
        if is_default and not enabled:
            raise PortalError("Default account must be enabled")
        if len(secret) > 4096 or any(c in secret for c in "\r\n\x00"):
            raise PortalError("Invalid credential")
        new_ref = uid() if secret.strip() else None
        if new_ref:
            path = self.root / "secrets" / new_ref
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as stream:
                stream.write(secret.strip())
                stream.flush()
                os.fsync(stream.fileno())
            directory = os.open(self.root / "secrets", os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        account_id, creating = account_id or uid(), account_id is None
        try:
            with self.tx() as db:
                old = db.execute("SELECT * FROM accounts WHERE id=? AND mode=?", (account_id, self.mode)).fetchone()
                if not creating and (old is None or old["revision"] != revision):
                    raise Conflict("Account changed; reload before editing")
                if old and old["provider"] != provider:
                    raise PortalError("Provider is immutable")
                if old and old["principal"] != principal and db.execute(
                    "SELECT 1 FROM operations WHERE account_id=? UNION SELECT 1 FROM notebooks WHERE account_id=? OR wandb_account_id=? LIMIT 1",
                    (account_id, account_id, account_id)).fetchone():
                    raise PortalError("Identity has references; create a new profile")
                if is_default:
                    db.execute("UPDATE accounts SET is_default=0,revision=revision+1 WHERE mode=? AND provider=? AND is_default=1 AND id<>?",
                               (self.mode, provider, account_id))
                if old:
                    db.execute("""UPDATE accounts SET name=?,slug=?,principal=?,description=?,enabled=?,is_default=?,revision=revision+1,
                        secret_ref=?,credential_revision=?,rotated_at=?,tested_at=?,test_result=? WHERE id=?""",
                               (name.strip(), slug, principal, description, int(enabled), int(is_default),
                                new_ref or old["secret_ref"], old["credential_revision"] + bool(new_ref),
                                now() if new_ref else old["rotated_at"], None if new_ref or principal != old["principal"] else old["tested_at"],
                                None if new_ref or principal != old["principal"] else old["test_result"], account_id))
                else:
                    db.execute("""INSERT INTO accounts(id,mode,provider,name,slug,principal,description,enabled,is_default,
                         revision,secret_ref,credential_revision,rotated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                               (account_id, self.mode, provider, name.strip(), slug, principal, description,
                                int(enabled), int(is_default), 1, new_ref, int(bool(new_ref)), now() if new_ref else None))
        except Exception as exc:
            if new_ref:
                (self.root / "secrets" / new_ref).unlink(missing_ok=True)
            if isinstance(exc, sqlite3.IntegrityError):
                raise Conflict("Slug/default conflicts with an existing account") from None
            raise
        self.audit("account_saved", {"id": account_id, "rotated": bool(new_ref)})
        return self.account(account_id)

    def archive_account(self, account_id, revision):
        with self.tx() as db:
            changed = db.execute("UPDATE accounts SET archived=1,enabled=0,is_default=0,revision=revision+1 WHERE id=? AND mode=? AND revision=?",
                                 (account_id, self.mode, revision)).rowcount
            if not changed:
                raise Conflict("Account changed; reload")
        self.audit("account_archived", {"id": account_id})

    def attach(self, account_id, kernel, wandb_account_id=None, run_ref="", attempt_id=None):
        account = self.account(account_id)
        if account["provider"] != "kaggle":
            raise PortalError("Select a Kaggle connection")
        kernel = reference(kernel)
        if run_ref:
            reference(run_ref, 3)
            if not wandb_account_id or self.account(wandb_account_id)["provider"] != "wandb":
                raise PortalError("Select an explicit W&B connection")
        else:
            wandb_account_id = None
        notebook_id = uid()
        with self.tx() as db:
            old = db.execute("SELECT * FROM notebooks WHERE mode=? AND account_id=? AND kernel=? AND attempt_id IS ?",
                             (self.mode, account_id, kernel, attempt_id)).fetchone()
            if old:
                if (old["wandb_account_id"], old["run_ref"]) == (None, "") and wandb_account_id and run_ref:
                    db.execute("UPDATE notebooks SET wandb_account_id=?, run_ref=? WHERE id=?",
                               (wandb_account_id, run_ref, old["id"]))
                    return old["id"]
                if old["wandb_account_id"] != wandb_account_id or old["run_ref"] != run_ref:
                    raise Conflict("Notebook already has a different tracking binding; attach as a new attempt")
                return old["id"]
            db.execute("INSERT INTO notebooks VALUES(?,?,?,?,?,?,?,?)", (notebook_id, self.mode, account_id, kernel,
                       wandb_account_id, run_ref, attempt_id, now()))
        return notebook_id

    def notebooks(self):
        return self.rows("SELECT * FROM notebooks WHERE mode=? ORDER BY created_at DESC", (self.mode,))

    def notebook(self, notebook_id):
        items = self.rows("SELECT * FROM notebooks WHERE id=? AND mode=?", (notebook_id, self.mode))
        if not items:
            raise PortalError("Notebook not found")
        return items[0]

    def observe(self, notebook_id, source, result):
        self.notebook(notebook_id)
        with self.tx() as db:
            if source == "wandb" and not result.get("error"):
                data = result["data"]
                old = db.execute("SELECT * FROM progress WHERE notebook_id=?", (notebook_id,)).fetchone()
                iteration, sample = data.get("last_iteration"), data.get("progress_sample_at")
                progress_at = old["progress_at"] if old else None
                if isinstance(iteration, (int, float)) and not isinstance(iteration, bool):
                    if old and old["iteration"] is not None and iteration < old["iteration"]:
                        progress_at = None
                    elif old and old["iteration"] is not None and iteration > old["iteration"] and sample:
                        try:
                            sample_time = datetime.fromisoformat(sample)
                            previous_time = datetime.fromisoformat(old["sample_at"]) if old["sample_at"] else None
                            if previous_time and previous_time <= sample_time <= datetime.now(timezone.utc):
                                progress_at = sample
                        except (ValueError, TypeError):
                            pass
                    db.execute("INSERT OR REPLACE INTO progress VALUES(?,?,?,?)", (notebook_id, iteration, sample, progress_at))
                data["observed_last_progress_at"] = progress_at
            db.execute("INSERT INTO observations(notebook_id,source,payload,created_at) VALUES(?,?,?,?)",
                       (notebook_id, source, canonical(result), now()))

    def observations(self, notebook_id, source):
        return [json.loads(r["payload"]) for r in self.rows(
            "SELECT payload FROM observations WHERE notebook_id=? AND source=? ORDER BY id DESC LIMIT 20", (notebook_id, source))]

    def enqueue(self, kind, payload, account_id=None, target=None, idem=None, cooldown=0):
        if kind not in ("test", "check_kaggle", "check_wandb", "build", "submit", "reconcile"):
            raise PortalError("Unknown operation")
        request_hash = digest({"kind": kind, "payload": payload, "account": account_id, "target": target})
        op_id, stamp = uid(), now()
        try:
            with self.tx() as db:
                if idem:
                    old = db.execute("SELECT * FROM operations WHERE mode=? AND idem=?", (self.mode, idem)).fetchone()
                    if old:
                        if old["request_hash"] != request_hash:
                            raise Conflict("Idempotency key reused with different payload")
                        return old["id"]
                if cooldown:
                    old = db.execute("SELECT * FROM operations WHERE mode=? AND kind=? AND account_id IS ? AND target IS ? ORDER BY created_at DESC LIMIT 1",
                                     (self.mode, kind, account_id, target)).fetchone()
                    if old and kind in ("build", "test") and old["request_hash"] != request_hash:
                        old = None
                    if old and old["error"] in ("rate_limited", "network_error"):
                        cooldown = max(cooldown, 60 if old["error"] == "rate_limited" else 30) + random.uniform(0, 5)
                    if old and (old["state"] in ("queued", "running") or
                                (datetime.now(timezone.utc) - datetime.fromisoformat(old["created_at"])).total_seconds() < cooldown):
                        return old["id"]
                db.execute("""INSERT INTO operations(id,mode,kind,account_id,target,payload,request_hash,idem,state,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (op_id, self.mode, kind, account_id, target, canonical(payload), request_hash, idem, "queued", stamp, stamp))
        except sqlite3.IntegrityError:
            raise Conflict("An unresolved submission already holds this target") from None
        return op_id

    def operations(self):
        return self.rows("SELECT * FROM operations WHERE mode=? ORDER BY created_at DESC LIMIT 200", (self.mode,))

    def operation(self, op_id):
        rows = self.rows("SELECT * FROM operations WHERE id=? AND mode=?", (op_id, self.mode))
        if not rows:
            raise PortalError("Operation not found")
        return rows[0]

    def claim(self, worker_id):
        with self.tx() as db:
            op = db.execute("SELECT * FROM operations WHERE mode=? AND state='queued' ORDER BY created_at LIMIT 1", (self.mode,)).fetchone()
            if not op:
                return None
            db.execute("UPDATE operations SET state='running',claimed_by=?,updated_at=? WHERE id=?", (worker_id, now(), op["id"]))
            return dict(op)

    def finish(self, op_id, result=None, error=None, state=None):
        state = state or ("failed" if error else "succeeded")
        with self.tx() as db:
            db.execute("UPDATE operations SET state=?,result=?,error=?,updated_at=? WHERE id=? AND mode=?",
                       (state, canonical(result) if result is not None else None, error, now(), op_id, self.mode))

    def recover(self):
        """Called only with the exclusive worker lock held. Never retry a push."""
        with self.tx() as db:
            db.execute("""UPDATE operations SET state=CASE WHEN kind='submit' AND dispatched_at IS NOT NULL THEN 'unknown' ELSE 'failed' END,
              error='Worker interrupted; explicit operator action required',updated_at=? WHERE mode=? AND state='running'""", (now(), self.mode))

    def add_preview(self, preview_id, account, options, manifest):
        with self.tx() as db:
            db.execute("INSERT INTO previews VALUES(?,?,?,?,?,?,?,?)", (preview_id, self.mode, account["id"],
                       account["revision"], account["credential_revision"], canonical(options), canonical(manifest), now()))

    def previews(self):
        rows = self.rows("SELECT * FROM previews WHERE mode=? ORDER BY created_at DESC", (self.mode,))
        for row in rows:
            if isinstance(row.get("options"), str):
                row["options"] = json.loads(row["options"])
            if isinstance(row.get("manifest"), str):
                row["manifest"] = json.loads(row["manifest"])
        return rows

    def preview(self, preview_id):
        rows = self.rows("SELECT * FROM previews WHERE id=? AND mode=?", (preview_id, self.mode))
        if not rows:
            raise PortalError("Preview not found")
        row = rows[0]
        row["options"], row["manifest"] = json.loads(row["options"]), json.loads(row["manifest"])
        return row

    def heartbeat(self):
        with self.tx() as db:
            db.execute("INSERT OR REPLACE INTO worker VALUES(?,?,?)", (self.mode, os.getpid(), time.time()))

    def worker_online(self):
        rows = self.rows("SELECT heartbeat FROM worker WHERE mode=?", (self.mode,))
        return bool(rows and time.time() - rows[0]["heartbeat"] < 60)

    def cleanup_secrets(self):
        """Offline maintenance only, with worker/UI stopped."""
        refs = {r["secret_ref"] for r in self.rows("SELECT secret_ref FROM accounts")}
        for path in (self.root / "secrets").iterdir():
            if path.name not in refs and path.is_file() and not path.is_symlink():
                path.unlink()
