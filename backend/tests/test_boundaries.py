"""The truth boundary (Document 07, Section 7.1; Document 06, Section 10).

import-linter enforces this in the check script; this test keeps it in the
normal test run as well so it can never be skipped by accident.
"""

from pathlib import Path

import pytest
from importlinter.cli import lint_imports

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_import_contracts_hold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(BACKEND_DIR)
    assert lint_imports(no_cache=True) == 0
