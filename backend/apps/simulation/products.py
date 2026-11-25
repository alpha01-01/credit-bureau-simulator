"""Product Development, a managed department (P3.10; Document 09).

A product is developed before it can be sold. The chief executive picks from a menu;
each product costs money and takes time, and is launched when it is ready. The score
(P3.6) needs both a scorecard from Data Analytics and the product built here; business
reports and batch enquiries (P3.11) are sold once developed.

ASSUMPTION A-080 (until real development costs): the work is contracted to a software
house, billed in full when it starts (30 days to pay); the costs and times are below.
Games begun before P3.10 sold the score without developing it, so it stays launched.

A startup (P3.13) develops the consumer credit report too; every other bureau has sold
it from the start, so it counts as launched wherever the bureau has it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from apps.commercial.models import Product
from apps.finance import payables

from . import finance_dept, scenarios
from .compliance import add_working_days
from .models import Game, ProductDevelopment

DEVELOPER = ("DEVWORKS", "DevWorks Software Ltd")
# What each developed product sells at (R8 placeholders, A-081): name, list price.
SOLD = {
    "BUSINESS_REPORT": ("Business credit report", Decimal("60.00")),
    "BATCH_ENQUIRY": ("Batch enquiry, per record", Decimal("13.50")),
}
ACCOUNT = "5900"
CONSUMER_REPORT = "CONSUMER_REPORT"


@dataclass(frozen=True)
class Offering:
    code: str
    name: str
    does: str
    cost: Decimal
    working_days: int


MENU = {
    o.code: o
    for o in (
        Offering(
            CONSUMER_REPORT, "Consumer credit report",
            "The bureau's core product: a person's accounts and their history from every "
            "provider, found by matching the applicant's identity. Lenders check it before "
            "they lend.",
            Decimal("90000.00"), 20,
        ),
        Offering(
            "CREDIT_SCORE", "Credit score",
            "A score, its band and reason codes on each report, sold as a separate line. "
            "Lenders buy it as far as the deployed scorecard predicts well.",
            Decimal("120000.00"), 30,
        ),
        Offering(
            "BUSINESS_REPORT", "Business credit report",
            "A report on a business: its facilities, dud cheques and court judgements, "
            "matched by registration number (P3.11).",
            Decimal("150000.00"), 40,
        ),
        Offering(
            "BATCH_ENQUIRY", "Batch enquiries",
            "A lender sends a file of applicants and gets back a file of reports, priced "
            "per record (P3.11).",
            Decimal("80000.00"), 25,
        ),
    )
}  # fmt: skip


class ProductError(Exception):
    pass


def sale_item(game: Game, code: str) -> Product:
    """The bureau's product for a developed offering, created on first sale."""
    name, price = SOLD[code]
    found, _ = Product.objects.get_or_create(
        organization=game.organization,
        product_code=code,
        defaults={"product_name": name, "list_price": price},
    )
    return found


def launched(game: Game, code: str) -> bool:
    """Whether the product may be sold."""
    if code == CONSUMER_REPORT:
        return Product.objects.filter(organization=game.organization, product_code=code).exists()
    return ProductDevelopment.objects.filter(
        game=game, code=code, launched_on__isnull=False
    ).exists()


def develop(game: Game, code: str, tick: int, today: date, at: datetime, add: Any) -> Any:
    """Start developing a product from the menu."""
    offering = MENU.get(code)
    if offering is None:
        raise ProductError(f"There is no product {code!r} to develop")
    found = ProductDevelopment.objects.filter(game=game, code=code).first()
    if launched(game, code):
        raise ProductError(f"The {offering.name.lower()} is already on sale")
    if found is not None and found.started_on is not None:
        raise ProductError(f"The {offering.name.lower()} is already being developed")
    project = found or ProductDevelopment(game=game, code=code)
    project.started_on, project.started_tick = today, tick
    project.ready_on = add_working_days(today, offering.working_days)
    project.cost = scenarios.cost(game, offering.cost)  # at the difficulty's prices (P3.13)
    project.save()
    bill = payables.receive_bill(
        game.organization, DEVELOPER, f"DW-{code}", f"Developing the {offering.name.lower()}",
        ACCOUNT, project.cost, today, today + timedelta(days=30), at,
    )  # fmt: skip
    finance_dept._announce(bill, add)
    if project.ready_on <= today:
        _launch(project, today, add)
    return project


def morning(game: Game, day: date, add: Any) -> None:
    for project in ProductDevelopment.objects.filter(
        game=game, launched_on__isnull=True, ready_on__lte=day
    ).order_by("code"):
        _launch(project, day, add)


def _launch(project: ProductDevelopment, day: date, add: Any) -> None:
    project.launched_on = day
    project.save(update_fields=["launched_on"])
    offering = MENU[project.code]
    if project.code == CONSUMER_REPORT:  # a startup's report goes on its price list
        from .demand import REFERENCE_PRICE

        Product.objects.get_or_create(
            organization=project.game.organization,
            product_code=CONSUMER_REPORT,
            defaults={"product_name": offering.name, "list_price": REFERENCE_PRICE},
        )
    add(
        "PRODUCT_LAUNCHED", "INFO", f"The {offering.name.lower()} is ready to sell",
        offering.does, {"screen": "products", "params": {}},
    )  # fmt: skip
