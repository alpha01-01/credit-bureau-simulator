"""API for the game screens (roadmap S8).

Everything the player sees is bureau-side data at the current game time.
Nothing here reveals world truth: correct answers, real identities and true
coverage stay hidden until the debrief.

Every dashboard figure carries a ``drill`` target: the screen and filters
that list the records behind it ("Why?", Document 07, Section 13.1).
"""

from __future__ import annotations

import threading
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import close_old_connections, connection
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from apps.bureau.core.models import (
    AccountObservation,
    CreditAccount,
    Customer,
    CustomerIdentifier,
    Enquiry,
    EnquiryOutcome,
)
from apps.bureau.quality.models import ValidationIssue
from apps.bureau.submissions.intake import due_date_for
from apps.bureau.submissions.models import (
    FileStatus,
    ProcessingRun,
    Submission,
)
from apps.commercial.models import UsageRecord
from apps.finance import statements
from apps.finance.events import outstanding
from apps.finance.ledger import BANK, REVENUE
from apps.finance.models import Invoice, JournalEntry
from apps.standards.calendar import is_working_day
from apps.standards.submission_template import OPEN_STATUS_CODES
from apps.workitems.models import ItemStatus, WorkItem
from apps.world.models import World

from . import controls
from .api import _game
from .bridge import start_game
from .clock import previous_month_end
from .history import DEFAULT_HISTORY_MONTHS, preload_history
from .models import Game

# --- Worlds and games -----------------------------------------------------------------


@api_view(["GET"])
def worlds(request: Request) -> Response:
    return Response(
        [
            {
                "id": w.pk,
                "seed": w.seed,
                "scale": w.scale,
                "history_end": w.config.get("history_end"),
            }
            for w in World.objects.order_by("pk")
        ]
    )


def _game_summary(game: Game) -> dict[str, Any]:
    clock = controls.state(game).as_dict() if game.setup_status == "READY" else None
    return {
        "id": game.pk,
        "bureau": game.organization.name,
        "world": game.world_id,
        "setup_status": game.setup_status,
        "setup_message": game.setup_message,
        "clock": clock,
    }


@api_view(["GET", "POST"])
def games(request: Request) -> Response:
    if request.method == "GET":
        mine = Game.objects.filter(owner_id=request.user.pk).select_related("organization", "world")
        return Response([_game_summary(g) for g in mine.order_by("-pk")])

    world = get_object_or_404(World, pk=request.data.get("world"))
    months = int(request.data.get("history_months", DEFAULT_HISTORY_MONTHS))
    if not 0 <= months <= 24:
        return Response({"detail": "history_months must be 0 to 24"}, status=400)
    game = start_game(world, owner=request.user)
    if months:
        Game.objects.filter(pk=game.pk).update(
            setup_status="PREPARING", setup_message="Waiting to load history"
        )
        if getattr(settings, "SIMB_SETUP_IN_BACKGROUND", True):
            threading.Thread(target=_prepare, args=(game.pk, months), daemon=True).start()
        else:
            _prepare(game.pk, months)
    game.refresh_from_db()
    return Response(_game_summary(game), status=status.HTTP_201_CREATED)


def _prepare(game_id: int, months: int) -> None:
    """Pre-load an established bureau's history (normally in a background thread)."""
    background = threading.current_thread() is not threading.main_thread()
    if background:
        close_old_connections()
    try:
        game = Game.objects.select_related("world", "organization").get(pk=game_id)

        def progress(message: str) -> None:
            Game.objects.filter(pk=game_id).update(setup_message=message[:200])

        preload_history(game, months, progress)
        Game.objects.filter(pk=game_id).update(setup_status="READY", setup_message="")
    except Exception as exc:  # the player must see why setup failed
        Game.objects.filter(pk=game_id).update(setup_status="FAILED", setup_message=str(exc)[:200])
        raise
    finally:
        if background:
            connection.close()


@api_view(["GET"])
def game_detail(request: Request, game_id: int) -> Response:
    return Response(_game_summary(_game(request, game_id)))


# --- Dashboard ---------------------------------------------------------------------------


def _today(game: Game) -> date:
    return controls.state(game).now.date()


def _metric(
    key: str, label: str, value: Any, unit: str, screen: str, **params: Any
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "value": value,
        "unit": unit,
        "drill": {"screen": screen, "params": {k: str(v) for k, v in params.items()}},
    }


