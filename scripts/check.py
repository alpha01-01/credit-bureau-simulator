"""Run every project check. Usage (from the repository root):

    backend/.venv/Scripts/python scripts/check.py           # all checks, without the slow tests
    backend/.venv/Scripts/python scripts/check.py --full    # all checks and the slow tests (before merging)
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


# NumPy's OpenBLAS reserves a buffer per thread; on a busy laptop that can fail.
# The project does no multi-threaded linear algebra, so one thread is enough.
ENV = {**os.environ, "OPENBLAS_NUM_THREADS": os.environ.get("OPENBLAS_NUM_THREADS", "1")}


def venv(tool: str) -> str:
    return str(VENV_BIN / tool)


# The fast backend tests run on eight workers, one test file to a worker, each with its own
# test database (pytest-xdist; P4.0). The full run stays on one: eight month-long tests
# at once run the database out of memory, and bring out the intermittent replay
# mismatch first seen in P3.0 more often (docs/progress.md, P4.0).
PARALLEL = ["-n", "8", "--dist", "loadfile"]

# (name, command, working directory, included in --fast)
CHECKS: list[tuple[str, list[str], Path, bool]] = [
    ("backend: format", [venv("ruff"), "format", "--check", "."], BACKEND, True),
    ("backend: lint", [venv("ruff"), "check", "."], BACKEND, True),
    ("backend: module boundaries", [venv("lint-imports"), "--no-cache"], BACKEND, True),
    ("backend: types", [venv("mypy"), "."], BACKEND, False),
    ("backend: migrations up to date", [venv("python"), "manage.py", "makemigrations", "--check", "--dry-run"], BACKEND, False),
    ("backend: tests", [venv("pytest"), "-q", "-m", "not slow", *PARALLEL], BACKEND, False),
    ("frontend: format", [NPM, "run", "--silent", "format:check"], FRONTEND, True),
    ("frontend: lint", [NPM, "run", "--silent", "lint"], FRONTEND, True),
    ("frontend: types", [NPM, "run", "--silent", "typecheck"], FRONTEND, False),
    ("frontend: tests", [NPM, "run", "--silent", "test"], FRONTEND, False),
]  # fmt: skip


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fast", action="store_true", help="run only the quick checks")
    parser.add_argument("--full", action="store_true", help="include the slow (month-long) tests")
    args = parser.parse_args()

    failures: list[str] = []
    for name, command, cwd, fast in CHECKS:
        if args.fast and not fast:
            continue
        if args.full and name == "backend: tests":
            name, command = "backend: tests (full)", [venv("pytest"), "-q"]
        started = time.monotonic()
        result = subprocess.run(  # noqa: S603
            command, cwd=cwd, capture_output=True, text=True, check=False, env=ENV
        )
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
