"""P2.10 — Pressure and failure.

Done when (Document 08): each hard failure can be reached deliberately, is
preceded by its warnings, and shows the path back.

* Insolvency: pay the team far more than the bureau earns. Cash falls below a
  month's costs, the overdraft is used, creditors serve notice, and 21 days later
  the bureau is insolvent. Replayed to the creditors' notice, the same bureau
  that cuts pay and asks the shareholders for capital is saved.
* Licence revoked: findings for missed dispute deadlines pile up (here recorded
  directly, as if the player left disputes unsettled); the regulator climbs its
  ladder one warning at a time to revocation.
* Removed by the board: a bureau that lets in no data and pays its staff a
  pittance loses the board's confidence at two quarterly reviews in a row.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.org.models import Employee
from apps.simulation import controls, solvency
from apps.simulation.bridge import start_game
from apps.simulation.engine import ClockError
from apps.simulation.fingerprint import fingerprint
from apps.simulation.models import (
    BoardReview,
    Game,
    GameStatus,
    Notice,
    RegulatorFinding,
    SolvencyState,
)
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import World


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world(db: None) -> World:
    g = build_world(81, "small")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


def _quiet(game: Game) -> Game:
    return controls.set_pause_rules(game, [], deadlines=False)


def _kinds(game: Game, kinds: list[str]) -> list[str]:
    return list(
        Notice.objects.filter(game=game, kind__in=kinds)
        .order_by("tick", "pk")
        .values_list("kind", flat=True)
    )


def _api(game: Game) -> APIClient:
    client = APIClient()
    assert game.owner is not None
    client.force_authenticate(game.owner)
    return client


@pytest.mark.django_db(transaction=True)
@pytest.mark.slow
def test_insolvency_is_reached_through_its_warnings_and_can_be_turned_back(world: World) -> None:
    owner = User.objects.create_user("player")
    game = _quiet(start_game(world, owner=owner))
    for e in Employee.objects.filter(organization=game.organization).order_by("employee_number"):
        controls.set_salary(game, e.employee_number, Decimal("300000"))

    marked = None
    while game.status != GameStatus.ENDED:
        game = controls.advance_by(game, "day")
        stage = SolvencyState.objects.get(game=game).stage
        if stage == "CREDITORS" and marked is None:
            marked = controls.checkpoint(game, "creditors")
            health = _api(game).get(f"/api/v1/games/{game.pk}/health/").json()
            path = next(p for p in health["failures"] if p["key"] == "INSOLVENT")
            assert path["next"] == "Insolvency" and "Creditors' deadline" in path["detail"]
            assert "shareholders" in path["path_back"]
        assert controls.state(game).now.year == 2027, "never reached insolvency"

    path = ["CASH_LOW", "OVERDRAFT_USED", "CREDITORS_NOTICE", "GAME_OVER"]
    seen = _kinds(game, path)
    print("insolvency path:", seen, "ended", controls.state(game).now.date())  # noqa: T201
    assert [k for k in path if k in seen] == path  # every warning came
    assert seen == sorted(seen, key=path.index)  # and in order
    assert game.ended_reason == "INSOLVENT"
    notice = Notice.objects.get(game=game, kind="CREDITORS_NOTICE")
    deadline = SolvencyState.objects.get(game=game).creditors_deadline
    assert deadline is not None
    over = Notice.objects.get(game=game, kind="GAME_OVER")
    assert over.sim_time.date() - notice.sim_time.date() >= timedelta(days=21)
    with pytest.raises(ClockError):
        controls.advance_by(game, "day")  # the game is over
    with pytest.raises(ClockError):
        controls.resume(game)

    # The path back: the same bureau at the creditors' notice cuts pay and raises capital.
    assert marked is not None
    saved = controls.replay_to(marked, start_game(world, owner=owner))
    for e in Employee.objects.filter(organization=saved.organization).order_by("employee_number"):
        controls.set_salary(saved, e.employee_number, Decimal("8000"))
    grant = controls.request_funding(saved, solvency.MAX_FUNDING)
    print("funding:", grant.granted, grant.reason)  # noqa: T201
    assert grant.granted
    for _ in range(25):
        saved = controls.advance_by(saved, "day")
    assert saved.status != GameStatus.ENDED
    assert Notice.objects.filter(game=saved, kind="CREDITORS_WITHDRAWN").exists()
    assert SolvencyState.objects.get(game=saved).stage != "CREDITORS"
    with pytest.raises(ClockError):
        controls.request_funding(saved, Decimal("100000"))  # once a quarter


@pytest.mark.django_db(transaction=True)
def test_the_regulator_climbs_to_revocation_one_warning_at_a_time(world: World) -> None:
    owner = User.objects.create_user("player")
    game = _quiet(start_game(world, owner=owner))
    game = controls.advance_by(game, "hour")
    titles = []
    for total in (1, 3, 5, 7, 9):
        at = controls.state(game).now
        have = RegulatorFinding.objects.filter(game=game).count()
        RegulatorFinding.objects.bulk_create(
            RegulatorFinding(
                game=game,
                kind="MISSED_DISPUTE_DEADLINE",
                reference=f"T{n}",
                raised_at=at,
                detail="A dispute left past its deadline.",
            )
            for n in range(have + 1, total + 1)
        )
        if total == 7:
            health = _api(game).get(f"/api/v1/games/{game.pk}/health/").json()
            path = next(p for p in health["failures"] if p["key"] == "LICENCE_REVOKED")
            assert path["current"] == "Financial penalty"
            assert "six months" in path["path_back"]
        game = controls.advance_by(game, "day")
        game = controls.advance_by(game, "hour")  # the regulator looks in the morning
        notice = Notice.objects.filter(game=game, kind="REGULATOR_LADDER").order_by("-pk").first()
        assert notice is not None
        titles.append(notice.title)
        if total < 9:
            assert "fall away after six months" in notice.detail  # the way back, every time
    print("ladder:", titles)  # noqa: T201
    assert titles[0].startswith("Concern letter") and titles[-1].startswith("Licence revoked")
    assert game.status == GameStatus.ENDED and game.ended_reason == "LICENCE_REVOKED"
    assert Notice.objects.filter(game=game, kind="GAME_OVER").exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.slow
def test_a_board_without_confidence_twice_removes_the_management(world: World) -> None:
    careful = _quiet(start_game(world))
    careless = _quiet(start_game(world))
    careless.organization.institutions.update(is_active=False)  # no data comes in
    for e in Employee.objects.filter(organization=careless.organization):
        controls.set_salary(careless, e.employee_number, Decimal("500"))

    for game in (careful, careless):
        while game.status != GameStatus.ENDED and BoardReview.objects.filter(game=game).count() < 2:
            game = controls.advance_by(game, "next_event")
        for r in BoardReview.objects.filter(game=game).order_by("period"):
            print(game.pk, r.period, r.confidence, r.verdict, r.parts)  # noqa: T201
        game.refresh_from_db()

    careful.refresh_from_db()
    careless.refresh_from_db()
    assert careful.status != GameStatus.ENDED
    assert BoardReview.objects.filter(game=careful).first().verdict == "CONFIDENT"  # type: ignore[union-attr]
    verdicts = list(
        BoardReview.objects.filter(game=careless)
        .order_by("period")
        .values_list("verdict", flat=True)
    )
    assert verdicts == ["NO_CONFIDENCE", "REMOVED"]
    assert _kinds(careless, ["BOARD_NO_CONFIDENCE", "GAME_OVER"]) == [
        "BOARD_NO_CONFIDENCE",
        "GAME_OVER",
    ]
    assert careless.ended_reason == "REMOVED_BY_BOARD"
    warning = Notice.objects.get(game=careless, kind="BOARD_NO_CONFIDENCE")
    assert "data quality" in warning.detail and "Bureau Health" in warning.detail

    # Replays agree, ending included.
    copy = start_game(world)
    copy.organization.institutions.update(is_active=False)  # as in the original
    copy = controls.replay(careless, copy)
    assert fingerprint(copy) == fingerprint(careless)
