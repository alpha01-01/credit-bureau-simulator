"""The economy as the bureau sees it: published indicators only (P3.12; PRD, Section 15).

The world's economy (``apps.world.generation.economy``) is the truth. The bureau reads
what is published: each month's inflation, policy rate, wage growth and growth in
activity, released at the start of the next month, and news of a stage beginning or a
shock. It never reads the world's stress index.

Costs follow the published prices: suppliers' bills, the landlord's renewal and the
contact centre move with the price index; the market for staff moves with the wage
index. Both are 1.0 when play begins and stay there until inflation begins.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from apps.world.models import EconomyMonth

from .models import Game

RULES = {
    "stage": "The economy moves through stages: Initial (costs and prices), then Intermediate "
    "(inflation, interest rates and wage pressure) from the sixth month of play, then Advanced "
    "(a business cycle and shocks) from the twelfth. Each stage's variables are set by rules "
    "from the world's seed (A-082).",
    "inflation": "Annual inflation follows its own path around a level set from the seed "
    "(8%-22%), moving a little each month, and jumps by 6 points in a shock. Suppliers' bills, "
    "rent renewals and the contact centre are priced at the published price index.",
    "policy_rate": "The Bank of Ghana's policy rate follows inflation: one point up for each "
    "point inflation runs above its usual level. Dearer credit means lenders lend less, so "
    "fewer applications reach the bureau.",
    "wages": "Wages grow with inflation plus a premium set from the seed (0%-4% a year). Staff "
    "compare their pay with the market for their role; candidates ask for market rates.",
    "growth": "Growth in economic activity falls as times get harder. In a shock it drops "
    "sharply: borrowers miss more payments, defaults rise, and lending falls.",
}


def _month_end_before(day: date) -> date:
    return day.replace(day=1) - timedelta(days=1)


def published(game: Game, today: date) -> list[EconomyMonth]:
    """The months published by ``today`` (each at the start of the next), oldest first."""
    return list(
        EconomyMonth.objects.filter(
            world=game.world, period__lte=_month_end_before(today)
        ).order_by("period")
    )


def _base(game: Game) -> EconomyMonth | None:
    """The last month before play began: the indices' starting point."""
    return (
        EconomyMonth.objects.filter(world=game.world, period__lt=game.clock_start)
        .order_by("-period")
        .first()
    )


def latest(game: Game, today: date) -> EconomyMonth | None:
    return (
        EconomyMonth.objects.filter(world=game.world, period__lte=_month_end_before(today))
        .order_by("-period")
        .first()
    )


def price_factor(game: Game, today: date) -> Decimal:
    """Prices now against when play began, as published."""
    return _factor(game, today, "price_index")


def wage_factor(game: Game, today: date) -> Decimal:
    return _factor(game, today, "wage_index")


def _factor(game: Game, today: date, field: str) -> Decimal:
    now, base = latest(game, today), _base(game)
    if now is None or base is None or not getattr(base, field):
        return Decimal("1")
    return (Decimal(str(getattr(now, field))) / Decimal(str(getattr(base, field)))).quantize(
        Decimal("0.0001")
    )


def priced(amount: Decimal, factor: Decimal) -> Decimal:
    return (amount * factor).quantize(Decimal("0.01"))


NEWS = {
    "INTERMEDIATE": ("ECONOMY_STAGE", "WARNING", "Inflation has arrived",
                     "Prices, interest rates and wages have begun to move. Costs will rise."),
    "ADVANCED": ("ECONOMY_STAGE", "WARNING", "The economy has entered its advanced stage",
                 "A business cycle now moves activity up and down, and shocks can strike."),
    "SHOCK": ("ECONOMIC_SHOCK", "CRITICAL", "The economy has taken a shock",
              "Growth has fallen sharply and inflation has jumped. Borrowers will miss more "
              "payments; expect defaults to rise and lending to fall."),
}  # fmt: skip


def month_start(game: Game, today: date, add: Any) -> None:
    """Last month's figures are published: news of a new stage or a shock."""
    month = latest(game, today)
    if month is None or month.period < game.clock_start:
        return
    for event in month.events or []:
        if event in NEWS:
            kind, severity, title, detail = NEWS[event]
            growth = f" Growth last month: {month.growth:.1%}." if month.growth is not None else ""
            add(kind, severity, title, detail + growth, {"screen": "economy", "params": {}})


def indicators(game: Game, today: date) -> dict[str, Any]:
    months = published(game, today)
    base = _base(game)
    play = [m for m in months if m.period >= game.clock_start]
    current = play[-1] if play else None
    staged = bool((game.world.config.get("economy") or {}).get("stages", False))
    return {
        "staged": staged,  # worlds made before P3.12 keep a still economy
        "stage": current.stage if current and current.stage != "HISTORY" else "INITIAL",
        "price_factor": str(price_factor(game, today)),
        "wage_factor": str(wage_factor(game, today)),
        "rules": RULES,
        "months": [
            {
                "period": m.period,
                "stage": m.stage,
                "inflation": m.inflation,
                "policy_rate": m.policy_rate,
                "growth": m.growth,
                "price_index": m.price_index / base.price_index if base else m.price_index,
                "wage_index": m.wage_index / base.wage_index if base else m.wage_index,
                "events": m.events or [],
            }
            for m in months[-24:]
        ],
    }
