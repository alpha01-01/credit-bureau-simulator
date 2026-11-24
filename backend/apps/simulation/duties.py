"""Compliance's duties (P3.7; Document 09; the rules in apps/standards/compliance_rules.py).

* The monthly return (rule RETURN): opened at each month's start for the month just
  ended, due by the 15th; filed late or not at all, it is a regulator finding.
* Consent (rule CONSENT): each subscriber enquires now and then without the subject's
  consent on file, at a hidden rate of its own. Compliance asks a subscriber for the
  forms behind a sample of its enquiries; the forms it cannot send are a finding, put
  right by warning or suspending the subscriber, which makes it more careful.
* Retention (rule RETENTION): reports leave out closed accounts older than the
  bureau's retention period. A period longer than the legal one shows old accounts the
  bureau should have let go, and the regulator records a breach.
* Access (rule ACCESS): each quarter Compliance reviews who can reach the bureau's
  data, and removes leavers' access.
* Findings (rule FINDINGS): each finding has a remedy and a deadline; one left past its
  deadline goes to the regulator, and climbs the same ladder as missed disputes.

The rates and periods are ASSUMPTION A-077.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from django.db.models import Max

from apps.bureau.core.models import Enquiry
from apps.bureau.quality.models import RegulatoryReturn
from apps.bureau.quality.returns import open_return
from apps.org.models import Employee
from apps.standards.calendar import next_working_day
from apps.standards.compliance_rules import (
    CONSENT_ANSWER_WORKING_DAYS,
    FINDING_WORKING_DAYS,
    LEGAL_RETENTION_YEARS,
    RETURN_DUE_DAY,
)
from apps.world.generation.rng import stream
from apps.world.provider_files import month_end as period_end

from .clock import TICKS_PER_DAY, Calendar, previous_month_end
from .compliance import add_working_days
from .models import (
    ComplianceFinding,
    ConsentCheck,
    EnquiryJudgement,
    Game,
    RegulatorFinding,
    Sanction,
    Severity,
)

IMPROPER_RATE = (0.005, 0.05)  # a subscriber's share of enquiries without consent on file
WARNING_FACTOR, SUSPENSION_FACTOR = 0.5, 0.25  # what a sanction does to that share
SUSPENSION_WORKING_DAYS = 22  # about a month
SAMPLE_SIZES = (10, 25, 50)
RETENTION_CHOICES = (3, 4, 5, 6, 7)  # years; above 5 breaks the rule
WARNING, SUSPENSION = "WARNING", "SUSPENSION"


def quietly(*_: Any) -> None:
    """A feed that posts nothing (for code run outside a tick)."""


class DutyError(Exception):
    """Compliance cannot do this; the message says why."""


# --- Findings --------------------------------------------------------------------------


def raise_finding(
    game: Game,
    kind: str,
    reference: str,
    detail: str,
    remedy: str,
    tick: int,
    at: datetime,
) -> ComplianceFinding:
    """A compliance finding, with its remedy and the date to put it right by."""
    number = (ComplianceFinding.objects.filter(game=game).aggregate(n=Max("number"))["n"] or 0) + 1
    return ComplianceFinding.objects.create(
        game=game, number=number, kind=kind, reference=reference, detail=detail,
        remedy=remedy[:300], raised_tick=tick, raised_at=at,
        due_date=add_working_days(at.date(), FINDING_WORKING_DAYS),
    )  # fmt: skip


def resolve_findings(game: Game, tick: int, **match: Any) -> int:
    return ComplianceFinding.objects.filter(game=game, resolved_tick__isnull=True, **match).update(
        resolved_tick=tick
    )


# --- The monthly return ----------------------------------------------------------------


def return_due(period: date) -> date:
    """The 15th of the month after ``period``, or the next working day."""
    following = date(period.year + period.month // 12, period.month % 12 + 1, RETURN_DUE_DAY)
    return next_working_day(following)


def month_start(game: Game, today: date, tick: int, at: datetime, add: Any) -> None:
    """At a month's start: last month's return is owed; at a quarter's, an access review."""
    period = previous_month_end(today)
    if not RegulatoryReturn.objects.filter(organization=game.organization, period=period).exists():
        found = open_return(game.organization, period, return_due(period), at)
        add(
            "RETURN_OWED", Severity.INFO, f"The return for {period:%B %Y} is owed",
            f"File it with the Bank of Ghana by {found.due_date:%d %B}.",
            {"screen": "compliance", "params": {}},
        )  # fmt: skip
    if today.month % 3 == 1:
        _access_review_due(game, today, tick, at, add)


