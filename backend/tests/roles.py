"""Test helper: work as a role at once (P3.1)."""

from __future__ import annotations

from apps.simulation import controls
from apps.simulation.models import Game


def working_as(game: Game, role: str) -> Game:
    """Switch role through the recorded action, then skip the changeover.

    Tests that drive department actions through the API use this; the changeover
    itself is tested in ``test_roles``. The changeover tick is not fingerprinted,
    so replays in those tests still match.
    """
    if game.role != role:
        game = controls.switch_role(game, role)
    Game.objects.filter(pk=game.pk).update(role_ready_tick=game.current_tick)
    game.role_ready_tick = game.current_tick
    return game
