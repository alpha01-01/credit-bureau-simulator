"""Cash, the overdraft and the road to insolvency (P2.10; Document 07, Section 10.2).

ASSUMPTION A-065:

* The bank has agreed an overdraft facility of GHS 500,000. Interest of 2.5% a
  month is charged on the overdrawn balance at each month start.
* Each working morning the bureau's cash is checked, and its stage moves:
  LOW below one month's costs (pay with employer SSNIT, rent, IT, software);
  OVERDRAFT once the bank balance is below zero; CREDITORS once the overdraft
  limit is exceeded: creditors serve notice and the bureau has 21 days to come
  back within the limit (after the statutory demand of the Corporate
  Insolvency and Restructuring Act 2020, Act 1015; reference R19 to confirm).
  If it has not by then, it is insolvent and the game ends.
* Stages move back down as cash recovers; a bureau back within its limit has
  the creditors' notice withdrawn.
* The shareholders put in new capital (at most GHS 2,000,000, once a quarter)
  when asked, if the board's confidence at its last review was 50 or more (a
  bureau not yet reviewed is given the benefit of the doubt).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from apps.finance.events import balance, capital_injection, overdraft_interest
from apps.finance.ledger import BANK

from .failure import INSOLVENT, PATHS, end_game
from .health import OVERDRAFT_LIMIT, monthly_costs
from .models import BoardReview, FundingRequest, Game, Severity, SolvencyState

INTEREST_PER_MONTH = Decimal("0.025")
CREDITORS_DAYS = 21
MAX_FUNDING = Decimal("2000000.00")
FUNDING_CONFIDENCE = 50.0
FUNDING_EVERY_DAYS = 91
STAGES = ("OK", "LOW", "OVERDRAFT", "CREDITORS")


class FundingError(Exception):
    pass


def money(amount: Decimal) -> str:
    return f"GHS {amount:,.2f}"


def state(game: Game) -> SolvencyState:
    record, _ = SolvencyState.objects.get_or_create(game=game)
    return record


def _stage_for(bank: Decimal, costs: Decimal) -> str:
    if bank < -OVERDRAFT_LIMIT:
        return "CREDITORS"
    if bank < 0:
        return "OVERDRAFT"
    if bank < costs:
        return "LOW"
    return "OK"


def morning(game: Game, today: date, at: datetime, tick: int, add: Any) -> None:
    """Each working morning: where does the bureau stand, and has time run out?"""
    record = state(game)
    bank = balance(game.organization, BANK, today)
    costs = monthly_costs(game, today)
    stage = _stage_for(bank, costs)
    if (
        record.stage == "CREDITORS"
        and stage == "CREDITORS"
        and record.creditors_deadline is not None
        and today >= record.creditors_deadline
    ):
        end_game(
            game, INSOLVENT, tick,
            f"The bank is overdrawn by {money(-bank)}, beyond the agreed "
            f"{money(OVERDRAFT_LIMIT)}, and the creditors' deadline of "
            f"{record.creditors_deadline:%d %B %Y} has passed.",
            add,
        )  # fmt: skip
        _move(record, "INSOLVENT", at, "Creditors' deadline passed")
        return
    if stage == record.stage:
        return
    rising = STAGES.index(stage) > STAGES.index(record.stage)
    # The cash steps lead to the bank account behind them; creditors to the way back.
    drill = {"screen": "ledger", "params": {"account": BANK}}
    if stage == "CREDITORS":
        record.creditors_deadline = today + timedelta(days=CREDITORS_DAYS)
        add(
            "CREDITORS_NOTICE", Severity.CRITICAL,
            "Creditors have served notice: the overdraft limit is exceeded",
            f"The bank is overdrawn by {money(-bank)}; the limit is {money(OVERDRAFT_LIMIT)}. "
            f"Come back within it by {record.creditors_deadline:%d %B} or the bureau is "
            f"insolvent. {PATHS[INSOLVENT]['path_back']}",
            {"screen": "health", "params": {}},
        )  # fmt: skip
    elif stage == "OVERDRAFT" and rising:
        add(
            "OVERDRAFT_USED", Severity.CRITICAL,
            "The bureau is using its overdraft",
            f"The bank is overdrawn by {money(-bank)} of the {money(OVERDRAFT_LIMIT)} agreed; "
            f"interest is {INTEREST_PER_MONTH:.1%} a month. Beyond the limit, creditors will "
            "serve notice.",
            drill,
        )  # fmt: skip
    elif stage == "LOW" and rising:
        add(
            "CASH_LOW", Severity.CRITICAL,
            "Cash is below one month's costs",
            f"The bank holds {money(bank)}; a month costs {money(costs)}. Next comes the "
            f"overdraft ({money(OVERDRAFT_LIMIT)} agreed).",
            drill,
        )  # fmt: skip
    else:  # recovering
        if record.stage == "CREDITORS":
            record.creditors_deadline = None
            add(
                "CREDITORS_WITHDRAWN", Severity.WARNING,
                "Creditors have withdrawn their notice",
                f"The bank balance, {money(bank)}, is back within the overdraft limit.",
                drill,
            )  # fmt: skip
        else:
            add(
                "CASH_RECOVERED", Severity.INFO,
                "Cash has recovered" if stage == "OK" else "The overdraft is cleared",
                f"The bank holds {money(bank)}; a month costs {money(costs)}.",
                drill,
            )  # fmt: skip
    _move(record, stage, at, f"Bank {bank}, a month's costs {costs}")


def _move(record: SolvencyState, stage: str, at: datetime, why: str) -> None:
    record.history = [*record.history, {"at": at.isoformat(), "stage": stage, "why": why}]
    record.stage = stage
    record.save(update_fields=["stage", "creditors_deadline", "history"])


def month_start(game: Game, today: date, at: datetime, add: Any) -> None:
    """Interest on last month's overdrawn balance."""
    bank = balance(game.organization, BANK, today - timedelta(days=1))
    if bank >= 0:
        return
    interest = (-bank * INTEREST_PER_MONTH).quantize(Decimal("0.01"))
    overdraft_interest(game.organization, interest, today, at)
    add(
        "OVERDRAFT_INTEREST", Severity.WARNING,
        f"Overdraft interest of {money(interest)} charged",
        f"On an overdrawn balance of {money(-bank)}.",
        {"screen": "ledger", "params": {"account": BANK}},
    )  # fmt: skip


def request_funding(game: Game, amount: Decimal, at: datetime) -> FundingRequest:
    if amount <= 0 or amount > MAX_FUNDING:
        raise FundingError(f"Ask for more than nothing and at most {money(MAX_FUNDING)}")
    recent = FundingRequest.objects.filter(
        game=game, granted=True, requested_at__gte=at - timedelta(days=FUNDING_EVERY_DAYS)
    )
    if recent.exists():
        raise FundingError("The shareholders put in capital less than a quarter ago")
    review = BoardReview.objects.filter(game=game).order_by("-period").first()
    confidence = review.confidence if review else None
    granted = confidence is None or confidence >= FUNDING_CONFIDENCE
    reason = (
        f"The board's confidence at its last review was {confidence:.0f}."
        if confidence is not None
        else "The board has not reviewed the management yet."
    )
    number = FundingRequest.objects.filter(game=game).count() + 1
    request = FundingRequest.objects.create(
        game=game,
        number=number,
        requested_at=at,
        amount=amount.quantize(Decimal("0.01")),
        granted=granted,
        reason=reason,
    )
    if granted:
        capital_injection(game.organization, request.amount, at.date(), at)
    return request
