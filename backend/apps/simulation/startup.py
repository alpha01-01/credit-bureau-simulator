"""The Startup scenario: a bureau built from capital (P3.13; PRD Section 4.2).

The bureau starts with its founding capital in the bank, its licence, and nothing
else. Each step needs the one before it, as in a real start:

1. **An office** (a year's rent in advance, and its furniture and computers). Staff
   need desks: hiring waits for an office, and an office has so many desks.
2. **IT**: servers, network and security set up by the hosting company; ready after
   ten working days. Until then no file can be received, no subscriber connected, and
   nothing is processed overnight.
3. **The first team**, hired from the month's candidates (HR).
4. **Providers**: the regulations oblige lenders to report to every licensed bureau,
   but each must be onboarded (a data-sharing agreement and a connection). An
   onboarded provider sends its whole book with the next month's files, and the
   database is built from those first files.
5. **The consumer credit report**, developed by Product Development.
6. **Contact-centre agents**, without whom a new subscriber cannot be welcomed.
7. **Subscribers**, signed by Sales and taken on by every department (P3.9).

The first report sold and the first invoice paid are the milestones.

ASSUMPTION A-084 (until reference R14 gives real set-up costs): the offices, set-up
costs and times below. Set-up costs are expensed when billed (a real bureau would
capitalise equipment and depreciate it). The board gives a startup its first year
before reviewing it, and the licence is taken as granted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from apps.bureau.providers.models import Institution
from apps.commercial.models import Product, Subscriber, UsageRecord
from apps.finance import payables
from apps.finance.events import open_startup_books
from apps.finance.models import Payment
from apps.org.models import Employee
from apps.world.models import Lender
from apps.world.provider_files.profiles import REPORTING_PROVIDERS

from . import economy, finance_dept, scenarios
from .compliance import add_working_days
from .models import Game, Notice, Onboarding, ProductDevelopment

SET_UP_ACCOUNT = "5950"
OFFICE_FITTER = ("FURNISHCO", "Accra Office Furnishings Ltd")
IT_SET_UP_DAYS = 10
IT_SET_UP_COST = Decimal("150000.00")
STARTUP_GRACE_MONTHS = 12  # the board's first review comes after a year


@dataclass(frozen=True)
class Office:
    code: str
    name: str
    monthly_rent: Decimal
    desks: int
    fit_out: Decimal  # furniture and computers


OFFICES = {
    o.code: o
    for o in (
        Office("SMALL", "A serviced office in Osu", Decimal("15000.00"), 10, Decimal("40000.00")),
        Office("STANDARD", "An office floor at Ridge", Decimal("45000.00"), 45,
               Decimal("120000.00")),
    )
}  # fmt: skip


class StartupError(Exception):
    pass


def is_startup(game: Game) -> bool:
    return game.scenario == scenarios.STARTUP


def set_up(game: Game) -> None:
    """The founding capital in the bank; no office, no systems, no staff, no agents."""
    org = game.organization
    org.office, org.has_systems, org.support_staff = "", False, 0
    org.save(update_fields=["office", "has_systems", "support_staff"])
    params = scenarios.parameters(game)
    capital = scenarios.STARTUP_CAPITAL + params.cash_adjustment
    eve = game.clock_start - timedelta(days=1)
    open_startup_books(org, capital, eve, _evening(eve))
    # The first budget is drawn up at the first month's start, from what it has by then.


def _evening(day: date) -> datetime:
    return datetime.combine(day, time(17, 0), tzinfo=UTC)


# --- Office and IT ------------------------------------------------------------------------


def office(game: Game) -> Office | None:
    return OFFICES.get(game.organization.office)


def desks_free(game: Game) -> int:
    found = office(game)
    if found is None:
        return 0
    staff = Employee.objects.filter(organization=game.organization, is_active=True).count()
    return found.desks - staff


def rent_office(game: Game, code: str, today: date, at: datetime, add: Any) -> Office:
    if code not in OFFICES:
        raise StartupError(f"{code!r} is not an office on offer")
    if game.organization.office:
        raise StartupError("The bureau already has an office")
    chosen = OFFICES[code]
    org = game.organization
    org.office = code
    org.save(update_fields=["office"])
    prices = economy.price_factor(game, today)
    month = f"{today:%Y%m}"
    for supplier, reference, description, account, amount in (
        (finance_dept.LANDLORD, f"RP-{month}", f"Office rent: the first 12 months in advance "
         f"({chosen.name})", "1300", chosen.monthly_rent * 12),
        (OFFICE_FITTER, f"FC-{month}", "Furniture and computers for the new office",
         SET_UP_ACCOUNT, chosen.fit_out),
    ):  # fmt: skip
        bill = payables.receive_bill(
            org, supplier, reference, description, account,
            economy.priced(scenarios.cost(game, amount), prices), today,
            today + timedelta(days=14), at,
        )  # fmt: skip
        finance_dept._announce(bill, add)
    return chosen


def set_up_it(game: Game, level: str, today: date, at: datetime, add: Any) -> date:
    from .it import CAPACITY

    org = game.organization
    if not org.office:
        raise StartupError("IT is installed in an office: rent one first")
    if org.has_systems:
        raise StartupError("IT has already been set up")
    if level not in CAPACITY:
        raise StartupError(f"{level} is not a capacity level")
    org.has_systems, org.it_capacity = True, level
    org.it_ready_on = add_working_days(today, IT_SET_UP_DAYS)
    org.save(update_fields=["has_systems", "it_capacity", "it_ready_on"])
    bill = payables.receive_bill(
        org, finance_dept.HOSTING, f"NC-SETUP-{today:%Y%m}",
        "Setting up servers, network and security", SET_UP_ACCOUNT,
        economy.priced(scenarios.cost(game, IT_SET_UP_COST), economy.price_factor(game, today)),
        today, today + timedelta(days=30), at,
    )  # fmt: skip
    finance_dept._announce(bill, add)
    return org.it_ready_on


def systems_ready(game: Game, day: date) -> bool:
    """IT has been set up and is ready (an established bureau's always is)."""
    org = game.organization
    return org.has_systems and (org.it_ready_on is None or org.it_ready_on <= day)


# --- Providers ----------------------------------------------------------------------------


def provider_prospects(game: Game) -> list[Lender]:
    """The reporting lenders the bureau has not onboarded."""
    onboarded = set(
        Institution.objects.filter(organization=game.organization).values_list(
            "institution_code", flat=True
        )
    )
    return [
        lender
        for lender in Lender.objects.filter(
            world=game.world, code__in=REPORTING_PROVIDERS
        ).order_by("seq_no")
        if lender.code not in onboarded
    ]


def onboard_provider(game: Game, code: str, today: date) -> Institution:
    from .bridge import onboard
    from .providers import relationship

    if not systems_ready(game, today):
        raise StartupError("A provider sends its files to the bureau's systems: set up IT first")
    lender = next((p for p in provider_prospects(game) if p.code == code), None)
    if lender is None:
        raise StartupError(f"{code} is not a provider the bureau could onboard")
    institution = onboard(game, lender, today)
    quality = scenarios.parameters(game).provider_quality
    if quality:
        found = relationship(game, code)
        found.quality = quality
        found.save(update_fields=["quality"])
    return institution


# --- Progress -----------------------------------------------------------------------------


def morning(game: Game, day: date, add: Any) -> None:
    """Systems ready; the first report sold; the first invoice paid."""
    if not is_startup(game):
        return
    org = game.organization
    if org.it_ready_on == day:
        add(
            "SYSTEMS_READY", "INFO", "The bureau's systems are ready",
            "Providers can now be onboarded and subscribers connected.",
            {"screen": "startup", "params": {}},
        )  # fmt: skip
    milestones = set(
        Notice.objects.filter(
            game=game, kind__in=("FIRST_REPORT_SOLD", "FIRST_PAYMENT")
        ).values_list("kind", flat=True)
    )
    if "FIRST_REPORT_SOLD" not in milestones and _sold(game).exists():
        add(
            "FIRST_REPORT_SOLD", "INFO", "The bureau has sold its first report",
            "A subscriber checked an applicant and the bureau had a file on them. It is "
            "billed with the month's usage.", {"screen": "enquiries", "params": {}},
        )  # fmt: skip
    if "FIRST_PAYMENT" not in milestones and _paid(game).exists():
        add(
            "FIRST_PAYMENT", "INFO", "A subscriber has paid for the bureau's reports",
            "The first invoice for reports has been paid: the bureau is earning from its data.",
            {"screen": "finance", "params": {}},
        )  # fmt: skip


def _sold(game: Game) -> Any:
    return UsageRecord.objects.filter(organization=game.organization, unit_price__gt=0)


def _paid(game: Game) -> Any:
    """Payments for invoices that bill reports."""
    return Payment.objects.filter(
        organization=game.organization, invoice__lines__product_code="CONSUMER_REPORT"
    )


def checklist(game: Game, today: date) -> list[dict[str, Any]]:
    """The steps to a working bureau, each done or not, with what it needs next."""
    org = game.organization
    staff = Employee.objects.filter(organization=org, is_active=True).count()
    providers = Institution.objects.filter(organization=org).count()
    files = org.submissions.count()
    report = Product.objects.filter(organization=org, product_code="CONSUMER_REPORT").exists()
    live = Subscriber.objects.filter(organization=org, is_active=True).count()
    joining = Onboarding.objects.filter(game=game, status="IN_PROGRESS").count()
    building = ProductDevelopment.objects.filter(game=game, code="CONSUMER_REPORT").first()
    ready_on = org.it_ready_on
    return [
        _step("OFFICE", "Rent an office", bool(org.office),
              OFFICES[org.office].name if org.office else "Staff need desks.", "startup"),
        _step("IT", "Set up IT", systems_ready(game, today),
              f"Ready on {ready_on:%d %B}" if org.has_systems and ready_on and ready_on > today
              else "Servers, network and security." if not org.has_systems else "Running.",
              "startup"),
        _step("TEAM", "Hire the first team", staff > 0,
              f"{staff} on the staff." if staff else "Data Officers process the files.", "staff"),
        _step("PROVIDERS", "Onboard providers", providers > 0,
              f"{providers} onboarded; {files} submission(s) received." if providers
              else "Their files build the database.", "startup"),
        _step("REPORT", "Develop the consumer credit report", report,
              "On sale." if report else f"In development; ready on {building.ready_on:%d %B}."
              if building is not None and building.ready_on else "Product Development builds it.",
              "products"),
        _step("AGENTS", "Hire contact-centre agents", org.support_staff > 0,
              f"{org.support_staff} agent(s)." if org.support_staff
              else "A new subscriber is welcomed by Support.", "support"),
        _step("SUBSCRIBERS", "Sign the first subscribers", live > 0,
              f"{live} live, {joining} joining." if live or joining
              else "Sales proposes; every department takes them on.", "sales"),
        _step("SOLD", "Sell the first report", _sold(game).exists(),
              "A subscriber checks an applicant the bureau has on file.", "enquiries"),
        _step("PAID", "Be paid for it", _paid(game).exists(),
              "Usage is invoiced at the month's start and paid on the subscriber's terms.",
              "finance"),
    ]  # fmt: skip


def _step(code: str, title: str, done: bool, detail: str, screen: str) -> dict[str, Any]:
    return {"code": code, "title": title, "done": done, "detail": detail, "screen": screen}


def view(game: Game, today: date) -> dict[str, Any]:
    from .it import CAPACITY

    return {
        "startup": is_startup(game),
        "steps": checklist(game, today),
        "office": game.organization.office or None,
        "desks_free": desks_free(game),
        "offices": [
            {
                "code": o.code,
                "name": o.name,
                "monthly_rent": str(scenarios.cost(game, o.monthly_rent)),
                "desks": o.desks,
                "fit_out": str(scenarios.cost(game, o.fit_out)),
            }
            for o in OFFICES.values()
        ],
        "it": {
            "set_up": game.organization.has_systems,
            "ready": systems_ready(game, today),
            "ready_on": game.organization.it_ready_on,
            "cost": str(scenarios.cost(game, IT_SET_UP_COST)),
            "days": IT_SET_UP_DAYS,
            "levels": list(CAPACITY),
        },
        "providers": [
            {"code": lender.code, "name": lender.name, "type": lender.lender_type}
            for lender in provider_prospects(game)
        ],
        "onboarded": [
            {"code": i.institution_code, "name": i.institution_name, "since": i.onboarding_date}
            for i in Institution.objects.filter(organization=game.organization).order_by(
                "institution_code"
            )
        ],
    }
