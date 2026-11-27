"""P3.7 — Compliance's duties.

Done when (Document 09): an enquiry without consent is found by sampling and
followed to a sanction; a missed return and a retention breach climb the regulator's
ladder; every rule carries its citation.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from django.db.models import Count
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bureau.core.models import AccountObservation, CreditAccount
from apps.bureau.quality.models import RegulatoryReturn
from apps.bureau.reports.enquiries import build_report, years_before
from apps.org.models import Employee
from apps.simulation import compliance, controls, duties, roles
from apps.simulation.bridge import start_game
from apps.simulation.engine import ClockError, advance
from apps.simulation.fingerprint import differences, fingerprint
from apps.simulation.models import (
    ComplianceFinding,
    ConsentCheck,
    EnquiryJudgement,
    Game,
    Notice,
    RegulatorFinding,
)
from apps.standards.compliance_rules import LEGAL_RETENTION_YEARS, RULES
from apps.standards.submission_template import CLOSED_STATUS_CODES
from apps.workitems.models import WorkItem
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import World
from tests.roles import working_as

HISTORY = 3  # months of records on file at the start

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.slow]


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world(db: None) -> World:
    g = build_world(81, "tiny")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


@pytest.fixture
def busy_world(db: None) -> World:
    """Enough applications for a sample: a tiny world sees a few a week."""
    g = build_world(81, "small")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


def _game(world: World, owner: User | None = None) -> Game:
    return controls.set_pause_rules(
        advance(start_game(world, owner=owner, history_months=HISTORY), 1), [], deadlines=False
    )


def _days(game: Game, n: int) -> Game:
    for _ in range(n):
        game = controls.advance_by(game, "day")
    return game


def _today(game: Game) -> Any:
    return controls.state(game).now.date()


@pytest.mark.django_db
def test_every_rule_carries_its_citation() -> None:
    assert set(RULES) == {"CONSENT", "RETURN", "RETENTION", "ACCESS", "FAIRNESS", "FINDINGS"}
    for rule in RULES.values():
        assert rule.title and rule.rule and rule.citation
        assert rule.status == "TO_CONFIRM"  # until the owner checks the texts (A-077)


def test_the_return_is_owed_and_filed_with_its_figures(world: World) -> None:
    owner = User.objects.create_user("compliance-head")
    game = _game(world, owner)
    owed = RegulatoryReturn.objects.get(organization=game.organization)
    assert owed.due_date.day >= 15 and owed.due_date > owed.period
    item = WorkItem.objects.get(case=owed.case)
    assert roles.ITEM_ROLES[item.item_type] == roles.COMPLIANCE
    assert item.correct_decision == "FILE_RETURN"
    client = APIClient()
    client.force_authenticate(owner)
    base = f"/api/v1/games/{game.pk}"
    shown = client.get(f"{base}/compliance/").json()
    assert shown["returns"][0]["work_item"] == item.item_number
    assert {r["code"] for r in shown["rules"]} == set(RULES)
    detail = client.get(f"{base}/work-items/{item.item_number}/").json()
    assert detail["regulatory_return"]["figures"]["accounts"] > 0  # what will be filed

    # The Head of Data Operations may not file it; the Head of Compliance does.
    working_as(game, roles.DATA_OPERATIONS)
    decide = {"decision": "FILE_RETURN"}
    assert client.post(f"{base}/work-items/{item.item_number}/resolve/", decide).status_code == 403
    working_as(Game.objects.get(pk=game.pk), roles.COMPLIANCE)
    assert client.post(f"{base}/work-items/{item.item_number}/resolve/", decide).status_code == 200
    owed.refresh_from_db()
    assert owed.filed_at is not None and owed.filed_by == "Player"
    assert owed.figures["customers"] > 0 and owed.figures["accounts"] > 0
    assert not client.get(f"{base}/compliance/").json()["returns"][0]["late"]


def test_consent_sampling_leads_to_a_sanction(busy_world: World, monkeypatch: Any) -> None:
    world = busy_world
    # Careless subscribers, so a sample surely finds enquiries without consent.
    monkeypatch.setattr(duties, "IMPROPER_RATE", (0.3, 0.4))
    owner = User.objects.create_user("compliance-head")
    game = _days(_game(world, owner), 3)
    busiest = (
        EnquiryJudgement.objects.filter(game=game)
        .values("enquiry__subscriber__subscriber_code")
        .annotate(n=Count("pk"))
        .order_by("-n")
        .first()
    )
    assert busiest is not None
    code = busiest["enquiry__subscriber__subscriber_code"]
    month = controls.this_month(game)
    client = APIClient()
    client.force_authenticate(owner)
    url = f"/api/v1/games/{game.pk}/compliance/"
    body = {"action": "sample", "subscriber": code, "month": month.isoformat(), "size": 10}
    assert client.post(url, body, format="json").status_code == 403  # the CEO does not sample
    game = working_as(Game.objects.get(pk=game.pk), roles.COMPLIANCE)
    assert client.post(url, body, format="json").status_code == 200
    check = ConsentCheck.objects.get(game=game)
    assert check.sample and not check.answered

    # The lender answers three working days later. Compliance reads the forms that
    # morning (ten forms, one working day: P4.0); those it could not send are a finding.
    game = _days(Game.objects.get(pk=game.pk), 4)
    check.refresh_from_db()
    assert check.answered and check.reviewed and check.missing
    game.organization.refresh_from_db()
    assert f"check {check.number}" in game.organization.compliance_busy_with
    held = dict(
        EnquiryJudgement.objects.filter(game=game, enquiry__enquiry_reference__in=check.sample)
        .values_list("enquiry__enquiry_reference", "grounds_held")
    )  # fmt: skip
    assert sorted(check.missing) == sorted(r for r, ok in held.items() if not ok)
    finding = ComplianceFinding.objects.get(game=game, kind="CONSENT_MISSING")
    assert finding.due_date is not None and code in finding.remedy
    assert Notice.objects.filter(game=game, kind="COMPLIANCE_FINDING").exists()

    # A suspension settles the finding, stops the lender's enquiries, and makes it careful.
    before = duties.improper_rate(game, code)
    sanction = {"action": "sanction", "subscriber": code, "kind": "SUSPENSION"}
    answer = client.post(url, sanction, format="json")
    assert answer.status_code == 200
    assert next(s for s in answer.json()["subscribers"] if s["code"] == code)["suspended"]
    finding.refresh_from_db()
    assert finding.resolved_tick is not None
    assert duties.improper_rate(game, code) == pytest.approx(before * duties.SUSPENSION_FACTOR)
    suspended_at = controls.state(game).now
    game = _days(Game.objects.get(pk=game.pk), 2)
    assert not EnquiryJudgement.objects.filter(
        game=game, enquiry__subscriber__subscriber_code=code,
        enquiry__enquired_at__gt=suspended_at,
    ).exists()  # fmt: skip
    assert EnquiryJudgement.objects.filter(
        game=game, enquiry__enquired_at__gt=suspended_at
    ).exists()  # the other lenders still enquire

    # The sample, the answers and the sanction replay exactly.
    copy = controls.replay(Game.objects.get(pk=game.pk), start_game(world, history_months=HISTORY))
    assert fingerprint(copy) == fingerprint(game), differences(copy, game)


def test_breaches_climb_the_regulators_ladder(world: World) -> None:
    game = _game(world)
    ComplianceFinding.objects.filter(game=game).delete()  # a quarter's review due at the start
    # Everyone leaves (and keeps their access): nobody files the return.
    Employee.objects.filter(organization=game.organization).update(is_active=False)
    today = _today(game)

    # A return left past its due date.
    RegulatoryReturn.objects.filter(organization=game.organization).update(
        due_date=today - timedelta(days=1)
    )
    # A compliance finding left past its deadline.
    finding = duties.raise_finding(
        game, "CONSENT_MISSING", "TEST-CHECK-1", "A lender lacked consent.", "Warn it.",
        game.current_tick, controls.state(game).now,
    )  # fmt: skip
    ComplianceFinding.objects.filter(pk=finding.pk).update(due_date=today - timedelta(days=1))
    # A report that shows an account closed more than five years ago.
    account = (
        CreditAccount.objects.filter(
            organization=game.organization, account_status__in=CLOSED_STATUS_CODES
        )
        .order_by("pk")
        .first()
    )
    assert account is not None
    for obs in AccountObservation.objects.filter(credit_account=account):
        obs.reporting_date = years_before(obs.reporting_date, LEGAL_RETENTION_YEARS + 1)
        obs.save(update_fields=["reporting_date"])
    now = controls.state(game).now
    shown = build_report(account.customer, now)
    assert "held_past_legal_limit" not in shown  # 5 years: the old account has gone
    controls.set_retention(game, 7)
    kept = build_report(account.customer, now)
    assert (
        kept["held_past_legal_limit"] == 1 and len(kept["accounts"]) == len(shown["accounts"]) + 1
    )
    report = SimpleNamespace(report=kept, enquiry_reference="TEST")
    duties.retention_breach(game, report, now, duties.quietly)  # type: ignore[arg-type]

    game = _days(game, 2)  # to the next morning's review
    kinds = set(RegulatorFinding.objects.filter(game=game).values_list("kind", flat=True))
    assert kinds == {"MISSED_RETURN", "RETENTION_BREACH", "UNRESOLVED_FINDING"}
    finding.refresh_from_db()
    assert finding.escalated
    assert compliance.standing(game).level == 2  # three findings: a formal directive
    with pytest.raises(ClockError, match="Retention"):
        controls.set_retention(game, 10)

    # The quarter's access review finds the leavers; reviewing removes their access, on
    # Compliance's next working day (P4.0).
    first = today.replace(day=1)
    quarter = first.replace(month=((first.month - 1) // 3) * 3 + 1)
    duties.month_start(game, quarter, game.current_tick, now, duties.quietly)
    due = ComplianceFinding.objects.get(game=game, kind="ACCESS_REVIEW_DUE")
    assert "leaver" in due.detail
    controls.review_access(game)
    with pytest.raises(ClockError, match="already due"):
        controls.review_access(game)
    due.refresh_from_db()
    assert due.resolved_tick is None  # asked for, not yet done
    assert duties.leavers_with_access(game)
    duties.compliance_day(game, today, game.current_tick, now, duties.quietly)
    game.organization.refresh_from_db()
    assert not game.organization.access_review_requested
    assert game.organization.compliance_busy_with == "the staff access review"
    due.refresh_from_db()
    assert due.resolved_tick is not None and not duties.leavers_with_access(game)
