"""P2.9 — Managed departments: HR, Sales and IT.

Done when (Document 08): hiring a senior officer, signing a new subscriber and
suffering an outage each show up in the queue, revenue and freshness metrics as
expected.

Three bureaus play the first three weeks of January in one world. The first
does nothing new. The second hires a senior officer and signs up SwiftCash on
day one. The third loses its systems for the first week, while its providers'
files are arriving, and sends an officer on a course.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from django.db.models import Sum
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.commercial.models import Subscriber, UsageRecord
from apps.finance.models import JournalEntry
from apps.org.models import Employee
from apps.simulation import controls, hr, it
from apps.simulation.assets import depth_and_freshness
from apps.simulation.bridge import start_game
from apps.simulation.clock import TICKS_PER_DAY, TICKS_PER_HOUR
from apps.simulation.demand import REFERENCE_PRICE
from apps.simulation.engine import ClockError
from apps.simulation.fingerprint import fingerprint
from apps.simulation.models import Game, Incident, LendingDecision, Notice, Proposal
from apps.workitems.models import ItemStatus, WorkItem
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import World
from tests.roles import working_as

DAYS = 15
OUTAGE_DAYS = 5
PROSPECT = "SWC"


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world(db: None) -> World:
    g = build_world(81, "small")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


def _start(world: World, owner: Any = None) -> Game:
    """A cautious bureau: fuzzy matching, and every near match held for review (a real queue)."""
    game = controls.set_pause_rules(start_game(world, owner=owner), [], deadlines=False)
    game = controls.set_matching_tooling(game, "STANDARD")
    game = controls.set_matching_thresholds(game, 0.99, 0.6)
    return controls.advance_by(game, "hour")


def _days(game: Game, days: int) -> Game:
    for _ in range(days):
        game = controls.advance_by(game, "day")
    return game


def _queue(game: Game) -> tuple[int, float]:
    """Items decided, and the average working hours they waited from opening to decision."""
    done = list(
        WorkItem.objects.filter(organization=game.organization, status=ItemStatus.DONE)
        .exclude(resolved_by="PLAYER")
        .values_list("created_tick", "resolved_tick")
    )
    waits = [(resolved - created) / TICKS_PER_HOUR for created, resolved in done if resolved]
    return len(done), sum(waits) / len(waits)


def _revenue(game: Game) -> Decimal:
    total = UsageRecord.objects.filter(organization=game.organization).aggregate(
        s=Sum("unit_price")
    )["s"]
    return total or Decimal("0")


@pytest.mark.django_db(transaction=True)
@pytest.mark.slow
def test_hiring_signing_and_an_outage_show_in_queue_revenue_and_freshness(world: World) -> None:
    base = _days(_start(world), OUTAGE_DAYS)
    outage_end = controls.state(base).now.date()
    base_week = depth_and_freshness(base, outage_end)
    base = _days(base, DAYS - OUTAGE_DAYS)

    # --- Growth: a senior officer and a new subscriber ---------------------------------
    grow = _start(world)
    pool = hr.candidates_for(grow, controls.this_month(grow))
    assert [c.job_title for c in pool] == list(hr.ROLES)  # one of each role, every month
    senior = controls.hire_candidate(grow, 3)
    assert senior.job_title == "Senior Data Officer" and senior.is_active
    with pytest.raises(ClockError):
        controls.hire_candidate(grow, 3)  # already hired
    price = (REFERENCE_PRICE * Decimal("0.8")).quantize(Decimal("0.01"))
    controls.send_proposal(grow, PROSPECT, price)
    with pytest.raises(ClockError):
        controls.send_proposal(grow, PROSPECT, price)  # one proposal at a time
    grow = _days(grow, DAYS)

    proposal = Proposal.objects.get(game=grow, lender_code=PROSPECT)
    assert proposal.status == "ACCEPTED", proposal.status
    subscriber = Subscriber.objects.get(organization=grow.organization, subscriber_code=PROSPECT)
    assert subscriber.is_active
    assert Notice.objects.filter(game=grow, kind="PROPOSAL_ACCEPTED").exists()

    # Queue: with a fourth pair of hands, items wait less for a decision.
    (base_done, base_wait), (grow_done, grow_wait) = _queue(base), _queue(grow)
    print(f"queue base {base_done} done, {base_wait:.1f}h wait; grow {grow_done}, {grow_wait:.1f}h")  # noqa: T201
    assert WorkItem.objects.filter(assignee=senior, status=ItemStatus.DONE).exists()
    assert grow_done >= base_done
    assert grow_wait < base_wait

    # Revenue: SwiftCash's checks are billed at the price it agreed.
    swc = UsageRecord.objects.filter(organization=grow.organization, subscriber=subscriber)
    print(f"revenue base {_revenue(base)} grow {_revenue(grow)}; SWC checks {swc.count()}")  # noqa: T201
    assert swc.exists() and {u.unit_price for u in swc} == {price}
    assert _revenue(grow) > _revenue(base)
    assert proposal.answered_at is not None
    assert min(swc.values_list("usage_at", flat=True)) > proposal.answered_at

    # --- An outage in the week the files arrive ---------------------------------------
    down = _start(world)
    officer = Employee.objects.get(organization=down.organization, job_title="Data Officer")
    skill = float(officer.skills["MATCH_REVIEW"])
    controls.train_employee(down, officer.employee_number, "MATCH_REVIEW")
    officer.refresh_from_db()
    assert float(officer.skills["MATCH_REVIEW"]) == pytest.approx(skill + hr.TRAINING_GAIN)
    assert JournalEntry.objects.filter(
        organization=down.organization, source_type="STAFF_TRAINING"
    ).exists()

    incident = it.start_outage(down, down.current_tick + 1, "Test outage.", lambda *a: None)
    assert incident.ends_tick - incident.started_tick + 1 == 2 * TICKS_PER_DAY
    # The backup fails too: the bureau is down for the first week.
    Incident.objects.filter(pk=incident.pk).update(
        ends_tick=incident.started_tick + OUTAGE_DAYS * TICKS_PER_DAY - 1
    )
    down = _days(down, OUTAGE_DAYS)
    assert it.waiting(down) > 0  # files arrived and wait for a working batch
    # Freshness: the day systems come back, the down bureau's reports are older.
    down_week = depth_and_freshness(down, outage_end)
    print(f"freshness after the outage: base {base_week} down {down_week}")  # noqa: T201
    # (In this small world the bureau's only data is January's files: none are loaded yet.)
    assert base_week["freshness_days"] is not None
    assert down_week["freshness_days"] is None or (
        down_week["freshness_days"] > base_week["freshness_days"]
    )
    assert down_week["accounts"] < base_week["accounts"]
    assert Notice.objects.filter(game=down, kind="BATCH_SKIPPED").exists()

    # Nobody could check the bureau: every lending decision was made blind.
    blind = LendingDecision.objects.filter(
        game=down, tick__lte=incident.started_tick + OUTAGE_DAYS * TICKS_PER_DAY - 1
    )
    assert blind.exists() and not blind.filter(checked=True).exists()

    # The officer was away the first day.
    first_day = WorkItem.objects.filter(
        assignee=officer, started_tick__lte=incident.started_tick + TICKS_PER_DAY - 1
    )
    assert not first_day.exists()

    down = _days(down, DAYS - OUTAGE_DAYS)
    assert Notice.objects.filter(game=down, kind="OUTAGE_OVER").exists()
    assert it.waiting(down) == 0  # the backlog cleared, two files a night
    assert _revenue(down) < _revenue(base)  # checks lost while systems were down

    # Responding: the vendor brings systems back within two working hours, for a fee.
    second = it.start_outage(down, down.current_tick + 1, "Again.", lambda *a: None)
    controls.respond_to_outage(down, "VENDOR")
    second.refresh_from_db()
    assert second.ends_tick == down.current_tick + 2 * TICKS_PER_HOUR
    assert JournalEntry.objects.filter(
        organization=down.organization, source_type="IT_INCIDENT"
    ).exists()
    with pytest.raises(ClockError):
        controls.respond_to_outage(down, "BACKUP")  # one response per outage
    down = controls.advance_by(down, "hour", 3)
    assert Notice.objects.filter(game=down, kind="OUTAGE_OVER", title__contains="vendor").exists()

    # The same actions replayed give the same game.
    replayed = controls.replay(grow, start_game(world))
    assert fingerprint(replayed) == fingerprint(grow)


@pytest.mark.django_db(transaction=True)
def test_pay_moves_morale_and_unhappy_staff_resign(world: World) -> None:
    game = start_game(world)
    junior = Employee.objects.get(organization=game.organization, job_title="Junior Data Officer")
    controls.set_salary(game, junior.employee_number, Decimal("1000"))
    notices: list[tuple[Any, ...]] = []
    for month in range(1, 13):
        hr.month_update(
            game, junior.hired_on.replace(month=month, day=1), lambda *a: notices.append(a)
        )
        junior.refresh_from_db()
        if not junior.is_active:
            break
    assert junior.morale < hr.RESIGN_BELOW
    assert not junior.is_active
    assert any(n[0] == "RESIGNATION" for n in notices)

    # A well-paid officer grows happier.
    senior = Employee.objects.get(organization=game.organization, job_title="Senior Data Officer")
    before = senior.morale
    controls.set_salary(game, senior.employee_number, Decimal("12000"))
    hr.month_update(game, senior.hired_on, lambda *a: None)
    senior.refresh_from_db()
    assert senior.morale > before


@pytest.mark.django_db(transaction=True)
def test_department_screens(world: World) -> None:
    owner = User.objects.create_user("player")
    game = start_game(world, owner=owner)
    client = APIClient()
    client.force_authenticate(owner)
    base = f"/api/v1/games/{game.pk}"

    staff = client.get(f"{base}/staff/").json()
    assert len(staff["team"]) == 3 and len(staff["candidates"]) == 3
    hired = client.post(f"{base}/staff/", {"action": "hire", "candidate": 1}, format="json")
    assert hired.status_code == 200 and len(hired.json()["team"]) == 4
    bad = client.post(f"{base}/staff/", {"action": "salary", "employee": "E0001", "salary": "x"})
    assert bad.status_code == 400

    sales = client.get(f"{base}/sales/").json()
    codes = {p["code"] for p in sales["prospects"]}
    assert PROSPECT in codes and "ATB" not in codes
    assert client.post(f"{base}/sales/", {"lender": PROSPECT, "price": "20"}).status_code == 403
    working_as(Game.objects.get(pk=game.pk), "SALES")  # proposals are the Head of Sales's (P3.1)
    sent = client.post(f"{base}/sales/", {"lender": PROSPECT, "price": "20.00"}, format="json")
    assert sent.status_code == 200 and sent.json()["proposals"][0]["status"] == "PENDING"
    assert client.post(f"{base}/sales/", {"lender": "ATB", "price": "20"}).status_code == 400
    working_as(Game.objects.get(pk=game.pk), "CEO")  # IT is managed by the chief executive

    it_screen = client.get(f"{base}/it/").json()
    assert it_screen["capacity"] == "STANDARD" and not it_screen["down"]
    assert (
        client.post(f"{base}/it/", {"action": "respond", "response": "VENDOR"}).status_code == 400
    )
    raised = client.post(f"{base}/it/", {"action": "capacity", "level": "HIGH"}, format="json")
    assert raised.status_code == 200 and raised.json()["capacity"] == "HIGH"


@pytest.mark.django_db(transaction=True)
def test_the_office_shows_who_is_where_the_queue_and_the_systems(world: World) -> None:
    """P3.2: the 3D office is drawn from this, so it must follow the game."""
    owner = User.objects.create_user("player")
    game = controls.set_pause_rules(start_game(world, owner=owner), [], deadlines=False)
    client = APIClient()
    client.force_authenticate(owner)
    url = f"/api/v1/games/{game.pk}/office/"

    calm = client.get(url).json()
    assert [s["state"] for s in calm["staff"]] == ["IDLE"] * 3
    assert calm["systems"]["down"] is False and calm["queue"]["open"] == 0

    officer = Employee.objects.filter(organization=game.organization).order_by("pk")[1]
    controls.train_employee(game, officer.employee_number, "MATCH_REVIEW")
    it.start_outage(game, game.current_tick + 1, "Test outage.", lambda *a: None)
    busy = client.get(url).json()
    states = {s["number"]: s["state"] for s in busy["staff"]}
    assert states[officer.employee_number] == "AWAY"
    assert busy["systems"]["down"] is True and busy["systems"]["detail"] == "Test outage."

    # Once files are processed, the queue on the desks is the work items' own count.
    while controls.state(game).now.day < 7:
        game = controls.advance_by(game, "next_event")
    shown = client.get(url).json()
    items = WorkItem.objects.filter(organization=game.organization)
    assert shown["queue"]["open"] == items.filter(status=ItemStatus.OPEN).count()
    assert shown["queue"]["in_progress"] == sum(s["state"] == "WORKING" for s in shown["staff"])
    assert sum(shown["queue"]["by_type"].values()) == shown["queue"]["open"]
