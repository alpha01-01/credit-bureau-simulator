"""Scenarios and difficulty (P3.13; PRD Sections 4 and 18; Document 07, Section 12).

A **scenario** is where the bureau starts:

* **Established**: an operating bureau with its providers, subscribers, team and history
  (the campaign's missions are written for it).
* **Startup**: capital and nothing else. The player rents an office, sets up IT, hires
  the first team, onboards providers, develops the consumer report and signs the first
  subscribers (``startup``).
* **Sandbox**: free play on an established bureau with the parameters set by hand: the
  world's size, the starting cash, how good the providers' data is, and the economy.

A **difficulty** is a named parameter set. It changes resources, costs, deadlines, the
economy and how severe the consequences are, never the rules: the law's deadlines,
penalties and the business logic are the same at every level. Assistance (estimated
accuracy, recommendations, extended deadlines) is set separately (Document 07, 12.2).

ASSUMPTION A-083 (the values; to be tuned in P3.15's balancing):

=========================  ==========  ============  ==========
                           Beginner    Intermediate  Expert
=========================  ==========  ============  ==========
Starting cash              +500,000    as set up     -500,000
Supplier prices            x0.85       x1.00         x1.15
Hosting suspended after    15 days     10 days       5 days
Work items due in          7 days      5 days        4 days
Overdraft agreed           750,000     500,000       300,000
Board removes you after    3 reviews   2 reviews     1 review
Economy                    Gentle      Standard      Harsh
=========================  ==========  ============  ==========

(Days are working days; reviews are reviews in a row with no confidence.) An
established bureau gets the difference as new capital from its shareholders, or pays
it out to them as a dividend, the day before play; a startup's capital is
GHS 2,000,000 plus the difference.

The economy belongs to the world, which every game in it shares: a game whose
difficulty asks for another economy is played in a world of the same seed and size
made with that economy (its history is the same; only play months differ).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from django.db import transaction

from apps.finance.events import balance, capital_injection, dividend_paid
from apps.finance.ledger import BANK
from apps.world.generation import build_world
from apps.world.generation.advance import stored_economy
from apps.world.generation.config import GENERATOR_VERSION, SCALES, EconomyModel
from apps.world.generation.persist import write_world
from apps.world.models import World

from .models import Game

ESTABLISHED, STARTUP, SANDBOX = "ESTABLISHED", "STARTUP", "SANDBOX"
SCENARIOS = {
    ESTABLISHED: (
        "Established bureau",
        "Run an operating bureau: five providers, three subscribers, a team, a year of data. "
        "The guided missions are written for it.",
    ),
    STARTUP: (
        "Startup bureau",
        "Start with capital and nothing else: rent an office, set up IT, hire the first team, "
        "onboard providers, build the database from their first files, develop the report "
        "and sign the first subscribers.",
    ),
    SANDBOX: (
        "Sandbox",
        "Free play on an established bureau, with the world's size, the starting cash, the "
        "providers' data quality and the economy set by hand.",
    ),
}

BEGINNER, INTERMEDIATE, EXPERT, CUSTOM = "BEGINNER", "INTERMEDIATE", "EXPERT", "CUSTOM"
STARTUP_CAPITAL = Decimal("2000000.00")
MAX_PROVIDER_QUALITY = 4

# The economy's settings by name (P3.12's model). Every one keeps the world's history.
ECONOMIES: dict[str, tuple[str, dict[str, Any]]] = {
    "GENTLE": (
        "Gentle: inflation from the twelfth month of play, cycles from the twenty-fourth, "
        "no shocks, and inflation of 6-12%",
        {"intermediate_from": 12, "advanced_from": 24, "shocks": False,
         "inflation_range": (0.06, 0.12)},
    ),
    "STANDARD": (
        "Standard: inflation from the sixth month of play, cycles and a shock from the twelfth",
        {},
    ),
    "HARSH": (
        "Harsh: inflation from the third month of play, cycles and a bigger shock from the "
        "sixth",
        {"intermediate_from": 3, "advanced_from": 6, "cycle_amplitude": 0.35,
         "shock_range": (1.4, 2.0)},
    ),
    "INTERMEDIATE_NOW": (
        "Inflation from the first month of play; cycles and a shock from the twelfth",
        {"intermediate_from": 1, "advanced_from": 12},
    ),
    "ADVANCED_NOW": (
        "Everything from the first month of play: inflation, cycles, and a shock within the "
        "first year",
        {"intermediate_from": 1, "advanced_from": 1},
    ),
    "STILL": (
        "Still: prices, rates and wages never move (as in worlds made before the economy "
        "had stages)",
        {"stages": False},
    ),
}  # fmt: skip


@dataclass(frozen=True)
class Parameters:
    cash_adjustment: Decimal
    cost_factor: Decimal
    supplier_patience_days: int
    work_item_days: int
    overdraft_limit: Decimal
    board_patience: int
    economy: str
    provider_quality: int = 0
    starting_cash: Decimal | None = None  # Sandbox: the bank balance when play begins
    scale: str | None = None  # Sandbox: the world's size

    def as_json(self) -> dict[str, Any]:
        return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in asdict(self).items()}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Parameters:
        base = DIFFICULTIES[INTERMEDIATE][1]
        if not data:
            return base
        values = {**base.as_json(), **data}
        return cls(
            cash_adjustment=Decimal(values["cash_adjustment"]),
            cost_factor=Decimal(values["cost_factor"]),
            supplier_patience_days=int(values["supplier_patience_days"]),
            work_item_days=int(values["work_item_days"]),
            overdraft_limit=Decimal(values["overdraft_limit"]),
            board_patience=int(values["board_patience"]),
            economy=str(values["economy"]),
            provider_quality=int(values["provider_quality"]),
            starting_cash=(
                Decimal(values["starting_cash"]) if values["starting_cash"] is not None else None
            ),
            scale=values["scale"],
        )


DIFFICULTIES: dict[str, tuple[str, Parameters]] = {
    BEGINNER: (
        "More cash, lower costs, more forgiving deadlines, a gentle economy, and a patient "
        "board.",
        Parameters(Decimal("500000.00"), Decimal("0.85"), 15, 7, Decimal("750000.00"), 3,
                   "GENTLE"),
    ),
    INTERMEDIATE: (
        "Realistic costs and deadlines, an economy that brings inflation and then a shock.",
        Parameters(Decimal("0.00"), Decimal("1.00"), 10, 5, Decimal("500000.00"), 2,
                   "STANDARD"),
    ),
    EXPERT: (
        "Tighter cash, dearer suppliers, strict deadlines, a harsh economy, and a board that "
        "removes you after one bad review.",
        Parameters(Decimal("-500000.00"), Decimal("1.15"), 5, 4, Decimal("300000.00"), 1,
                   "HARSH"),
    ),
}  # fmt: skip


class ScenarioError(ValueError):
    pass


def resolve(scenario: str, difficulty: str, overrides: dict[str, Any] | None = None) -> Parameters:
    """The parameters for a new game: the difficulty's, with a Sandbox's own settings."""
    if scenario not in SCENARIOS:
        raise ScenarioError(f"{scenario!r} is not a scenario")
    if difficulty not in DIFFICULTIES:
        raise ScenarioError(f"{difficulty!r} is not a difficulty")
    params = DIFFICULTIES[difficulty][1]
    overrides = {k: v for k, v in (overrides or {}).items() if v not in (None, "")}
    if not overrides:
        return params
    if scenario != SANDBOX:
        raise ScenarioError("Only a Sandbox game takes settings of its own")
    changes: dict[str, Any] = {}
    if "starting_cash" in overrides:
        cash = Decimal(str(overrides["starting_cash"]))
        if not Decimal("0") <= cash <= Decimal("20000000"):
            raise ScenarioError("Starting cash must be between GHS 0 and GHS 20,000,000")
        changes["starting_cash"] = cash.quantize(Decimal("0.01"))
    if "provider_quality" in overrides:
        quality = int(overrides["provider_quality"])
        if not 0 <= quality <= MAX_PROVIDER_QUALITY:
            raise ScenarioError(f"Provider quality must be 0 to {MAX_PROVIDER_QUALITY}")
        changes["provider_quality"] = quality
    if "economy" in overrides:
        if overrides["economy"] not in ECONOMIES:
            raise ScenarioError(f"{overrides['economy']!r} is not an economy")
        changes["economy"] = str(overrides["economy"])
    if "scale" in overrides:
        if overrides["scale"] not in SCALES:
            raise ScenarioError(f"{overrides['scale']!r} is not a world size")
        changes["scale"] = str(overrides["scale"])
    unknown = set(overrides) - {"starting_cash", "provider_quality", "economy", "scale"}
    if unknown:
        raise ScenarioError(f"Unknown settings: {', '.join(sorted(unknown))}")
    return replace(params, **changes)


def parameters(game: Game) -> Parameters:
    """The game's parameters (games begun before P3.13 are Intermediate)."""
    return Parameters.from_json(game.parameters or {})


