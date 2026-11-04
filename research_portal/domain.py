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
    """Redact recursively before persistence; never retain signed URLs or non-finite floats."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
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


def _finite_num(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return value
    return None


def _first_finite(mapping, keys):
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        val = _finite_num(mapping.get(key))
        if val is not None:
            return val
    return None


def _fmt_duration(seconds):
    sec = _finite_num(seconds)
    if sec is None or sec < 0:
        return "—"
    total = int(sec)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def extract_wandb_telemetry(rows, summary=None):
    """Extract live scalar metrics, bounded time-series curves, and step log lines from W&B data."""
    summary = summary if isinstance(summary, dict) else {}
    rows = rows if isinstance(rows, list) else []

    live_metrics = {
        "iteration": _first_finite(summary, ("global_step", "train/iter", "iteration", "train/iteration", "iter")),
        "runtime_seconds": _first_finite(summary, ("_runtime",)),
        "supervised_loss": _first_finite(summary, ("train/supervised", "train/supervised_main", "train/loss", "loss")),
        "consistency_loss": _first_finite(summary, ("train/consistency",)),
        "total_loss_min": _first_finite(summary, ("train/total.min", "train/total")),
        "lr": _first_finite(summary, ("train/lr", "lr")),
        "val_dice": _first_finite(summary, ("train/val_mDice", "val/mDice", "val/dice_positive_mean", "val/dice_case_mean")),
        "best_dice": _first_finite(summary, ("best_mDice", "val/best_mDice", "train/best_mDice", "val/mDice.max")),
        "best_iter": _first_finite(summary, ("train/best_iter",)),
        "phase": summary.get("phase") if isinstance(summary.get("phase"), str) else None,
    }
    live_metrics = {k: v for k, v in live_metrics.items() if v is not None}

    train_curve = []
    val_curve = []
    log_entries = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        step = _first_finite(row, ("global_step", "train/iter", "iteration", "train/iteration", "iter", "_step"))
        if step is None:
            continue
        step_int = int(step)
        rt = _first_finite(row, ("_runtime",))
        sup = _first_finite(row, ("train/supervised", "train/supervised_main", "train/loss", "loss"))
        cons = _first_finite(row, ("train/consistency",))
        weight = _first_finite(row, ("train/weight",))
        lr = _first_finite(row, ("train/lr", "lr"))
        dice = _first_finite(row, ("val/mDice", "train/val_mDice", "val/dice_positive_mean", "val/dice_Hemorrhage"))
        best = _first_finite(row, ("val/best_mDice", "best_mDice", "train/best_mDice", "val/mDice.max"))

        if sup is not None or cons is not None:
            train_curve.append({
                "step": step_int,
                "sup": round(float(sup), 5) if sup is not None else None,
                "cons": round(float(cons), 5) if cons is not None else None,
                "lr": round(float(lr), 6) if lr is not None else None,
                "t": round(float(rt), 1) if rt is not None else None,
            })
            parts = [f"[Iter {step_int:6d} | {_fmt_duration(rt)}] [TRAIN]"]
            if sup is not None:
                parts.append(f"sup_loss={sup:.4f}")
            if cons is not None:
                parts.append(f"cons_loss={cons:.4f}")
            if weight is not None:
                parts.append(f"w={weight:.4f}")
            if lr is not None:
                parts.append(f"lr={lr:.6f}")
            log_entries.append((step_int, 0, " | ".join(parts)))

        if dice is not None:
            val_curve.append({
                "step": step_int,
                "dice": round(float(dice), 5),
                "best": round(float(best), 5) if best is not None else None,
                "t": round(float(rt), 1) if rt is not None else None,
            })
            parts = [f"[Iter {step_int:6d} | {_fmt_duration(rt)}] [VAL]  ", f"val/mDice={dice:.4f}"]
            if best is not None:
                parts.append(f"best_mDice={best:.4f}")
            log_entries.append((step_int, 1, " | ".join(parts)))

    train_curve.sort(key=lambda item: item["step"])
    val_curve.sort(key=lambda item: item["step"])
    log_entries.sort(key=lambda item: (item[0], item[1]))

    return {
        "live_metrics": live_metrics,
        "curves": {
            "train": train_curve[-150:],
            "val": val_curve[-150:],
        },
        "live_log_text": "\n".join(item[2] for item in log_entries[-150:]),
        "live_log_lines": len(log_entries[-150:]),
    }


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
