"""P2.0b — The rule book: versioned rules with effective dates (D19).

Released rules are frozen part by part (the lock file), the edition in force is found by
date, and trial editions leave the series as released.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from apps.standards import rulebook
from apps.standards.rulebook import (
    DATA_STANDARDS,
    SERIES,
    STANDARD_1_1,
    TAX_2024,
    TAX_RULES,
    Series,
    digest,
    parts,
)

LOCK = Path(rulebook.__file__).with_name("rulebook.lock.json")


def test_released_editions_are_frozen() -> None:
    """Changing a released rule would rewrite the past of every game that used it.

    Each part of each edition (a template, a code list, a threshold) is locked.
    A released part may never change or disappear; new parts may be added (and
    must then be locked too). To change a rule, publish a new edition.
    """
    lock = json.loads(LOCK.read_text())
    assert set(lock) == set(SERIES)
    for name, series in SERIES.items():
        published = {e.version: e for e in series.editions}
        assert set(published) == set(lock[name]), f"{name}: every edition must be in the lock"
        for version, entry in lock[name].items():
            edition = published[version]
            assert str(edition.effective) == entry["effective"], f"{name} {version} moved"
            current = parts(edition)
            for part, locked in entry["parts"].items():
                assert part in current, f"{name} {version}: {part} was removed"
                assert current[part] == locked, f"{name} {version}: {part} was edited"
            unlocked = set(current) - set(entry["parts"])
            assert not unlocked, f"{name} {version}: lock the new parts {sorted(unlocked)}"


def test_the_edition_in_force_is_found_by_date() -> None:
    later = replace(STANDARD_1_1, version="9.9", effective=date(2027, 3, 1))
    with DATA_STANDARDS.trial(later):
        assert DATA_STANDARDS.at(date(2027, 2, 28)) is STANDARD_1_1
        assert DATA_STANDARDS.at(date(2027, 3, 1)) is later
        assert DATA_STANDARDS.at(date(2030, 1, 1)) is later
        assert DATA_STANDARDS.get("1.1") is STANDARD_1_1
    assert DATA_STANDARDS.editions == (STANDARD_1_1,)
    with pytest.raises(LookupError):
        DATA_STANDARDS.get("9.9")
    with pytest.raises(LookupError):
        TAX_RULES.at(date(2023, 12, 31))
    assert TAX_RULES.at(date(2024, 1, 1)) is TAX_2024


def test_editions_must_be_distinct() -> None:
    with pytest.raises(ValueError, match="already exists"):
        Series("test", (TAX_2024, replace(TAX_2024, effective=date(2025, 1, 1))))
    with pytest.raises(ValueError, match="take effect on"):
        Series("test", (TAX_2024, replace(TAX_2024, version="other")))


def test_parts_split_an_edition_into_its_rules() -> None:
    names = parts(STANDARD_1_1)
    assert {"fields:CONC", "fields:BUSC", "fields:COND", "fields:CONJ"} <= set(names)
    assert "code_lists:Gender" in names and "id_required_from" in names
    assert "version" not in names and "note" not in names
    assert set(parts(TAX_2024)) == {
        "vat_and_levies",
        "ssnit_employer",
        "ssnit_employee",
        "paye_bands",
        "remittance_day",
    }


def test_the_digest_sees_any_change() -> None:
    assert digest(TAX_2024) == digest(replace(TAX_2024))
    assert digest(TAX_2024) != digest(replace(TAX_2024, remittance_day=15))
    fields = dict(STANDARD_1_1.fields)
    kind = next(iter(fields))
    fields[kind] = fields[kind][:-1]
    assert digest(STANDARD_1_1) != digest(replace(STANDARD_1_1, fields=fields))
