"""When the bureau's business events happen in game time (roadmap S7).

  Game start          books opened with an established bureau's position
  Month start         rent and IT hosting; last month's usage invoiced; each
                      invoice's payment scheduled by the subscriber's habits;
                      payroll taxes due on the 14th; VAT due at month end
  Last working day    salaries paid (after the day's work)

When subscribers pay is world behaviour (ASSUMPTION A-035): each has its
own habit of paying early or late, drawn from the seed.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from apps.finance.events import (
    REMITTANCE_DAY,
    file_vat,
    invoice_usage,
    month_start_costs,
    open_books,
    outstanding,
    receive_payment,
    remit_payroll_taxes,
)
from apps.finance.models import Invoice
from apps.standards.calendar import is_working_day, next_working_day
from apps.world.generation.rng import stream

from .clock import Calendar, previous_month_end
from .models import EventType, Game, ScheduledEvent

PAYMENT_TIME = time(10, 0)


def open_game_books(game: Game) -> None:
    opening = game.clock_start - timedelta(days=1)
    open_books(game.organization, opening, datetime.combine(opening, time(17, 0), tzinfo=UTC))


def last_working_day(day: date) -> date:
    candidate = (day.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    while not is_working_day(candidate):
        candidate -= timedelta(days=1)
    return candidate


def month_start(game: Game, cal: Calendar, tick: int, sequence: int) -> int:
    """Post the month's opening costs and bill last month. Returns the next event sequence."""
    at = cal.tick_start(tick)
    today = at.date()
    first = today.replace(day=1)
    org = game.organization
    month_start_costs(org, first, at)

    # Invoices are dated the last day of the month the service was delivered, so the
    # revenue (and the VAT on it) belongs to that month, as accrual accounting requires.
    previous_end = previous_month_end(today)
    invoices = invoice_usage(org, previous_end.replace(day=1), previous_end, previous_end, at)
    events = []
    for invoice in invoices:
        paid_on = _payment_date(game, invoice)
        events.append(
            ScheduledEvent(
                game=game,
                event_type=EventType.SUBSCRIBER_PAYMENT,
                due_tick=max(
                    cal.tick_at(datetime.combine(paid_on, PAYMENT_TIME, tzinfo=UTC)), tick
                ),
                sequence=sequence,
                payload={"invoice": invoice.invoice_number, "paid_on": paid_on.isoformat()},
            )
        )
        sequence += 1
    remit_on = next_working_day(first.replace(day=REMITTANCE_DAY))
    vat_on = last_working_day(first)
    for event_type, on in (
        (EventType.PAYROLL_TAX_REMITTANCE, remit_on),
        (EventType.VAT_RETURN, vat_on),
    ):
        events.append(
            ScheduledEvent(
                game=game,
                event_type=event_type,
                due_tick=max(cal.tick_at(datetime.combine(on, PAYMENT_TIME, tzinfo=UTC)), tick),
                sequence=sequence,
                payload={"on": on.isoformat()},
            )
        )
        sequence += 1
    ScheduledEvent.objects.bulk_create(events)
    return sequence


def _payment_date(game: Game, invoice: Invoice) -> date:
    """Due date, shifted by the subscriber's habit and this month's circumstances."""
    code = invoice.subscriber.subscriber_code
    habit = float(stream(game.world.seed, f"payer-habit:{code}").normal(4.0, 7.0))
    noise = float(stream(game.world.seed, f"payment:{invoice.invoice_number}").normal(0.0, 4.0))
    days = max(5, round((invoice.due_date - invoice.issue_date).days + habit + noise))
    return next_working_day(invoice.issue_date + timedelta(days=days))


def handle(game: Game, event: ScheduledEvent, at: datetime) -> None:
    org = game.organization
    if event.event_type == EventType.SUBSCRIBER_PAYMENT:
        invoice = Invoice.objects.get(organization=org, invoice_number=event.payload["invoice"])
        amount = outstanding(invoice)
        if amount > 0:
            receive_payment(invoice, amount, date.fromisoformat(event.payload["paid_on"]), at)
    elif event.event_type == EventType.PAYROLL_TAX_REMITTANCE:
        remit_payroll_taxes(org, date.fromisoformat(event.payload["on"]), at)
    elif event.event_type == EventType.VAT_RETURN:
        file_vat(org, date.fromisoformat(event.payload["on"]), at)


FINANCE_EVENTS = {
    EventType.SUBSCRIBER_PAYMENT,
    EventType.PAYROLL_TAX_REMITTANCE,
    EventType.VAT_RETURN,
}
