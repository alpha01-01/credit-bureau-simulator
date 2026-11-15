"""Dishonoured cheques and court judgments (P2.0c).

Events that lenders report on their own files, grown out of the credit
history so that they agree with it (ASSUMPTION A-040):

* **Dishonoured cheques.** Banks and savings and loans companies give their
  customers cheque books. In a month, a borrower's cheque bounces with a
  chance that rises with arrears: 0.2% when current, 5% when in arrears, 10%
  at 90 days or more. 4% of bounced cheques are returned for fraud, the rest
  for insufficient funds. The amount is around 40% of a person's monthly
  income, or 25% of a business's monthly revenue. At most one per borrower,
  lender and month.
* **Judgments.** A lender sues 35% of the borrowers whose loans it writes off
  with at least GHS 1,000 outstanding, filing 2 to 8 months after the
  write-off, for the balance written off plus 5 to 15% costs. The court is by
  amount: District Court below GHS 50,000, Circuit Court below GHS 500,000,
  else the High Court (Commercial Division), in the borrower's town. 70% end
  in judgment by default, the rest in a court order.

People and businesses draw from separate streams, so adding one never moves
the other. Generation is lazy and deterministic: a month's events are created
the first time they are needed, from the world seed, the same however often or
in whatever order months are asked for.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db import connection, transaction

from apps.world.models import (
    Business,
    CourtJudgment,
    DishonouredCheque,
    EventMonth,
    Lender,
    Loan,
    Person,
    World,
)

from .persist import loan_month_partition
from .rng import stream

CHEQUE_LENDER_TYPES = ("COMMERCIAL_BANK", "SAVINGS_AND_LOANS")
BOUNCE_CHANCE = ((0, 0.002), (1, 0.05), (90, 0.10))  # (days past due from, monthly chance)
FRAUD_SHARE = 0.04
SUE_SHARE = 0.35
MIN_CLAIM = Decimal("1000")  # lenders do not go to court over small balances
FILING_LAG_MONTHS = (2, 8)
COURTS = (
    (Decimal("50000"), "District Court", "District", "DC"),
    (Decimal("500000"), "Circuit Court", "Circuit", "CC"),
    (None, "High Court (Commercial Division)", "High Court", "HC"),
)


def _month_index(period: date) -> int:
    return period.year * 12 + period.month - 1


def _month_end(index: int) -> date:
    year, month = divmod(index, 12)
    first_of_next = date(year + (month + 1) // 12, (month + 1) % 12 + 1, 1)
    return first_of_next - timedelta(days=1)


def _whole(value: Decimal) -> Decimal:
    return value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def ensure_events(world: World, period: date) -> None:
    """Create the month's cheques and judgments if that has not been done yet."""
    if EventMonth.objects.filter(world=world, period=period).exists():
        return
    if period > world.history_end:
        raise ValueError(f"The world has not lived through {period:%B %Y} yet")
    with transaction.atomic():
        DishonouredCheque.objects.bulk_create(_cheques(world, period), batch_size=2000)
        CourtJudgment.objects.bulk_create(_judgments(world, period), batch_size=2000)
        EventMonth.objects.create(world=world, period=period)


def _loan_months(world: World, where: str, params: list[Any]) -> list[tuple[Any, ...]]:
    """Rows of the world's own loan-month partition: no joins, so the plan is always simple."""
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT loan_id, lender_id, period, days_past_due, outstanding_balance "  # noqa: S608
            f"FROM {loan_month_partition(world.pk)} WHERE {where}",
            params,
        )
        rows: list[tuple[Any, ...]] = cursor.fetchall()
    return rows


# Borrower kinds: (tag, account digit, share of monthly income or revenue a cheque is for).
PERSON, BUSINESS = ("P", "1", 0.4), ("B", "2", 0.25)


def _loans(loan_ids: list[int]) -> dict[int, tuple[Any, ...]]:
    """Loans by id: (seq, account, disbursed, borrower, borrower seq, monthly income, town).

    ``borrower`` is (kind tag, world id) of the person or business.
    """
    out: dict[int, tuple[Any, ...]] = {}
    for pk, seq, account, disbursed, person, business in Loan.objects.filter(
        pk__in=loan_ids
    ).values_list(
        "pk", "seq_no", "account_number", "disbursement_date", "customer__person_id",
        "customer__business_id",
    ):  # fmt: skip
        out[pk] = (seq, account, disbursed, ("P", person) if person else ("B", business))
    people = {
        pk: (seq, income, town)
        for pk, seq, income, town in Person.objects.filter(
            pk__in={v[3][1] for v in out.values() if v[3][0] == "P"}
        ).values_list("pk", "seq_no", "monthly_income", "town")
    }
    businesses = {
        pk: (seq, revenue, town)
        for pk, seq, revenue, town in Business.objects.filter(
            pk__in={v[3][1] for v in out.values() if v[3][0] == "B"}
        ).values_list("pk", "seq_no", "monthly_revenue", "town")
    }
    for pk, (seq, account, disbursed, borrower) in list(out.items()):
        details = (people if borrower[0] == "P" else businesses)[borrower[1]]
        out[pk] = (seq, account, disbursed, borrower, *details)
    return out


