"""Validate a clean installed environment before producing a tested lockfile."""
import importlib.metadata
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def load_expected_versions():
    expected = {}
    for req_name in ("requirements.txt", "requirements-dev.txt"):
        req_path = ROOT / req_name
        if not req_path.is_file():
            continue
        for raw_line in req_path.read_text().splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            if "==" in line:
                pkg, ver = line.split("==", 1)
                expected[pkg.strip()] = ver.strip()
    return expected


EXPECTED = load_expected_versions()


def main():
    if sys.version_info[:2] != (3, 11) or sys.prefix == sys.base_prefix:
        raise SystemExit("Use a dedicated Python 3.11 virtual environment")
    for package, version in EXPECTED.items():
        try:
            installed = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            raise SystemExit(f"Missing dependency: {package}; install requirements-dev.txt first") from None
        if installed != version:
            raise SystemExit(f"Expected {package}=={version}, got {installed}")
    subprocess.run([sys.executable, "-m", "pip", "check"], check=True)
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    subprocess.run([sys.executable, "-m", "pytest", "-q"], check=True, cwd=ROOT, env=env)
    installed = sorted(f"{d.metadata['Name']}=={d.version}" for d in importlib.metadata.distributions()
                       if d.metadata["Name"].lower() != "pip")
    target = ROOT / "requirements.lock"
    temporary = target.with_suffix(".lock.tmp")
    temporary.write_text("# Tested Python 3.11 environment, including test dependencies.\n" + "\n".join(installed) + "\n")
    temporary.replace(target)
    print("All checks passed; wrote requirements.lock")


if __name__ == "__main__":
    main()
