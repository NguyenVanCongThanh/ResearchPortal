"""Validate a clean installed environment before producing a tested lockfile."""
import importlib.metadata
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {"streamlit": "1.51.0", "kaggle": "1.7.4.5", "wandb": "0.26.1", "requests": "2.32.5",
            "PyYAML": "6.0.3", "pytest": "8.4.2"}


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