@api_view(["GET"])
def dashboard(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    org = game.organization
    today = _today(game)
    month_start = today.replace(day=1)
    income = statements.income_statement(org, month_start, today)
    cash = statements.cash_position(org, today)
    enquiries = Enquiry.objects.filter(organization=org, enquired_at__date__gte=month_start)
    total = enquiries.count()
    hits = enquiries.filter(outcome=EnquiryOutcome.HIT).count()
    backlog = WorkItem.objects.filter(
        organization=org, status__in=[ItemStatus.OPEN, ItemStatus.IN_PROGRESS]
    ).count()
    submissions = Submission.objects.filter(organization=org, received_at__date__gte=month_start)
    billable = UsageRecord.objects.filter(
        organization=org, usage_at__date__gte=month_start, usage_at__date__lte=today
    ).aggregate(total=Sum("unit_price"))["total"] or Decimal("0.00")
    return Response(
        {
            "as_of": today,
            "metrics": [
                _metric(
                    "revenue",
                    "Revenue booked this month",
                    income["total_income"],
                    "GHS",
                    "ledger",
                    account=REVENUE,
                    start=month_start,
                ),
                _metric(
                    "usage",
                    "Billable usage this month",
                    billable,
                    "GHS",
                    "enquiries",
                    start=month_start,
                ),
                _metric("cash", "Cash at bank", cash["bank"], "GHS", "ledger", account=BANK),
                _metric(
                    "receivables",
                    "Owed by subscribers",
                    cash["receivables"],
                    "GHS",
                    "invoices",
                    unpaid="1",
                ),
                _metric("backlog", "Work items waiting", backlog, "items", "queue", status="OPEN"),
                _metric(
                    "enquiries",
                    "Enquiries this month",
                    total,
                    "enquiries",
                    "enquiries",
                    start=month_start,
                ),
                _metric(
                    "hit_rate",
                    "Hit rate this month",
                    round(hits / total, 3) if total else None,
                    "share",
                    "enquiries",
                    start=month_start,
                    outcome="NO_HIT",
                ),
                _metric(
                    "customers",
                    "Customers on file",
                    Customer.objects.filter(organization=org).count(),
                    "customers",
                    "customers",
                ),
                _metric(
                    "accounts",
                    "Open accounts",
                    CreditAccount.objects.filter(
                        organization=org, account_status__in=OPEN_STATUS_CODES
                    ).count(),
                    "accounts",
                    "customers",
                ),
                _metric(
                    "submissions",
                    "Files received this month",
                    submissions.count(),
                    "submissions",
                    "submissions",
                    start=month_start,
                ),
            ],
        }
    )


# --- Morning briefing and inbox ----------------------------------------------------------


def _previous_working_day(day: date) -> date:
    day -= timedelta(days=1)
    while not is_working_day(day):
        day -= timedelta(days=1)
    return day


@api_view(["GET"])
def briefing(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    org = game.organization
    today = _today(game)
    yesterday = _previous_working_day(today)

    received = Submission.objects.filter(organization=org, received_at__date=yesterday)
    runs = ProcessingRun.objects.filter(submission__organization=org, completed_at__date=yesterday)
    run_totals = runs.aggregate(
        received=Sum("records_received"), accepted=Sum("records_accepted"),
        unloadable=Sum("records_unloadable"), pending=Sum("records_pending"),
    )  # fmt: skip
    items = WorkItem.objects.filter(organization=org)
    enquiries = Enquiry.objects.filter(organization=org, enquired_at__date=yesterday)
    return Response(
        {
            "today": today,
            "yesterday": yesterday,
            "files_received": [
                {"reference": s.submission_reference, "provider": s.institution.institution_code}
                for s in received.select_related("institution")
            ],
            "records": {k: v or 0 for k, v in run_totals.items()},
            "work": {
                "waiting": items.filter(
                    status__in=[ItemStatus.OPEN, ItemStatus.IN_PROGRESS]
                ).count(),
                "resolved_yesterday": items.filter(
                    status=ItemStatus.DONE, case__decided_at__date=yesterday
                ).count(),
            },
            "enquiries": {
                "count": enquiries.count(),
                "hits": enquiries.filter(outcome=EnquiryOutcome.HIT).count(),
            },
            "inbox": _inbox(game, today),
        }
    )


def _inbox(game: Game, today: date) -> list[dict[str, Any]]:
    """Things that need attention, oldest first. Derived from the bureau's own data."""
    org = game.organization
    messages: list[dict[str, Any]] = []
    period = previous_month_end(today)
    due = due_date_for(period)
    if today > due:
        for institution in org.institutions.filter(is_active=True).order_by("institution_code"):
            if not Submission.objects.filter(
                institution=institution, reporting_period=period
            ).exists():
                messages.append(
                    {
                        "severity": "WARNING",
                        "title": f"{institution.institution_name} has not submitted {period:%B} data",
                        "detail": f"Due {due:%d %B}; {(today - due).days} days overdue.",
                        "drill": {
                            "screen": "submissions",
                            "params": {"provider": institution.institution_code},
                        },
                    }
                )
    for submission in (
        Submission.objects.filter(
            organization=org,
            received_at__date__gte=today - timedelta(days=7),
            files__file_status=FileStatus.REJECTED,
        )
        .distinct()
        .select_related("institution")
    ):
        messages.append(
            {
                "severity": "ERROR",
                "title": f"File rejected: {submission.institution.institution_name}",
                "detail": f"{submission.submission_reference}: a file did not pass the file checks.",
                "drill": {
                    "screen": "submission",
                    "params": {"reference": submission.submission_reference},
                },
            }
        )
    overdue = [
        i for i in Invoice.objects.filter(organization=org, due_date__lt=today).select_related("subscriber")
        if outstanding(i) > 0
    ]  # fmt: skip
    for invoice in overdue:
        messages.append(
            {
                "severity": "WARNING",
                "title": f"Invoice {invoice.invoice_number} is overdue",
                "detail": f"{invoice.subscriber.subscriber_name} owes GHS {outstanding(invoice):,.2f}, due {invoice.due_date:%d %B}.",
                "drill": {"screen": "invoices", "params": {"unpaid": "1"}},
            }
        )
    return messages


# --- Submissions -----------------------------------------------------------------------


@api_view(["GET"])
def submissions(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    rows = Submission.objects.filter(organization=game.organization).select_related("institution")
    if provider := request.query_params.get("provider"):
        rows = rows.filter(institution__institution_code=provider)
    if start := request.query_params.get("start"):
        rows = rows.filter(received_at__date__gte=start)
    out = []
    for s in rows.order_by("-received_at", "-submission_reference")[:300]:
        run = s.runs.order_by("-run_number").first()
        out.append(
            {
                "reference": s.submission_reference,
                "provider": s.institution.institution_code,
                "provider_name": s.institution.institution_name,
                "period": s.reporting_period,
                "received_at": s.received_at,
                "due_date": s.due_date,
                "late": s.is_late,
                "status": s.submission_status,
                "received": run.records_received if run else None,
                "accepted": run.records_accepted if run else None,
                "unloadable": run.records_unloadable if run else None,
                "duplicates": run.records_duplicated if run else None,
                "pending": run.records_pending if run else None,
            }
        )
    return Response(out)


@api_view(["GET"])
def submission_detail(request: Request, game_id: int, reference: str) -> Response:
    game = _game(request, game_id)
    s = get_object_or_404(
        Submission.objects.select_related("institution"),
        organization=game.organization,
        submission_reference=reference,
    )
    runs = []
    for run in s.runs.order_by("run_number"):
        issues = (
            ValidationIssue.objects.filter(run=run)
            .values("rule_code", "severity", "message")
            .annotate(count=Count("id"))
            .order_by("-count", "rule_code")
        )
        runs.append(
            {
                "run_number": run.run_number,
                "started_at": run.started_at,
                "completed_at": run.completed_at,
                "status": run.processing_status,
                "received": run.records_received,
                "accepted": run.records_accepted,
                "unloadable": run.records_unloadable,
                "duplicates": run.records_duplicated,
                "pending": run.records_pending,
                "reconciles": run.reconciles,
                "customers_created": run.customers_created,
                "accounts_created": run.accounts_created,
                "issues": list(issues),
                "examples": [
                    {
                        "row": i.source_row_number,
                        "file": i.file.file_name,
                        "rule": i.rule_code,
                        "field": i.field,
                        "value": i.value,
                    }
                    for i in ValidationIssue.objects.filter(run=run, severity="ERROR")
                    .select_related("file")
                    .order_by("file__file_name", "source_row_number")[:50]
                ],
            }
        )
    return Response(
        {
            "reference": s.submission_reference,
            "provider": s.institution.institution_name,
            "period": s.reporting_period,
            "received_at": s.received_at,
            "due_date": s.due_date,
            "late": s.is_late,
            "status": s.submission_status,
            "files": [
                {
                    "name": f.file_name,
                    "kind": f.file_kind,
                    "format": f.file_format,
                    "size": f.file_size_bytes,
                    "sha256": f.file_hash,
                    "status": f.file_status,
                    "rejection_reason": f.rejection_reason,
                }
                for f in s.files.order_by("file_name")
            ],
            "runs": runs,
        }
    )


# --- Customers -----------------------------------------------------------------------------


@api_view(["GET"])
def customers(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    org = game.organization
    q = (request.query_params.get("q") or "").strip()
    rows = Customer.objects.filter(organization=org).select_related("individual", "business")
    if q:
        by_identifier = CustomerIdentifier.objects.filter(
            organization=org, identifier_value__iexact=q
        ).values("customer_id")
        rows = rows.filter(
            Q(customer_reference__iexact=q)
            | Q(pk__in=by_identifier)
            | Q(individual__last_name__icontains=q)
            | Q(individual__first_name__icontains=q)
            | Q(business__registered_name__icontains=q)
        )
    return Response([_customer_summary(c) for c in rows.order_by("customer_reference")[:100]])


def _customer_summary(c: Customer) -> dict[str, Any]:
    individual = getattr(c, "individual", None)
    business = getattr(c, "business", None)
    name = (
        f"{individual.first_name} {individual.last_name}"
        if individual
        else (business.registered_name if business else "")
    )
    return {"reference": c.customer_reference, "type": c.customer_type, "name": name}


@api_view(["GET"])
def customer_detail(request: Request, game_id: int, reference: str) -> Response:
    game = _game(request, game_id)
    c = get_object_or_404(
        Customer.objects.select_related("individual", "business"),
        organization=game.organization,
        customer_reference=reference,
    )
    individual = getattr(c, "individual", None)
    accounts = []
    for a in c.accounts.select_related("institution").order_by(
        "institution__institution_code", "facility_account_number"
    ):
        observations = AccountObservation.objects.filter(
            credit_account=a, is_current=True
        ).order_by("reporting_date")
        accounts.append(
            {
                "lender": a.institution.institution_name,
                "account_number": a.facility_account_number,
                "facility_type": a.facility_type,
                "opened": a.disbursement_date,
                "original_amount": a.original_amount,
                "status": a.account_status,
                "observations": [
                    {
                        "date": o.reporting_date,
                        "balance": o.outstanding_balance,
                        "arrears": o.arrears_amount,
                        "days_past_due": o.days_past_due,
                        "status": o.facility_status,
                        "source": f"{o.source_file.file_name} row {o.source_row_number}",
                    }
                    for o in observations.select_related("source_file")
                ],
            }
        )
    return Response(
        _customer_summary(c)
        | {
            "date_of_birth": individual.date_of_birth if individual else None,
            "gender": individual.gender_code if individual else None,
            "identifiers": [
                {"type": i.identifier_type, "value": i.identifier_value}
                for i in c.identifiers.order_by("identifier_type")
            ],
            "contacts": [
                {"value": x.contact_value, "primary": x.is_primary}
                for x in c.contacts.order_by("-is_primary", "contact_value")
            ],
            "provider_links": [
                {
                    "provider": link.institution.institution_code,
                    "number": link.provider_customer_number,
                }
                for link in c.provider_links.select_related("institution").order_by("pk")
            ],
            "accounts": accounts,
            "enquiries": [
                {
                    "reference": e.enquiry_reference,
                    "subscriber": e.subscriber.subscriber_code,
                    "at": e.enquired_at,
                    "purpose": e.purpose,
                }
                for e in c.enquiries.select_related("subscriber").order_by("-enquired_at")[:20]
            ],
        }
    )


# --- Ledger and invoices ---------------------------------------------------------------------


@api_view(["GET"])
def ledger(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    entries = JournalEntry.objects.filter(organization=game.organization)
    if account := request.query_params.get("account"):
        entries = entries.filter(lines__account__code=account).distinct()
    if start := request.query_params.get("start"):
        entries = entries.filter(transaction_date__gte=start)
    rows = entries.order_by("-transaction_date", "-journal_reference").prefetch_related(
        "lines__account"
    )[:200]
    return Response(
        [
            {
                "reference": e.journal_reference,
                "date": e.transaction_date,
                "description": e.description,
                "source": e.source_type,
                "lines": [
                    {
                        "account": f"{line.account.code} {line.account.name}",
                        "debit": line.debit,
                        "credit": line.credit,
                    }
                    for line in e.lines.all()
                ],
            }
            for e in rows
        ]
    )


@api_view(["GET"])
def invoices(request: Request, game_id: int) -> Response:
    game = _game(request, game_id)
    rows = []
    for i in (
        Invoice.objects.filter(organization=game.organization)
        .select_related("subscriber")
        .order_by("-issue_date", "-invoice_number")[:200]
    ):
        owed = outstanding(i)
        if request.query_params.get("unpaid") and owed <= 0:
            continue
        rows.append(
            {
                "number": i.invoice_number,
                "subscriber": i.subscriber.subscriber_name,
                "period": i.period_start,
                "issued": i.issue_date,
                "due": i.due_date,
                "total": i.total,
                "outstanding": owed,
            }
        )
    return Response(rows)
