"""Small, provider-independent contracts and input validation."""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
import re


class PortalError(ValueError):
    pass


class Conflict(PortalError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def reference(value, parts=2):
    value = value.strip()
    if len(value.split("/")) != parts or not all(
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", p) and p not in (".", "..")
        for p in value.split("/")
    ):
        raise PortalError("Expected owner/slug" if parts == 2 else "Expected entity/project/run-id")
    return value


def scrub(value, secrets=()):
    """Redact recursively before persistence; never retain signed URLs."""
    if isinstance(value, dict):
        return {str(k): ("[redacted]" if re.search(r"token|password|api.?key|credential|authorization|secret", str(k), re.I)
                         else scrub(v, secrets)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(v, secrets) for v in value]
    if not isinstance(value, str):
        return value
    for secret in secrets:
        if secret:
            value = value.replace(secret, "[redacted]")
            if len(secret) >= 12:
                value = value.replace(secret[:12], "[redacted]")
    value = re.sub(r"https?://[^\s\"'<>]+[?][^\s\"'<>]+", "[redacted URL]", value)
    value = re.sub(r"(?i)(bearer\s+)[\w.-]+", r"\1[redacted]", value)
    return value


def sampled_progress(rows, method=None):
    """Only explicit training axes; global_step is verified for BHSD Mean Teacher."""
    axes = ("iteration", "train/iteration", "iter") + (("global_step",) if method == "mean_teacher" else ())
    candidates = []
    for row in rows:
        stamp = row.get("_timestamp")
        if not isinstance(stamp, (int, float)) or isinstance(stamp, bool) or not math.isfinite(stamp) or stamp < 0:
            continue
        for axis in axes:
            value = row.get(axis)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                candidates.append((stamp, value, axis))
                break
    if not candidates:
        return {"last_iteration": None, "iteration_axis": None, "progress_sample_at": None}
    stamp, value, axis = max(candidates, key=lambda item: item[0])
    return {"last_iteration": value, "iteration_axis": axis,
            "progress_sample_at": datetime.fromtimestamp(stamp, timezone.utc).isoformat()}


@dataclass
class Result:
    connection_id: str
    remote_ref: str
    source: str
    data: dict = field(default_factory=dict)
    error: str | None = None
    completeness: str = "partial"
    fetched_at: str = field(default_factory=now)
    schema_version: int = 1
    remote_version: str | None = None
    version_scope: str = "latest_unverified"
    warnings: list = field(default_factory=list)

    def payload(self):
        return asdict(self)


@dataclass(frozen=True)
class BuildOptions:
    template: str = "mean_teacher"
    task: str = "multiclass"
    slug: str = ""
    title: str = ""
    dataset: str = ""
    gpu: bool = True
    tracking: str = "offline"
    resume_run: str = ""
    resume_mode: str = ""
    checkpoint: str = ""

    def validate(self):
        if self.template != "mean_teacher" or self.task not in ("multiclass", "binary"):
            raise PortalError("Unsupported template/task")
        if self.slug:
            reference("owner/" + self.slug)
        if len(self.title) > 120 or any(ord(c) < 32 for c in self.title):
            raise PortalError("Invalid title")
        if self.dataset:
            reference(self.dataset)
        if self.tracking not in ("offline", "kaggle_secrets"):
            raise PortalError("Unsupported tracking mode")
        if self.resume_run:
            reference(self.resume_run, 3)
            if self.tracking != "kaggle_secrets":
                raise PortalError("Resume requires Kaggle Secrets / online W&B")
        elif self.resume_mode or self.checkpoint:
            raise PortalError("Resume mode/checkpoint require a source run")
        if self.resume_mode not in ("", "same-run", "new-run") or self.checkpoint not in ("", "latest", "best"):
            raise PortalError("Invalid resume policy")
        return self

    def payload(self):
        return asdict(self)
