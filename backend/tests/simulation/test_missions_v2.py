"""P3.14 — the workspace missions W1-W5 and Handbook v2.

Done when (Document 09): a scripted player completes M7, M8 and each new mission from
what the screens show; every regulatory citation is either confirmed by the owner or
marked TO_CONFIRM. M7 and M8 are played at the end of the campaign in
``test_learning``; the workspace missions are played here, on a bureau with six
months of history, through the API only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from apps.accounts.models import User
from apps.simulation import controls, missions
from apps.simulation.bridge import start_game
from apps.simulation.fingerprint import differences, fingerprint
from apps.simulation.models import Game, MissionState, Notice
from apps.standards.compliance_rules import RULES
from apps.standards.handbook import BY_KEY, DSC, ENTRIES
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import World

from .test_learning import Player

MAX_STEPS = 300


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


def _world() -> World:
    g = build_world(61, "tiny")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


class Workspaces(Player):
    """A player who works through the workspace missions, one department at a time."""

    def open(self) -> dict[str, dict[str, Any]]:
        rows = self.get("/missions/")["missions"]
        return {m["code"]: m for m in rows if m["track"] == "WORKSPACE" and m["status"] != "DONE"}

    def work_as(self, role: str) -> bool:
        """Switch role if need be; True once the role is ready to act."""
        current = self.get("/role/")["current"]
        if current["code"] != role:
            switched = self.post("/role/", {"role": role})
            assert switched.status_code == 200, switched.content
            return False
        return bool(current["ready"])

    def ok(self, path: str, body: dict[str, Any]) -> Any:
        response = self.post(path, body)
        assert response.status_code == 200, (path, body, response.content)
        return response.json()

    def answer_ready(self, mission: dict[str, Any], value: Any) -> None:
        q = mission["question"]
        if q and q["ready"] and not q["answered"]:
            assert self.answer(mission["code"], value), (mission["code"], value)


def _w1(p: Workspaces, m: dict[str, Any]) -> None:
    if not p.work_as("DATA_ANALYTICS"):
        return
    oldest = p.get("/analytics/")["vintages"][0]["default_rate_so_far"]
    p.answer_ready(m, f"{oldest * 100:.1f}%")


def _w2(p: Workspaces, m: dict[str, Any]) -> None:
    if not p.work_as("DATA_ANALYTICS"):
        return
    listing = p.get("/scorecards/")
    if not listing["models"]:
        window = next(w for w in listing["options"]["windows"] if w["observation_dates"])
        for term in [t["code"] for t in listing["options"]["terms"]]:  # "or another term"
            features = [  # the recommended ones; for one scorecard for all, every allowed one
                f["name"]
                for f in listing["options"]["features"]
                if term in f["recommended_for"] or (term == "ALL" and not f["restricted"])
            ]
            built = p.post("/scorecards/", {"action": "build", "term": term,
                                            "window": window["months"], "features": features,
                                            "observation": window["observation_dates"][0]})  # fmt: skip
            if built.status_code == 200:
                return
            assert "Too little data" in built.json()["detail"], built.content
        pytest.fail("No term has enough data for a scorecard")
    first = min(listing["models"], key=lambda x: x["number"])
    p.answer_ready(m, f"{first['holdout']['gini']:.3f}")


def _w3(p: Workspaces, m: dict[str, Any]) -> None:
    if not p.work_as("COMPLIANCE"):
        return
    screen = p.get("/compliance/")
    if not screen["consent_checks"]:
        for month in screen["sample_months"]:  # a month in which someone enquired
            for subscriber in screen["subscribers"]:
                body = {"action": "sample", "subscriber": subscriber["code"], "month": month,
                        "size": screen["sample_sizes"][-1]}  # fmt: skip
                asked = p.post("/compliance/", body)
                if asked.status_code == 200:
                    return
                assert "made no enquiries" in asked.json()["detail"], asked.content
        return  # nobody has enquired yet: wait
    first = min(screen["consent_checks"], key=lambda c: c["number"])
    if first["answered"]:
        p.answer_ready(m, len(first["missing"]))


def _w4(p: Workspaces, m: dict[str, Any]) -> None:
    if not p.work_as("FINANCE"):
        return
    bills = p.get("/finance/bills/")
    if not m["objectives"][0]["done"]:
        waiting = [b for b in bills["bills"] if b["status"] == "RECEIVED"]
        if waiting:
            p.ok("/finance/bills/", {"action": "approve", "number": waiting[0]["number"]})
        elif float(bills["approval_limit"]) > 0:  # every bill to come waits for the head
            p.ok("/finance/bills/", {"action": "limit", "amount": "0"})
    if not m["objectives"][1]["done"]:
        statement = p.get("/finance/bank/")["statement"]
        if statement is None or statement["reconciled_at"]:
            return
        period = statement["period"]
        for line in statement["unrecorded"]:
            if line["status"] != "OPEN":
                continue
            posted = p.post("/finance/bank/", {"action": "post", "period": period,
                                               "line": line["line"]})  # fmt: skip
            if posted.status_code != 200:  # nothing in the books explains it: ask the bank
                p.ok("/finance/bank/", {"action": "query", "period": period, "line": line["line"]})
        p.ok("/finance/bank/", {"action": "complete", "period": period})


def _w5(p: Workspaces, m: dict[str, Any]) -> None:
    if not p.work_as("SALES"):
        return
    sales = p.get("/sales/")
    researched = [x for x in sales["prospects"] if x["research"]]
    if not researched:
        p.ok("/sales/", {"action": "research", "lender": sales["prospects"][0]["code"]})
        return
    found = researched[0]["research"]["findings"]
    if found is None:
        return
    p.answer_ready(m, found["volume"])
    if not m["objectives"][1]["done"]:
        p.ok("/sales/", {"lender": researched[0]["code"], "price": sales["list_price"]})


SOLVERS = {"W1": _w1, "W2": _w2, "W3": _w3, "W4": _w4, "W5": _w5}


@pytest.mark.django_db(transaction=True)
@pytest.mark.slow
def test_a_player_completes_each_workspace_mission_from_what_the_screens_show() -> None:
    world = _world()
    owner = User.objects.create_user("analyst")
    game = controls.set_pause_rules(
        start_game(world, owner=owner, history_months=6), [], deadlines=False
    )
    assert game.campaign
    player = Workspaces(game)
    assert set(player.open()) == {"W1", "W2", "W3", "W4", "W5"}  # open together, from the start

    for _ in range(MAX_STEPS):
        still = player.open()
        if not still:
            break
        code = min(still)  # one department at a time
        SOLVERS[code](player, still[code])
        if player.open() == still:  # nothing more to do now: let time pass
            player.advance()
    else:
        pytest.fail(f"Stuck: {sorted(player.open())} still open at tick {player.game.current_tick}")

    game = Game.objects.get(pk=game.pk)
    states = {s.code: s for s in MissionState.objects.filter(game=game, code__startswith="W")}
    finished = sorted(states, key=lambda c: (states[c].completed_tick, c))
    assert sorted(finished) == ["W1", "W2", "W3", "W4", "W5"]
    print("completed in order", finished, "by tick", game.current_tick)  # noqa: T201
    for code in finished:
        debrief = states[code].debrief
        assert debrief["headline"] and debrief["figures"] and debrief["lessons"], code
        print(code, debrief["headline"])  # noqa: T201
    assert Notice.objects.filter(game=game, kind="MISSION_COMPLETE").count() == 5
    # The campaign is not held up by them: M1 is still the campaign's current mission.
    now = missions.current(game)
    assert now is not None and now.code == "M1"

    copy = controls.replay(game, start_game(world, owner=owner, history_months=6))
    assert fingerprint(copy) == fingerprint(game), differences(copy, game)


def test_handbook_v2_covers_every_mission_and_marks_what_is_unconfirmed() -> None:
    # Every mission's reading resolves, and every concept the new missions teach is in v2.
    for mission in missions.MISSIONS:
        assert all(key in BY_KEY for key in mission.handbook), mission.code
    new = {k for m in missions.MISSIONS if m.code in ("M7", "M8") or m.track == "WORKSPACE"
           for k in m.handbook}  # fmt: skip
    assert {BY_KEY[k].added for k in new} <= {"v1", "v2"}
    assert sum(e.added == "v2" for e in ENTRIES) >= 30
    assert len({e.key for e in ENTRIES}) == len(ENTRIES)

    # Every regulatory citation is confirmed by the owner or marked TO_CONFIRM. None has
    # been confirmed yet (D14): only the Data Standards manuals are, as our own references.
    for entry in ENTRIES:
        if entry.regulatory:
            assert entry.citations, entry.key
            assert not entry.reviewed, entry.key
        for c in entry.citations:
            assert c.status in ("CONFIRMED", "TO_CONFIRM"), entry.key
            if c.status == "CONFIRMED":
                assert c.instrument == DSC, (entry.key, c.instrument)
    for rule in RULES.values():
        assert rule.status == "TO_CONFIRM", rule.code
