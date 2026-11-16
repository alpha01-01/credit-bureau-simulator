"""Disputes from the world, and the regulator (P2.7; Document 07, Sections 8.5 and 10.2).

Subjects dispute (ASSUMPTION A-056):

* a subject whose report showed someone else's accounts disputes it with chance
  0.4, a few working days later (2 to 8);
* a subject whose report is right but shows an account of theirs in arrears
  wrongly disputes it with chance 0.02.

The bureau must settle a dispute within its statutory period: 10 working days here,
a placeholder until reference R7 (L.I. 2394, Regulations 23-26) gives the real one.

The regulator records a finding for every dispute left past its deadline, and
escalates with the number of findings in the last six months: 1 a concern letter,
3 a formal directive, 5 a financial penalty (1,000 penalty units at GHS 12), 7 a
licence suspension, during which subscribers cannot enquire. As findings age out
the bureau steps back down the ladder: the way back is always visible.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from apps.bureau.core.models import AccountObservation, CreditAccount, Customer, Enquiry
from apps.bureau.quality.disputes import latest_record, open_dispute
from apps.bureau.quality.models import Dispute, DisputeStatus
from apps.finance.events import regulatory_penalty
from apps.standards.calendar import is_working_day
from apps.world.generation.rng import stream

from .clock import TICKS_PER_DAY
from .consequences import MIXED
from .failure import LICENCE_REVOKED, end_game
from .models import (
    Consequence,
    EventType,
    Game,
    RegulatorFinding,
    RegulatorStanding,
    ScheduledEvent,
    Severity,
)

DISPUTE_WRONG_REPORT = 0.4
DISPUTE_OWN_ARREARS = 0.02
FILING_DELAY_DAYS = (2, 8)
STATUTORY_WORKING_DAYS = 10
FINDINGS_WINDOW_DAYS = 183
LADDER = (
    (9, 5, "Licence revoked: the bureau may no longer operate"),
    (7, 4, "Licence suspended: subscribers may not enquire until the regulator is satisfied"),
    (5, 3, "Financial penalty imposed for repeated breaches"),
    (3, 2, "Formal directive: settle disputes within the statutory period"),
    (1, 1, "Concern letter from the regulator"),
)
LEVEL_NAMES = ("good standing", "concern letter", "directive", "penalty", "suspended", "revoked")
REVOKED = 5
# What the next step up would be, said with each warning (P2.10).
NEXT_STEP = {
    1: "Three findings in six months bring a formal directive.",
    2: "Five bring a financial penalty.",
    3: "Seven suspend the licence.",
    4: "Nine revoke it, and the bureau closes.",
}
PENALTY = Decimal("12000.00")  # 1,000 penalty units at GHS 12 (ASSUMPTION A-058)


def add_working_days(day: date, days: int) -> date:
    while days > 0:
        day += timedelta(days=1)
        if is_working_day(day):
            days -= 1
    return day


def maybe_dispute(
    game: Game,
    enquiry: Enquiry,
    subject_name: str,
    chains: list[Consequence],
    tick: int,
) -> bool:
    """After a report is delivered: does its subject dispute it? Schedules the filing."""
    if enquiry.customer_id is None:
        return False
    rng = stream(game.world.seed, f"dispute:{enquiry.enquiry_reference}")
    wrong = [c for c in chains if c.effect == MIXED]
    accounts: list[list[str]] = []
    if wrong:
        if rng.random() >= DISPUTE_WRONG_REPORT:
            return False
        keys = {(c.provider, c.provider_customer) for c in wrong}
        accounts = _accounts_of(enquiry.customer_id, keys)
        claim = "These accounts are not mine; I have never borrowed from these lenders."
    else:
        in_arrears = [
            a for a in enquiry.report.get("accounts", []) if (a.get("days_past_due") or 0) > 0
        ]
        if not in_arrears or rng.random() >= DISPUTE_OWN_ARREARS:
            return False
        accounts = _arrears_accounts(enquiry.customer_id)
        claim = "I do not recognise these arrears; they must be someone else's."
    if not accounts:
        return False
    low, high = FILING_DELAY_DAYS
    delay = int(rng.integers(low, high + 1))
    ScheduledEvent.objects.create(
        game=game,
        event_type=EventType.DISPUTE_FILED,
        due_tick=tick + delay * TICKS_PER_DAY,
        sequence=_next_sequence(game),
        payload={
            "enquiry": enquiry.enquiry_reference,
            "customer": Customer.objects.get(pk=enquiry.customer_id).customer_reference,
            "subject": subject_name,
            "claim": claim,
            "accounts": accounts,
        },
    )
    return True


def _next_sequence(game: Game) -> int:
    last = game.events.order_by("-sequence").values_list("sequence", flat=True).first()
    return (last or 0) + 1


def _accounts_of(customer_id: int, keys: set[tuple[str, str]]) -> list[list[str]]:
    """The subject's accounts that came through the wrongly linked provider customers."""
    out = []
    for account in CreditAccount.objects.filter(customer_id=customer_id).select_related(
        "institution"
    ):
        record = latest_record(account)
        code = account.institution.institution_code
        if record is not None and (code, record.cleansed.get("CustomerID", "")) in keys:
            out.append([code, account.facility_account_number])
    return sorted(out)