def _cheques(world: World, period: date) -> list[DishonouredCheque]:
    banks = dict(
        Lender.objects.filter(world=world, lender_type__in=CHEQUE_LENDER_TYPES).values_list(
            "id", "code"
        )
    )
    if not banks:
        return []
    months = _loan_months(
        world, "period = %s AND status = 'ACTIVE' AND lender_id = ANY(%s)", [period, list(banks)]
    )
    loans = _loans([m[0] for m in months])
    out: list[DishonouredCheque] = []
    for kind, stream_name in ((PERSON, "cheques"), (BUSINESS, "business-cheques")):
        rows = sorted(
            (
                (lender_id, loan_id, dpd, *loans[loan_id])
                for loan_id, lender_id, _, dpd, _ in months
                if loans[loan_id][3][0] == kind[0]
            ),
            key=lambda r: (banks[r[0]], r[7], r[4]),  # lender code, borrower seq, account
        )
        out += _bounced(
            world, period, kind, stream(world.seed, stream_name, _month_index(period)), rows
        )
    return out


def _bounced(
    world: World,
    period: date,
    kind: tuple[str, str, float],
    rng: Any,
    rows: list[tuple[Any, ...]],
) -> list[DishonouredCheque]:
    _, digit, share = kind
    index = _month_index(period)
    days = period.day
    out: list[DishonouredCheque] = []
    seen: set[tuple[int, Any]] = set()
    for lender_id, loan_id, dpd, _, account, disbursed, borrower, seq, income, _ in rows:
        if (lender_id, borrower) in seen:  # one chance per borrower and lender a month
            continue
        seen.add((lender_id, borrower))
        chance = next(p for floor, p in reversed(BOUNCE_CHANCE) if dpd >= floor)
        draw = rng.random(5)
        if draw[0] >= chance:
            continue
        bounced = period.replace(day=1 + int(draw[1] * days))
        amount = max(Decimal("50"), _whole(Decimal(income) * Decimal(share * (0.5 + draw[2]))))
        out.append(
            DishonouredCheque(
                world=world, lender_id=lender_id, loan_id=loan_id, period=period,
                account_number=f"{account[:4]}{digit}{seq:09d}",
                account_opened=disbursed - timedelta(days=365 * (1 + seq % 5)),
                cheque_number=f"{index % 100000:05d}{int(draw[3] * 10)}",
                date_issued=bounced - timedelta(days=1 + int(draw[3] * 10)),
                date_bounced=bounced,
                reason="12" if draw[4] < FRAUD_SHARE else "11",
                amount=amount,
            )
        )  # fmt: skip
    return out


def _judgments(world: World, period: date) -> list[CourtJudgment]:
    index = _month_index(period)
    low, high = FILING_LAG_MONTHS
    months = _loan_months(
        world,
        "status = 'WRITTEN_OFF' AND period BETWEEN %s AND %s",
        [_month_end(index - high), _month_end(index - low)],
    )
    loans = _loans([m[0] for m in months])
    rows = sorted(
        (
            (lender_id, loan_id, loans[loan_id][0], written_off, balance, loans[loan_id][6])
            for loan_id, lender_id, written_off, _, balance in months
        ),
        key=lambda r: r[2],  # by the loan's place in the world
    )

    out: list[CourtJudgment] = []
    counters: dict[str, int] = {}
    for lender_id, loan_id, loan_seq, written_off, balance, town in rows:
        # The loan's own fate, by its place in the world (never a database id): the same
        # whichever month asks, and the same in every world built from this seed.
        rng = stream(world.seed, "judgment", loan_seq)
        draw = rng.random(4)
        lag = low + int(draw[1] * (high - low + 1))
        if draw[0] >= SUE_SHARE or balance < MIN_CLAIM or _month_index(written_off) + lag != index:
            continue
        amount = _whole(Decimal(balance) * Decimal(1.05 + 0.10 * draw[2]))
        _, court, court_type, code = next(c for c in COURTS if c[0] is None or amount < c[0])
        counters[code] = counters.get(code, 0) + 1
        out.append(
            CourtJudgment(
                world=world, lender_id=lender_id, loan_id=loan_id, period=period,
                court_name=f"{town} {court}"[:50], court_location=town[:50],
                court_type=court_type,
                case_number=f"{code}{period:%y}/{period.month:02d}{counters[code]:03d}",
                filing_date=period.replace(day=1 + int(draw[3] * period.day)),
                case_type="J" if draw[3] < 0.7 else "C",
                case_reason="R",
                amount=amount,
            )
        )  # fmt: skip
    return out
