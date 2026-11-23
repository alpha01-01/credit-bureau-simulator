"""P2.11 — Learning: missions, debriefs, the Handbook, assistance.

Done when (Document 08): a new player completes M1-M6 without outside help in
about two hours. That is a playtest with people; what can be tested here is that
every mission can be completed from what the screens show, in order, each ending
in a debrief, and how much game time the campaign takes.

A scripted player works through the API only: it reads the mission, finds the
answer on the screen the mission points to, and decides work items by the
recommendation the assistance toggle offers (a learner's first steps).
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bureau.quality.models import CaseType
from apps.simulation import controls
from apps.simulation.bridge import start_game
from apps.simulation.clock import TICKS_PER_DAY
from apps.simulation.fingerprint import fingerprint
from apps.simulation.models import Game, MissionState, Notice
from apps.standards.handbook import BY_KEY, ENTRIES
from apps.workitems.models import ItemStatus, WorkItem
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import World

MAX_STEPS = 400


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world(db: None) -> World:
    g = build_world(81, "small")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


class Player:
    """Plays through the API, as the browser would."""

    def __init__(self, game: Game) -> None:
        self.game = game
        self.client = APIClient()
        assert game.owner is not None
        self.client.force_authenticate(game.owner)
        self.base = f"/api/v1/games/{game.pk}"

    def get(self, path: str) -> Any:
        response = self.client.get(f"{self.base}{path}")
        assert response.status_code == 200, (path, response.content)
        return response.json()

    def post(self, path: str, body: dict[str, Any]) -> Any:
        return self.client.post(f"{self.base}{path}", body, format="json")

    def mission(self) -> dict[str, Any] | None:
        rows = self.get("/missions/")["missions"]
        return next((m for m in rows if m["status"] == "CURRENT"), None)

    def answer(self, code: str, value: Any) -> bool:
        response = self.post("/missions/", {"action": "answer", "code": code, "value": str(value)})
        assert response.status_code == 200, response.content
        return bool(response.json()["last_answer"]["right"])

    def decide(self, item_type: str, count: int) -> int:
        """Decide open items of a type yourself, following the recommendation."""
        decided = 0
        for row in self.get("/work-items/"):  # waiting or in someone's hands
            if decided >= count or row["type"] != item_type or row["status"] == "DONE":
                continue
            item = self.get(f"/work-items/{row['number']}/")
            recommended = item["assist"]["recommendation"]
            assert item["assist"]["estimated_accuracy"]["share"] > 0
            decision = recommended["decision"] if recommended else item["allowed_decisions"][0]
            response = self.post(f"/work-items/{row['number']}/resolve/", {"decision": decision})
            assert response.status_code == 200, response.content
            decided += 1
        return decided

    def advance(self, unit: str = "next_event") -> None:
        response = self.post("/clock/advance/", {"unit": unit, "count": 1})
        assert response.status_code == 200, response.content
        self.game.refresh_from_db()


def _reference(text: str) -> str:
    """The submission a question is about, as written in it."""
    found = re.search(r"SUB-[0-9]+-[A-Z]+-[0-9]+", text)
    assert found, text
    return found.group(0)


def _solve(player: Player, mission: dict[str, Any]) -> None:
    """Do what the current mission asks, as far as the game allows now."""
    code = mission["code"]
    question = mission.get("question")
    if code == "M2":
        player.decide(CaseType.UNLOADABLE_TRIAGE, 3)
        subs = player.get("/submissions/")
        rows = subs["submissions"] if isinstance(subs, dict) else subs
        if not any(m["done"] for m in mission["objectives"][1:2]):
            for sub in rows:
                detail = player.get(f"/submissions/{sub['reference']}/")
                if detail["runs"] and detail["runs"][-1]["unloadable"]:
                    sent = player.post(f"/submissions/{sub['reference']}/feedback/", {})
                    assert sent.status_code in (200, 201), sent.content
                    break
        if not mission["objectives"][2]["done"]:
            relaxed = player.post("/rules/", {"override": {"code": "F006", "setting": "WARNING"}})
            assert relaxed.status_code == 200, relaxed.content
    elif code == "M3":
        player.decide(CaseType.MATCH_REVIEW, 5)
    if not question or not question["ready"] or question["answered"]:
        return
    if code == "M1":
        reference = _reference(question["text"])
        run = player.get(f"/submissions/{reference}/")["runs"][-1]
        assert player.answer(code, run["unloadable"] + 1) is False  # a wrong answer first
        assert player.answer(code, run["unloadable"])
    elif code == "M4":
        reference = _reference(question["text"])
        run = player.get(f"/submissions/{reference}/")["runs"][-1]
        assert player.answer(code, run["accounts_created"])
    elif code == "M5":
        dashboard = player.get("/dashboard/")
        rate = next(m["value"] for m in dashboard["metrics"] if m["key"] == "hit_rate")
        assert player.answer(code, f"{Decimal(str(rate)) * 100:.1f}%")
    elif code == "M6":
        income = player.get("/finance/")["income_last_month"]["net_profit"]
        assert player.answer(code, f"GHS {income}")


@pytest.mark.django_db(transaction=True)
@pytest.mark.slow
def test_a_player_completes_the_campaign_from_what_the_screens_show(world: World) -> None:
    owner = User.objects.create_user("learner")
    game = controls.set_pause_rules(start_game(world, owner=owner), [], deadlines=False)
    game = controls.set_matching_tooling(game, "STANDARD")  # near matches go to review:
    game = controls.set_matching_thresholds(game, 0.99, 0.6)  # a queue to learn from
    player = Player(game)
    for name in ("assist_accuracy", "assist_recommend"):
        assert player.post("/assistance/", {"name": name, "on": True}).status_code == 200

    order: list[str] = []
    for _ in range(MAX_STEPS):
        mission = player.mission()
        if mission is None:
            break
        if not order or order[-1] != mission["code"]:
            order.append(mission["code"])
        _solve(player, mission)
        if player.mission() == mission or (player.mission() or {}).get("code") == mission["code"]:
            player.advance()
    else:
        items = WorkItem.objects.filter(organization=game.organization)
        by_type = {
            t: (
                items.filter(item_type=t).count(),
                items.filter(item_type=t, resolved_by="PLAYER").count(),
            )
            for t in (CaseType.MATCH_REVIEW, CaseType.UNLOADABLE_TRIAGE)
        }
        pytest.fail(
            f"The campaign did not finish; stuck at {order[-1]}: {by_type}, tick {game.current_tick}"
        )

    assert order == ["M1", "M2", "M3", "M4", "M5", "M6"]
    states = {s.code: s for s in MissionState.objects.filter(game=game)}
    for code in order:
        debrief = states[code].debrief
        assert debrief["headline"] and debrief["figures"] and debrief["lessons"], code
    assert Notice.objects.filter(game=game, kind="MISSION_COMPLETE").count() == 6
    days = game.current_tick / TICKS_PER_DAY
    print(f"campaign: {days:.1f} working days of game time")  # noqa: T201
    for code in order:
        print(code, states[code].debrief["headline"])  # noqa: T201
    for mission in player.get("/missions/")["missions"]:
        assert all(key in BY_KEY for key in mission["handbook"])  # every link resolves

    # Replayed, answers and all, the campaign ends the same.
    copy = controls.replay(game, start_game(world, owner=owner))
    assert fingerprint(copy) == fingerprint(game)


@pytest.mark.django_db(transaction=True)
def test_assistance_toggles_and_the_handbook(world: World) -> None:
    owner = User.objects.create_user("learner")
    game = controls.set_pause_rules(start_game(world, owner=owner), [], deadlines=False)
    player = Player(game)
    off = player.get("/assistance/")
    assert off == {
        "assist_accuracy": False,
        "assist_recommend": False,
        "assist_extended_deadlines": False,
        "pause_all": False,
    }
    on = player.post("/assistance/", {"name": "pause_all", "on": True}).json()
    assert on["pause_all"]
    game.refresh_from_db()
    assert sorted(game.pause_severities) == ["CRITICAL", "INFO", "WARNING"]
    assert player.post("/assistance/", {"name": "nonsense", "on": True}).status_code == 400

    # Extended deadlines: an item opened now is due ten working days on, not five.
    player.post("/assistance/", {"name": "assist_extended_deadlines", "on": True})
    controls.set_pause_rules(game, [], deadlines=False)
    while not WorkItem.objects.filter(organization=game.organization).exists():
        game = controls.advance_by(game, "next_event")
    item = WorkItem.objects.filter(organization=game.organization).order_by("item_number").first()
    assert item is not None and item.due_tick is not None
    assert item.due_tick - item.created_tick >= 10 * TICKS_PER_DAY - TICKS_PER_DAY

    # Without the toggles, items carry no assistance.
    open_item = WorkItem.objects.filter(
        organization=game.organization, status=ItemStatus.OPEN
    ).first()
    if open_item is not None:
        assert "assist" not in player.get(f"/work-items/{open_item.item_number}/")

    # The campaign is optional.
    assert player.post("/missions/", {"action": "campaign", "on": False}).status_code == 200
    assert player.mission() is None

    handbook = player.get("/handbook/")
    assert "not legal advice" in handbook["disclaimer"]
    assert len(handbook["entries"]) == len(ENTRIES)
    dispute = next(e for e in handbook["entries"] if e["key"] == "dispute")
    assert dispute["regulatory"] and not dispute["reviewed"]
    assert any("L.I. 2394" in c["instrument"] for c in dispute["citations"])
    # Every regulatory entry cites something, and nothing claims a review it has not had.
    for entry in handbook["entries"]:
        if entry["regulatory"]:
            assert entry["citations"]
        assert not entry["reviewed"]
