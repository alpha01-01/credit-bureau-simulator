"""S8 — The API behind the game screens."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import World

PASSWORD = "test-only-not-a-real-password"  # noqa: S105 - test fixture


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture
def world(db: None) -> World:
    g = build_world(121, "tiny")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


@pytest.fixture
def player(db: None) -> User:
    return User.objects.create_user("player", password=PASSWORD)


def _signed_in(player: User) -> APIClient:
    client = APIClient(enforce_csrf_checks=True)
    client.get("/api/v1/auth/session/")
    token = client.cookies["csrftoken"].value
    response = client.post(
        "/api/v1/auth/login/",
        {"username": "player", "password": PASSWORD},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 200
    assert response.json() == {"authenticated": True, "username": "player"}
    client.credentials(HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
    return client


def test_sign_in_needs_the_csrf_token_and_the_right_password(player: User) -> None:
    client = APIClient(enforce_csrf_checks=True)
    assert client.get("/api/v1/auth/session/").json() == {"authenticated": False}
    # Without the token the login is refused.
    refused = client.post(
        "/api/v1/auth/login/", {"username": "player", "password": PASSWORD}, format="json"
    )
    assert refused.status_code == 403
    token = client.cookies["csrftoken"].value
    wrong = client.post(
        "/api/v1/auth/login/",
        {"username": "player", "password": "nope"},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert wrong.status_code == 400
    assert _signed_in(player).get("/api/v1/auth/session/").json()["username"] == "player"


def _new_game(client: APIClient, world: World, months: int = 2) -> dict[str, Any]:
    response = client.post(
        "/api/v1/games/", {"world": world.pk, "history_months": months}, format="json"
    )
    assert response.status_code == 201, response.content
    game: dict[str, Any] = response.json()
    return game


def test_a_new_established_game_is_prepared_and_listed(world: World, player: User) -> None:
    client = _signed_in(player)
    game = _new_game(client, world)
    # In tests, preparation runs in the request; in play it runs in the background.
    detail = client.get(f"/api/v1/games/{game['id']}/").json()
    assert detail["setup_status"] == "READY"
    assert detail["clock"]["date"] == "2027-01-04"
    assert [g["id"] for g in client.get("/api/v1/games/").json()] == [game["id"]]
    worlds = client.get("/api/v1/worlds/").json()
    assert worlds[0]["id"] == world.pk


def test_screens_show_the_bureau_after_a_few_days(world: World, player: User) -> None:
    client = _signed_in(player)
    game_id = _new_game(client, world)["id"]
    base = f"/api/v1/games/{game_id}"
    for _ in range(4):
        advanced = client.post(f"{base}/clock/advance/", {"unit": "day"}, format="json")
        assert advanced.status_code == 200

    dashboard = client.get(f"{base}/dashboard/").json()
    keys = {m["key"] for m in dashboard["metrics"]}
    assert {"revenue", "cash", "backlog", "hit_rate", "customers"} <= keys
    assert all(m["drill"]["screen"] for m in dashboard["metrics"])

    briefing = client.get(f"{base}/briefing/").json()
    assert {"files_received", "records", "work", "enquiries", "inbox"} <= set(briefing)

    submissions = client.get(f"{base}/submissions/").json()
    assert submissions
    detail = client.get(f"{base}/submissions/{submissions[0]['reference']}/").json()
    assert detail["files"] and detail["runs"][0]["reconciles"] is True

    customers = client.get(f"{base}/customers/").json()
    assert customers
    customer = client.get(f"{base}/customers/{customers[0]['reference']}/").json()
    assert customer["accounts"] and customer["accounts"][0]["observations"][0]["source"]
    by_name = client.get(f"{base}/customers/?q={customer['name'].split()[-1]}").json()
    assert customer["reference"] in [c["reference"] for c in by_name]

    ledger = client.get(f"{base}/ledger/?account=1010").json()
    assert ledger and all(
        any(line["account"].startswith("1010") for line in e["lines"]) for e in ledger
    )

    # The screens never reveal the world's truth.
    everything = str(dashboard) + str(briefing) + str(detail) + str(customer)
    for secret in ("correct", "risk_z", "health_z", "is_correct"):
        assert secret not in everything


def test_other_players_cannot_see_your_game(world: World, player: User) -> None:
    game_id = _new_game(_signed_in(player), world, months=0)["id"]
    User.objects.create_user("rival", password=PASSWORD)
    rival = APIClient()
    rival.login(username="rival", password=PASSWORD)
    assert rival.get(f"/api/v1/games/{game_id}/dashboard/").status_code == 404
    assert rival.get("/api/v1/games/").json() == []
