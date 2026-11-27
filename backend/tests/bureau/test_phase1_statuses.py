"""P4.0: games loaded before P2.0a keep Phase 1's account statuses (AC, PD, ES, WO) on
file. What the bureau reads counts each as the status it became, so their analytics,
reports and account lists show a live book; validation knows only today's codes."""

from __future__ import annotations

from apps.standards.submission_template import (
    CLOSED_STATUS_CODES,
    CLOSED_STATUS_ON_FILE,
    CODE_LISTS,
    OPEN_STATUS_CODES,
    OPEN_STATUS_ON_FILE,
    PHASE_1_STATUS_CODES,
    WRITTEN_OFF_STATUS_CODES,
    WRITTEN_OFF_STATUS_ON_FILE,
)


def test_phase_1_statuses_count_as_the_statuses_they_became() -> None:
    assert "AC" in OPEN_STATUS_ON_FILE
    assert {"PD", "ES"} <= CLOSED_STATUS_ON_FILE
    assert "WO" in WRITTEN_OFF_STATUS_ON_FILE
    # Each old code lands in exactly one of the three.
    sets = (OPEN_STATUS_ON_FILE, CLOSED_STATUS_ON_FILE, WRITTEN_OFF_STATUS_ON_FILE)
    for old in PHASE_1_STATUS_CODES:
        assert sum(old in s for s in sets) == 1


def test_validation_still_knows_only_todays_codes() -> None:
    assert not set(CODE_LISTS["FacilityStatusCode"]) & set(PHASE_1_STATUS_CODES)
    for today in (OPEN_STATUS_CODES, CLOSED_STATUS_CODES, WRITTEN_OFF_STATUS_CODES):
        assert not today & set(PHASE_1_STATUS_CODES)