def cost(game: Game, amount: Decimal) -> Decimal:
    """A supplier's price at this game's difficulty."""
    return (amount * parameters(game).cost_factor).quantize(Decimal("0.01"))


# --- Worlds -------------------------------------------------------------------------------


def economy_model(name: str) -> EconomyModel:
    return replace(EconomyModel(), **ECONOMIES[name][1])


def economy_name(world: World) -> str:
    """The named economy a world was made with: ``CUSTOM`` if none (tests, studies)."""
    made = stored_economy(world.config)
    if not made.stages:
        return "STILL"
    for name in ECONOMIES:
        if name != "STILL" and made == economy_model(name):
            return name
    return "CUSTOM"


def find_world(seed: int, scale: str, economy: str) -> World | None:
    """A stored world of this seed, size and economy, if there is one."""
    for world in World.objects.filter(
        seed=seed, scale=scale, generator_version=GENERATOR_VERSION
    ).order_by("pk"):
        if economy_name(world) == economy and world.config.get("mobile_loans", False):
            return world
    return None


def make_world(seed: int, scale: str, economy: str) -> World:
    """Generate and store a world of this seed, size and economy (minutes for a full size)."""
    made = build_world(seed, scale, economy=economy_model(economy))
    with transaction.atomic():
        world_id = write_world(
            made.config, made.people, made.businesses, made.branches, made.result, made.stats
        )
    return World.objects.get(pk=world_id)


