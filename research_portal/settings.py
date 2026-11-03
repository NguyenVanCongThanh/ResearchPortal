"""Configuration loading has no provider side effects."""
from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
import tomllib

from .domain import PortalError

REPO = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    mode: str = "fixture"
    runtime: Path = Path(tempfile.gettempdir()) / f"research-portal-{os.getuid()}"
    bhsd: Path = Path("/home/u001015/BHSD_SSL")
    revision: str = "8d4a78e96400eb94d3c07fce810e495845df3783"
    allow_live_submit: bool = False
    timeout: int = 40
    cooldown: int = 10
    stale_seconds: int = 180
    stall_seconds: int = 1200


def load_settings():
    path = Path(os.environ.get("RESEARCH_PORTAL_SETTINGS", REPO / "config/settings.toml"))
    data = tomllib.loads(path.read_text()) if path.is_file() else {}
    app, runtime, bhsd = (data.get(k, {}) for k in ("app", "runtime", "bhsd"))
    mode = os.environ.get("RESEARCH_PORTAL_MODE", app.get("mode", "fixture"))
    if mode not in ("fixture", "live"):
        raise PortalError("Mode must be fixture or live")
    root = os.environ.get("RESEARCH_PORTAL_RUNTIME", runtime.get("root", ""))
    if mode == "live" and (not root or not runtime.get("local_filesystem_confirmed", False)):
        raise PortalError("Live mode requires runtime.root and local_filesystem_confirmed=true")
    root = Path(root).expanduser().resolve() if root else Settings().runtime
    if root == REPO or REPO in root.parents or root == Path("/"):
        raise PortalError("Runtime must be a private directory outside the checkout")
    if not isinstance(app.get("allow_live_submit", False), bool) or not isinstance(runtime.get("local_filesystem_confirmed", False), bool):
        raise PortalError("allow_live_submit and local_filesystem_confirmed must be TOML booleans")
    for key, default, lower, upper in (("provider_timeout_seconds", 40, 1, 120), ("cooldown_seconds", 10, 0, 3600),
                                       ("stale_seconds", 180, 1, 86400), ("stall_seconds", 1200, 1, 86400)):
        value = app.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
            raise PortalError(f"Invalid {key}: expected integer from {lower} to {upper}")
    return Settings(mode=mode, runtime=root, bhsd=Path(bhsd.get("checkout", Settings().bhsd)).expanduser().resolve(),
                    revision=bhsd.get("revision", Settings().revision),
                    allow_live_submit=bool(app.get("allow_live_submit", False)),
                    timeout=int(app.get("provider_timeout_seconds", 40)),
                    cooldown=int(app.get("cooldown_seconds", 10)),
                    stale_seconds=int(app.get("stale_seconds", 180)),
                    stall_seconds=int(app.get("stall_seconds", 1200)))