def _arrears_accounts(customer_id: int) -> list[list[str]]:
    out = set()
    for code, number, dpd in AccountObservation.objects.filter(
        credit_account__customer_id=customer_id, is_current=True
    ).values_list(
        "credit_account__institution__institution_code",
        "credit_account__facility_account_number",
        "days_past_due",
    ):
        if dpd and dpd > 0:
            out.add((code, number))
    return sorted([list(a) for a in out])


def file_dispute(game: Game, payload: dict[str, Any], at: datetime) -> Dispute | None:
    """The subject's dispute reaches the bureau."""
    customer = Customer.objects.filter(
        organization=game.organization, customer_reference=payload["customer"]
    ).first()
    if customer is None:
        return None
    enquiry = Enquiry.objects.filter(
        organization=game.organization, enquiry_reference=payload["enquiry"]
    ).first()
    return open_dispute(
        game.organization,
        customer,
        enquiry,
        str(payload["subject"]),
        str(payload["claim"]),
        [list(a) for a in payload["accounts"]],
        at,
        add_working_days(at.date(), STATUTORY_WORKING_DAYS),
    )


# --- The regulator ---------------------------------------------------------------------


def standing(game: Game) -> RegulatorStanding:
    found, _ = RegulatorStanding.objects.get_or_create(game=game)
    return found


def suspended(game: Game) -> bool:
    return RegulatorStanding.objects.filter(game=game, level__gte=4).exists()


def morning_review(game: Game, today: date, at: datetime, add: Any) -> None:
    """Each morning: findings for disputes past their deadline, then the ladder.

    ``add`` posts a notice to the tick's feed: add(kind, severity, title, detail, drill).
    """
    for dispute in Dispute.objects.filter(
        organization=game.organization, status=DisputeStatus.OPEN, due_date__lt=today
    ).order_by("dispute_number"):
        _, created = RegulatorFinding.objects.get_or_create(
            game=game,
            kind="MISSED_DISPUTE_DEADLINE",
            reference=str(dispute.dispute_number),
            defaults={
                "raised_at": at,
                "detail": f"Dispute {dispute.dispute_number} from {dispute.subject_name} was "
                f"not settled by {dispute.due_date:%d %B %Y}.",
            },
        )
        if created:
            add(
                "REGULATOR_FINDING",
                Severity.WARNING,
                f"Regulator finding: dispute {dispute.dispute_number} missed its deadline",
                f"It was due on {dispute.due_date:%d %B}. Settle it now; findings add up.",
                {"screen": "disputes", "params": {}},
            )
    _climb(game, today, at, add)


def _climb(game: Game, today: date, at: datetime, add: Any) -> None:
    since = at - timedelta(days=FINDINGS_WINDOW_DAYS)
    count = RegulatorFinding.objects.filter(game=game, raised_at__gte=since).count()
    level = next((lvl for threshold, lvl, _ in LADDER if count >= threshold), 0)
    record = standing(game)
    if level == record.level or record.level == REVOKED:  # revocation is final
        return
    rising = level > record.level
    why = next((text for _, lvl, text in LADDER if lvl == level), "Back in good standing")
    record.history = [
        *record.history,
        {"at": at.isoformat(), "level": level, "findings": count, "why": why},
    ]
    record.level = level
    record.save(update_fields=["level", "history"])
    if rising and level == 3:
        regulatory_penalty(game.organization, PENALTY, today, at)
    add(
        "REGULATOR_LADDER",
        Severity.CRITICAL
        if rising and level >= 2
        else Severity.WARNING
        if rising
        else Severity.INFO,
        why if rising else f"The regulator has stepped back: {LEVEL_NAMES[level]}",
        f"{count} finding(s) in the last six months. "
        + (
            f"{NEXT_STEP[level]} Settle disputes on time: findings fall away after six months."
            if rising and level in NEXT_STEP
            else ""
        ),
        {"screen": "disputes", "params": {}},
    )
    if level == REVOKED:
        end_game(
            game, LICENCE_REVOKED, game.current_tick + 1,
            f"{count} findings in six months for disputes left past the statutory deadline.",
            add,
        )  # fmt: skip
