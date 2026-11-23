"""P3.1 — Roles and workspaces.

Done when (Document 09): the player can switch between CEO and Data Operations;
each role sees only its own workspace and actions; the API refuses an action
outside the current role; a switch replays exactly (PRD criterion 13).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bureau.quality.models import CaseType
from apps.simulation import controls, roles
from apps.simulation.bridge import start_game
from apps.simulation.fingerprint import differences, fingerprint
from apps.simulation.models import Game
from apps.workitems.models import WorkItem
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import World


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world(db: None) -> World:
    g = build_world(61, "tiny")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


def _client(game: Game) -> APIClient:
    client = APIClient()
    assert game.owner is not None
    client.force_authenticate(game.owner)
    return client


def test_a_game_starts_with_the_chief_executive_who_keeps_the_company_decisions(
    world: World,
) -> None:
    game = start_game(world, owner=User.objects.create_user("player"))
    client, base = _client(game), f"/api/v1/games/{game.pk}"

    role = client.get(f"{base}/role/").json()
    assert role["current"]["code"] == "CEO" and role["current"]["ready"]
    assert {r["code"] for r in role["roles"]} == set(roles.ROLES)
    assert "queue" in role["current"]["screens"]  # the chief executive sees every screen

    # Department work is refused, with the reason and the way round it.
    refused = client.post(f"{base}/rejection-policy/", {"policy": "CORE"}, format="json")
    assert refused.status_code == 403
    assert "Head of Data Operations" in refused.json()["detail"]
    assert "switch role" in refused.json()["detail"]
    # The company's own decisions are the chief executive's.
    raised = client.post(f"{base}/it/", {"action": "capacity", "level": "HIGH"}, format="json")
    assert raised.status_code == 200


def test_taking_over_a_department_takes_half_an_hour_then_its_work_is_yours(
    world: World,
) -> None:
    game = start_game(world, owner=User.objects.create_user("player"))
    client, base = _client(game), f"/api/v1/games/{game.pk}"

    switched = client.post(f"{base}/role/", {"role": "DATA_OPERATIONS"}, format="json").json()
    current = switched["current"]
    assert current["code"] == "DATA_OPERATIONS" and not current["ready"]
    assert current["ready_at"]
    assert "queue" in current["screens"] and "staff" not in current["screens"]
    assert set(roles.SHARED_SCREENS) <= set(current["screens"])
    assert client.get(f"{base}/clock/").json()["role"]["code"] == "DATA_OPERATIONS"

    during = client.post(f"{base}/rejection-policy/", {"policy": "CORE"}, format="json")
    assert during.status_code == 403 and "taking over" in during.json()["detail"]

    client.post(f"{base}/clock/advance/", {"unit": "hour", "count": 1}, format="json")
    assert client.get(f"{base}/role/").json()["current"]["ready"]
    done = client.post(f"{base}/rejection-policy/", {"policy": "CORE"}, format="json")
    assert done.status_code == 200 and done.json()["policy"] == "CORE"

    # The chief executive's decisions are no longer the player's to take.
    hire = client.post(f"{base}/staff/", {"action": "hire", "candidate": 1}, format="json")
    assert hire.status_code == 403 and "Chief Executive" in hire.json()["detail"]

    # Switching needs a real role, and a different one.
    assert client.post(f"{base}/role/", {"role": "JANITOR"}).status_code == 400
    assert client.post(f"{base}/role/", {"role": "DATA_OPERATIONS"}).status_code == 400


def test_work_items_belong_to_the_department_that_decides_them() -> None:
    def item(kind: str) -> WorkItem:
        return WorkItem(item_type=kind)

    assert roles.owner_of("RESOLVE_ITEM", item(CaseType.MATCH_REVIEW)) == "DATA_OPERATIONS"
    assert roles.owner_of("RESOLVE_ITEM", item(CaseType.UNLOADABLE_TRIAGE)) == "DATA_OPERATIONS"
    assert roles.owner_of("RESOLVE_ITEM", item(CaseType.DISPUTE)) == "COMPLIANCE"
    assert roles.owner_of("SEND_PROPOSAL") == "SALES"
    assert roles.owner_of("ADVANCE") is None  # the clock is everyone's


def test_every_player_action_has_an_owner_or_is_shared() -> None:
    """A new action must be given to a role, or the API could never be asked for it."""
    source = Path(controls.__file__).read_text(encoding="utf-8")
    applied = set(re.findall(r'case "([A-Z_]+)":', source))
    assert len(applied) > 25
    for action in applied:
        roles.owner_of(action)  # raises for an action no role takes
    owned = [a for r in roles.ROLES.values() for a in r.actions if a != "RESOLVE_ITEM"]
    assert len(owned) == len(set(owned)), "an action belongs to one role only"


def test_role_switches_replay_exactly(world: World) -> None:
    original = start_game(world)
    original = controls.switch_role(original, "DATA_OPERATIONS")
    original = controls.advance_by(original, "hour", 2)
    original = controls.switch_role(original, "COMPLIANCE")
    original = controls.advance_by(original, "day")

    copy = controls.replay(original, start_game(world))
    assert (copy.role, copy.role_ready_tick) == (original.role, original.role_ready_tick)
    assert fingerprint(copy) == fingerprint(original), differences(copy, original)
