"""Run every project check. Usage (from the repository root):

    backend/.venv/Scripts/python scripts/check.py           # all checks
    backend/.venv/Scripts/python scripts/check.py --fast    # pre-commit subset

Exits non-zero if any check fails. See Document 06, Section 11.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"
FRONTEND = REPO / "frontend"

VENV_BIN = BACKEND / ".venv" / ("Scripts" if os.name == "nt" else "bin")
NPM = shutil.which("npm.cmd" if os.name == "nt" else "npm") or "npm"


def venv(tool: str) -> str:
    return str(VENV_BIN / tool)


# (name, command, working directory, included in --fast)
CHECKS: list[tuple[str, list[str], Path, bool]] = [
    ("backend: format", [venv("ruff"), "format", "--check", "."], BACKEND, True),
    ("backend: lint", [venv("ruff"), "check", "."], BACKEND, True),
    ("backend: module boundaries", [venv("lint-imports"), "--no-cache"], BACKEND, True),
    ("backend: types", [venv("mypy"), "."], BACKEND, False),
    ("backend: migrations up to date", [venv("python"), "manage.py", "makemigrations", "--check", "--dry-run"], BACKEND, False),
    ("backend: tests", [venv("pytest"), "-q"], BACKEND, False),
    ("frontend: format", [NPM, "run", "--silent", "format:check"], FRONTEND, True),
    ("frontend: lint", [NPM, "run", "--silent", "lint"], FRONTEND, True),
    ("frontend: types", [NPM, "run", "--silent", "typecheck"], FRONTEND, False),
    ("frontend: tests", [NPM, "run", "--silent", "test"], FRONTEND, False),
]  # fmt: skip


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fast", action="store_true", help="run only the quick checks")
    args = parser.parse_args()

    failures: list[str] = []
    for name, command, cwd, fast in CHECKS:
        if args.fast and not fast:
            continue
        started = time.monotonic()
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)  # noqa: S603
        elapsed = time.monotonic() - started
        if result.returncode == 0:
            print(f"  PASS  {name}  ({elapsed:.1f}s)")  # noqa: T201
        else:
            print(f"  FAIL  {name}  ({elapsed:.1f}s)")  # noqa: T201
            print(result.stdout + result.stderr)  # noqa: T201
            failures.append(name)

    if failures:
        print(f"\n{len(failures)} check(s) failed: {', '.join(failures)}")  # noqa: T201
        return 1
    print("\nAll checks passed.")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