def _access_review_due(game: Game, today: date, tick: int, at: datetime, add: Any) -> None:
    reference = f"ACCESS-{today:%Y-%m}"
    if ComplianceFinding.objects.filter(game=game, reference=reference).exists():
        return
    leavers = leavers_with_access(game)
    detail = (
        f"The quarter's review of who can reach the bureau's data is due. {len(leavers)} "
        f"leaver(s) still hold access."
        if leavers
        else "The quarter's review of who can reach the bureau's data is due."
    )
    finding = raise_finding(
        game, "ACCESS_REVIEW_DUE", reference, detail,
        "Review access and remove it from everyone who has left.", tick, at,
    )  # fmt: skip
    add(
        "COMPLIANCE_FINDING", Severity.WARNING, "The quarterly access review is due",
        f"{detail} Due by {finding.due_date:%d %B}.", {"screen": "compliance", "params": {}},
    )  # fmt: skip


def leavers_with_access(game: Game) -> list[Employee]:
    return list(
        Employee.objects.filter(
            organization=game.organization, is_active=False, has_system_access=True
        ).order_by("employee_number")
    )


def review_access(game: Game, tick: int) -> int:
    """Remove every leaver's access and settle the access findings. Returns how many lost it."""
    removed = Employee.objects.filter(
        organization=game.organization, is_active=False, has_system_access=True
    ).update(has_system_access=False)
    resolve_findings(game, tick, kind="ACCESS_REVIEW_DUE")
    return removed


# --- Consent ---------------------------------------------------------------------------


def improper_rate(game: Game, code: str) -> float:
    """The subscriber's hidden share of enquiries without consent on file, after sanctions."""
    low, high = IMPROPER_RATE
    rate = float(stream(game.world.seed, f"consent-rate:{code}").uniform(low, high))
    for kind in Sanction.objects.filter(game=game, subscriber_code=code).values_list(
        "kind", flat=True
    ):
        rate *= WARNING_FACTOR if kind == WARNING else SUSPENSION_FACTOR
    return rate


def grounds_held(game: Game, code: str, period: date, seq: int, memo: dict[object, Any]) -> bool:
    """Whether the subscriber holds the subject's consent for this enquiry."""
    key = ("improper-rate", code)
    if key not in memo:
        memo[key] = improper_rate(game, code)
    rng = stream(game.world.seed, f"grounds:{code}:{period:%Y%m}:{seq}")
    return bool(rng.random() >= memo[key])


def subscriber_suspended(game: Game, code: str, tick: int) -> bool:
    return Sanction.objects.filter(
        game=game, subscriber_code=code, kind=SUSPENSION, until_tick__gte=tick
    ).exists()


def sample_consent(game: Game, code: str, month: date, size: int, tick: int) -> ConsentCheck:
    """Ask a subscriber for the consent forms behind a sample of a month's enquiries."""
    if size not in SAMPLE_SIZES:
        raise DutyError(f"A sample is {', '.join(map(str, SAMPLE_SIZES))} enquiries")
    month = period_end(month.year, month.month)  # any day names its month
    start = month.replace(day=1)
    refs = list(  # the subscriber's own enquiries for its applicants that month
        EnquiryJudgement.objects.filter(
            game=game,
            enquiry__subscriber__subscriber_code=code,
            enquiry__enquired_at__date__gte=start,
            enquiry__enquired_at__date__lte=month,
        )
        .order_by("enquiry__enquiry_reference")
        .values_list("enquiry__enquiry_reference", flat=True)
    )
    if not refs:
        raise DutyError(f"{code} made no enquiries in {month:%B %Y}")
    number = (ConsentCheck.objects.filter(game=game).aggregate(n=Max("number"))["n"] or 0) + 1
    rng = stream(game.world.seed, f"consent-sample:{code}:{month:%Y%m}:{number}")
    picked = sorted(rng.choice(refs, size=min(size, len(refs)), replace=False).tolist())
    cal = Calendar(game.clock_start)
    today = cal.tick_start(max(tick, 1)).date()
    answer_day = add_working_days(today, CONSENT_ANSWER_WORKING_DAYS)
    return ConsentCheck.objects.create(
        game=game, number=number, subscriber_code=code, month=month, sample=picked,
        requested_tick=tick, answer_tick=cal.first_tick_of_day(cal.index_of(answer_day)),
    )  # fmt: skip


def answer_consent_checks(game: Game, tick: int, at: datetime, add: Any) -> None:
    """Subscribers send what consent forms they have; the forms missing are a finding."""
    for check in ConsentCheck.objects.filter(
        game=game, answered=False, answer_tick__lte=tick
    ).order_by("number"):
        held = dict(
            EnquiryJudgement.objects.filter(
                game=game, enquiry__enquiry_reference__in=check.sample
            ).values_list("enquiry__enquiry_reference", "grounds_held")
        )
        check.missing = [ref for ref in check.sample if not held.get(ref, True)]
        check.answered = True
        check.save(update_fields=["missing", "answered"])
        code = check.subscriber_code
        if not check.missing:
            add(
                "CONSENT_CHECKED", Severity.INFO, f"{code} showed consent for every enquiry asked",
                f"{len(check.sample)} enquiries from {check.month:%B %Y}.",
                {"screen": "compliance", "params": {}},
            )  # fmt: skip
            continue
        detail = (
            f"{code} could not show the subject's consent for {len(check.missing)} of the "
            f"{len(check.sample)} enquiries from {check.month:%B %Y} asked about."
        )
        finding = raise_finding(
            game, "CONSENT_MISSING", f"{code}-CHECK-{check.number}", detail,
            f"Warn {code}, or suspend its enquiries for a month.", tick, at,
        )  # fmt: skip
        add(
            "COMPLIANCE_FINDING", Severity.WARNING, f"Compliance finding: {code} lacks consent",
            f"{detail} Act by {finding.due_date:%d %B}.", {"screen": "compliance", "params": {}},
        )  # fmt: skip