# --- Applying the parameters to a new game -------------------------------------------------


def apply(game: Game) -> None:
    """Settle the starting cash and the providers' quality once the bureau is set up."""
    from .providers import relationship

    params = parameters(game)
    org = game.organization
    eve = game.clock_start - timedelta(days=1)
    at = datetime.combine(eve, time(17, 0), tzinfo=UTC)
    if game.scenario != STARTUP:
        change = params.cash_adjustment
        if params.starting_cash is not None:
            change = params.starting_cash - balance(org, BANK, eve)
        if change > 0:
            capital_injection(org, change, eve, at)
        elif change < 0:
            dividend_paid(org, -change, eve, at)
    if params.provider_quality:
        for code in org.institutions.order_by("institution_code").values_list(
            "institution_code", flat=True
        ):
            found = relationship(game, code)
            found.quality = params.provider_quality
            found.save(update_fields=["quality"])


def describe(game: Game) -> dict[str, Any]:
    params = parameters(game)
    return {
        "scenario": game.scenario,
        "scenario_name": SCENARIOS[game.scenario][0],
        "difficulty": game.difficulty,
        "parameters": params.as_json(),
        "economy": ECONOMIES.get(params.economy, ("",))[0],
        "world_economy": economy_name(game.world),
    }


def catalogue() -> dict[str, Any]:
    """Everything the new-game form offers, with what each choice means."""
    return {
        "scenarios": [{"code": c, "name": n, "does": d} for c, (n, d) in SCENARIOS.items()],
        "difficulties": [
            {"code": c, "name": c.title(), "does": d, "parameters": p.as_json()}
            for c, (d, p) in DIFFICULTIES.items()
        ],
        "economies": [{"code": c, "does": d} for c, (d, _) in ECONOMIES.items()],
        "scales": list(SCALES),
        "startup_capital": str(STARTUP_CAPITAL),
        "max_provider_quality": MAX_PROVIDER_QUALITY,
    }
