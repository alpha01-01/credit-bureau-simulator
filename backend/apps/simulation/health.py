"""The Bureau Health summary (P2.10; Document 07, Section 10.3).

ASSUMPTION A-067, five dimensions each scored out of 100:

* **Financial**: 70% runway (months of costs the bank balance covers; 12 months or
  more scores 100) and 30% the last three months' result (break-even scores 50,
  a loss as large as the costs scores 0, a profit of half the costs scores 100).
* **Data quality**: half the audited accuracy, half the coverage of the market's
  active borrowers, from the latest month-end figures.
* **Reputation**: the average of the three audiences (A-061).
* **Compliance**: the regulator's score (A-061).
* **Team**: the average morale of active staff; no staff scores 0.

A dimension is good from 65, to watch from 50, and poor below. Overall health
weights them 30/25/20/10/15; the board's confidence is the same figure (A-066).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Avg, Count, Sum

from apps.finance.events import (
    IT_CAPACITY_COST,
    MATCHING_TOOLING_COST,
    MONTHLY_IT,
    MONTHLY_RENT,
    balance,
)
from apps.finance.ledger import BANK
from apps.finance.statements import income_statement
from apps.org.models import Employee
from apps.standards.rulebook import TAX_RULES
from apps.workitems.models import ItemStatus, WorkItem

from .compliance import LEVEL_NAMES
from .models import Game, Notice
from .reputation import reputation

WEIGHTS = {"financial": 30, "data_quality": 25, "reputation": 20, "compliance": 10, "team": 15}
GOOD, WATCH = 65, 50
RUNWAY_FULL_MONTHS = 12
# ASSUMPTION A-065: the overdraft facility the bureau's bank has agreed.
OVERDRAFT_LIMIT = Decimal("500000.00")


def _clamp(x: float) -> float:
    return max(0.0, min(100.0, x))


def rating(score: float | None) -> str:
    if score is None:
        return "unknown"
    return "good" if score >= GOOD else "watch" if score >= WATCH else "poor"


def monthly_costs(game: Game, on: date) -> Decimal:
    """What a month costs now: pay with employer SSNIT, rent, IT and software."""
    org = game.organization
    pay = Employee.objects.filter(organization=org, is_active=True).aggregate(
        t=Sum("monthly_salary")
    )["t"] or Decimal("0")
    ssnit = TAX_RULES.at(on).ssnit_employer
    return (
        pay * (1 + ssnit)
        + MONTHLY_RENT
        + MONTHLY_IT
        + IT_CAPACITY_COST[org.it_capacity]
        + MATCHING_TOOLING_COST[org.matching_tooling]
    ).quantize(Decimal("0.01"))


def financial(game: Game, today: date) -> dict[str, Any]:
    org = game.organization
    bank = balance(org, BANK, today)
    costs = monthly_costs(game, today)
    runway = float(bank / costs) if costs else float(RUNWAY_FULL_MONTHS)
    statement = income_statement(org, today - timedelta(days=91), today)
    result = statement["net_profit"]
    quarter_costs = statement["total_expenses"] or costs * 3
    result_score = _clamp(50 + 100 * float(result / quarter_costs))
    runway_score = _clamp(100 * max(runway, 0) / RUNWAY_FULL_MONTHS)
    stage = getattr(game, "solvency", None)
    return {
        "score": round(0.7 * runway_score + 0.3 * result_score, 1),
        "bank": str(bank),
        "monthly_costs": str(costs),
        "runway_months": round(runway, 1),
        "result_3_months": str(result),
        "overdraft_limit": str(OVERDRAFT_LIMIT),
        "overdraft_used": str(max(-bank, Decimal("0"))),
        "stage": stage.stage if stage else "OK",
        "creditors_deadline": stage.creditors_deadline if stage else None,
    }


def data_quality(game: Game) -> dict[str, Any]:
    latest = game.reviews.order_by("-period").first()
    if latest is None:
        return {"score": None, "as_of": None, "accuracy": None, "coverage": None}
    visible = latest.figures["assets"]["visible"]
    accuracy = visible["audit"]["accuracy"]["share"]
    coverage = visible["coverage"]["share"]
    score = 100 * (0.5 * (accuracy or 0.0) + 0.5 * (coverage or 0.0))
    return {
        "score": round(score, 1),
        "as_of": latest.period,
        "accuracy": accuracy,
        "coverage": coverage,
        "freshness_days": visible.get("freshness_days"),
    }


def team(game: Game, at: datetime) -> dict[str, Any]:
    org = game.organization
    active = Employee.objects.filter(organization=org, is_active=True)
    figures = active.aggregate(n=Count("id"), morale=Avg("morale"))
    queue = WorkItem.objects.filter(
        organization=org, status__in=[ItemStatus.OPEN, ItemStatus.IN_PROGRESS]
    ).count()
    resignations = Notice.objects.filter(
        game=game, kind="RESIGNATION", sim_time__gte=at - timedelta(days=91)
    ).count()
    morale = figures["morale"]
    return {
        "score": round(100 * morale, 1) if morale is not None else 0.0,
        "staff": figures["n"],
        "average_morale": round(morale, 3) if morale is not None else None,
        "open_items": queue,
        "resignations_3_months": resignations,
    }


def health(game: Game, at: datetime) -> dict[str, Any]:
    today = at.date()
    rep = reputation(game, at)
    level = rep["regulator"]["level"]
    parts: dict[str, dict[str, Any]] = {
        "financial": financial(game, today),
        "data_quality": data_quality(game),
        "reputation": {
            "score": round(
                (
                    rep["subscribers"]["score"]
                    + rep["providers"]["score"]
                    + rep["regulator"]["score"]
                )
                / 3,
                1,
            ),
            "subscribers": rep["subscribers"]["score"],
            "providers": rep["providers"]["score"],
            "regulator": rep["regulator"]["score"],
        },
        "compliance": {
            "score": float(rep["regulator"]["score"]),
            "level": level,
            "standing": LEVEL_NAMES[min(level, len(LEVEL_NAMES) - 1)],
            "findings_6_months": rep["regulator"]["findings"],
        },
        "team": team(game, at),
    }
    for part in parts.values():
        part["rating"] = rating(part["score"])
    return {"as_of": today, "overall": overall(parts), "parts": parts}


def overall(parts: dict[str, dict[str, Any]]) -> float:
    """Weighted health; a dimension not yet measured counts as middling (50)."""
    total = sum(
        WEIGHTS[name] * (part["score"] if part["score"] is not None else 50.0)
        for name, part in parts.items()
    )
    return round(total / sum(WEIGHTS.values()), 1)