def sanction(game: Game, code: str, kind: str, tick: int) -> Sanction:
    if kind not in (WARNING, SUSPENSION):
        raise DutyError(f"A sanction is a {WARNING} or a {SUSPENSION}")
    if kind == SUSPENSION and subscriber_suspended(game, code, tick):
        raise DutyError(f"{code} is already suspended")
    number = (Sanction.objects.filter(game=game).aggregate(n=Max("number"))["n"] or 0) + 1
    made = Sanction.objects.create(
        game=game, number=number, subscriber_code=code, kind=kind, tick=tick,
        until_tick=tick + SUSPENSION_WORKING_DAYS * TICKS_PER_DAY if kind == SUSPENSION else None,
    )  # fmt: skip
    resolve_findings(game, tick, kind="CONSENT_MISSING", reference__startswith=f"{code}-CHECK-")
    return made


# --- Retention -------------------------------------------------------------------------


def set_retention(game: Game, years: int) -> None:
    if years not in RETENTION_CHOICES:
        raise DutyError(f"Retention is one of {', '.join(map(str, RETENTION_CHOICES))} years")
    game.organization.retention_years = years
    game.organization.save(update_fields=["retention_years"])


def retention_breach(game: Game, enquiry: Enquiry, at: datetime, add: Any) -> None:
    """A report showed accounts the bureau should have let go: the regulator's finding."""
    held = int(enquiry.report.get("held_past_legal_limit") or 0)
    if not held:
        return
    _, created = RegulatorFinding.objects.get_or_create(
        game=game,
        kind="RETENTION_BREACH",
        reference=f"RETENTION-{at:%Y-%m}",
        defaults={
            "raised_at": at,
            "detail": f"Report {enquiry.enquiry_reference} showed {held} closed account(s) "
            f"kept past the legal {LEGAL_RETENTION_YEARS} years.",
        },
    )
    if created:
        add(
            "REGULATOR_FINDING", Severity.WARNING,
            "Regulator finding: reports show accounts kept too long",
            f"The legal limit is {LEGAL_RETENTION_YEARS} years after an account closes; ours "
            f"is {game.organization.retention_years}.", {"screen": "compliance", "params": {}},
        )  # fmt: skip


# --- Each morning ----------------------------------------------------------------------


def morning(game: Game, today: date, tick: int, at: datetime, add: Any) -> None:
    """Consent forms that have come in; then late returns and findings, to the regulator.

    Runs before the regulator's own morning review, which climbs the ladder.
    """
    answer_consent_checks(game, tick, at, add)
    for late in RegulatoryReturn.objects.filter(
        organization=game.organization, filed_at__isnull=True, due_date__lt=today
    ).order_by("period"):
        _, created = RegulatorFinding.objects.get_or_create(
            game=game,
            kind="MISSED_RETURN",
            reference=f"RETURN-{late.period:%Y-%m}",
            defaults={
                "raised_at": at,
                "detail": f"The return for {late.period:%B %Y} was not filed by "
                f"{late.due_date:%d %B %Y}.",
            },
        )
        if created:
            add(
                "REGULATOR_FINDING", Severity.WARNING,
                f"Regulator finding: the {late.period:%B} return is late",
                f"It was due on {late.due_date:%d %B}. File it now; findings add up.",
                {"screen": "compliance", "params": {}},
            )  # fmt: skip
    for finding in ComplianceFinding.objects.filter(
        game=game, resolved_tick__isnull=True, escalated=False, due_date__lt=today
    ).order_by("number"):
        finding.escalated = True
        finding.save(update_fields=["escalated"])
        RegulatorFinding.objects.get_or_create(
            game=game,
            kind="UNRESOLVED_FINDING",
            reference=f"FINDING-{finding.number}",
            defaults={
                "raised_at": at,
                "detail": f"Compliance finding {finding.number} ({finding.kind}) was not put "
                f"right by {finding.due_date:%d %B %Y}.",
            },
        )
        add(
            "REGULATOR_FINDING", Severity.WARNING,
            f"Regulator finding: compliance finding {finding.number} left unresolved",
            f"{finding.detail} It was due on {finding.due_date:%d %B}.",
            {"screen": "compliance", "params": {}},
        )  # fmt: skip
