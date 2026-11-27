"""P3.11 — Business credit reports and batch enquiries.

Done when (Document 09): a business report shows exactly the business's facilities,
cheques and judgments as loaded; a batch file is answered record by record, with hits
and misses that agree with single enquiries; both are billed correctly.
"""

from __future__ import annotations

import csv
import dataclasses
import io
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from django.db import transaction
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bureau.core.models import (
    CourtJudgment,
    Customer,
    CustomerType,
    DishonouredCheque,
    Enquiry,
    IdentifierType,
)
from apps.bureau.reports.batch import BATCH_ENQUIRY, answer_batch, result_file
from apps.bureau.reports.enquiries import (
    BUSINESS_REPORT,
    _mask,
    _retained,
    build_business_report,
    enquire,
)
from apps.bureau.reports.models import BatchFile, BatchRecord
from apps.commercial.models import Subscriber, UsageRecord
from apps.finance.models import InvoiceLine
from apps.simulation import controls, products
from apps.simulation.bridge import start_game
from apps.simulation.fingerprint import differences, fingerprint
from apps.simulation.models import Game
from apps.world.generation import build_world
from apps.world.generation.persist import write_world
from apps.world.models import World

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.slow]


@pytest.fixture(autouse=True)
def _storage(settings: Any, tmp_path: Path) -> None:
    settings.STORAGE_ROOT = tmp_path


@pytest.fixture(autouse=True)
def _developed_at_once(monkeypatch: Any) -> None:
    """Both products are developed in no time here (P3.10 tests the development)."""
    for code in (BUSINESS_REPORT, BATCH_ENQUIRY):
        quick = dataclasses.replace(products.MENU[code], working_days=0)
        monkeypatch.setitem(products.MENU, code, quick)


@pytest.fixture
def world(db: None) -> World:
    g = build_world(81, "small")
    return World.objects.get(
        pk=write_world(g.config, g.people, g.businesses, g.branches, g.result, g.stats)
    )


def _game(world: World, owner: User | None = None) -> Game:
    return controls.set_pause_rules(
        start_game(world, owner=owner, history_months=12), [], deadlines=False
    )


def _today(game: Game) -> date:
    return controls.state(game).now.date()


def _next_month(game: Game) -> Game:
    month = _today(game).month
    while _today(game).month == month:
        game = controls.advance_by(game, "next_event")
    return game


def test_a_business_report_shows_exactly_what_was_loaded(world: World) -> None:
    owner = User.objects.create_user("chief")
    game = _game(world, owner)
    org = game.organization
    at = controls.state(game).now

    # Every business on file: its report against what the bureau loaded for it.
    businesses = Customer.objects.filter(organization=org, customer_type=CustomerType.BUSINESS)
    assert businesses.exists()
    with_cheques = with_judgments = 0
    for customer in businesses.select_related("business"):
        report = build_business_report(customer, at)
        profile = customer.business
        assert report["layout"] == "SIMB-B1"
        assert report["subject"]["registration_number"] == (profile.registration_number or None)
        assert report["subject"]["registered_name"] == profile.registered_name
        retained, _ = _retained(customer, at.date(), game.organization.retention_years)
        assert sorted(
            (f["lender"], f["account"], f["original_amount"]) for f in report["facilities"]
        ) == sorted(
            (a.institution.institution_name, _mask(a.facility_account_number),
             str(a.original_amount))
            for a in retained
        )  # fmt: skip
        cheques = DishonouredCheque.objects.filter(customer=customer, date_bounced__lte=at.date())
        assert sorted(
            (c["account_number"], c["cheque_number"], c["amount"])
            for c in report["dishonoured_cheques"]
        ) == sorted((c.account_number, c.cheque_number, str(c.amount)) for c in cheques)
        judgments = CourtJudgment.objects.filter(customer=customer, filing_date__lte=at.date())
        assert sorted((j["case_number"], j["amount"]) for j in report["judgments"]) == sorted(
            (j.case_number, str(j.amount)) for j in judgments
        )
        with_cheques += bool(cheques)
        with_judgments += bool(judgments)
    print(f"{businesses.count()} businesses, {with_cheques} with cheques, "  # noqa: T201
          f"{with_judgments} with judgments")  # fmt: skip
    assert with_cheques and with_judgments  # the comparison covered both

    # Until it is developed, lenders check businesses with the consumer report.
    game = controls.advance_by(game, "day", 3)
    on_business = Enquiry.objects.filter(
        organization=org, identifier_type=IdentifierType.BUSINESS_REGISTRATION
    )
    assert not on_business.filter(product_code=BUSINESS_REPORT).exists()
    client = APIClient()
    client.force_authenticate(owner)
    assert (
        client.post(f"/api/v1/games/{game.pk}/products/", {"code": BUSINESS_REPORT}).status_code
        == 200
    )
    launched = controls.state(game).now
    game = _next_month(game)  # a month of business applications, then its invoices
    sold = on_business.filter(product_code=BUSINESS_REPORT, enquired_at__gt=launched)
    assert sold.exists()
    assert (
        not on_business.filter(enquired_at__gt=launched)
        .exclude(product_code=BUSINESS_REPORT)
        .exists()
    )  # every business checked since has had the business report
    hit = sold.filter(customer__isnull=False).first()
    assert hit is not None and hit.report["layout"] == "SIMB-B1" and "facilities" in hit.report
    usage = UsageRecord.objects.filter(organization=org, product__product_code=BUSINESS_REPORT)
    assert usage.count() == sold.count()  # one charge per business report
    assert {u.unit_price for u in usage} == {Decimal("60.00")}
    lines = InvoiceLine.objects.filter(invoice__organization=org, product_code=BUSINESS_REPORT)
    billed = usage.filter(usage_at__date__lt=_today(game).replace(day=1))
    assert sum(x.quantity for x in lines) == billed.count() > 0
    assert sum(x.amount for x in lines) == Decimal("60.00") * billed.count()

    copy = controls.replay(Game.objects.get(pk=game.pk), start_game(world, history_months=12))
    game = Game.objects.get(pk=game.pk)
    assert fingerprint(copy) == fingerprint(game), differences(copy, game)


def test_a_batch_is_answered_record_by_record_like_single_enquiries(world: World) -> None:
    game = _game(world)
    org = game.organization
    controls.develop_product(game, BATCH_ENQUIRY)
    game = _next_month(game)  # the month's batch files arrive at its start
    batches = BatchFile.objects.filter(organization=org)
    assert batches.exists()
    records = BatchRecord.objects.filter(batch__organization=org).select_related("enquiry")
    assert sum(b.records for b in batches) == records.count()
    for b in batches:
        assert b.hits == records.filter(batch=b, enquiry__customer__isnull=False).count()
        assert 0 < b.hits < b.records  # some found, some not on file
        returned = list(csv.DictReader(io.StringIO(result_file(b))))
        assert [int(x["row"]) for x in returned] == list(range(1, b.records + 1))

    # Each record, searched alone at the same moment, finds the same subject, or nobody,
    # with the same accounts. (The batch is sent again here and searched record by record
    # against the same data; undone afterwards, so the game still replays.)
    subscriber = Subscriber.objects.filter(organization=org, is_active=True).first()
    sent = [(r.identifier_type, r.identifier_value, r.subject_name)
            for r in records.order_by("batch__reference", "row_number")]  # fmt: skip
    now = controls.state(game).now
    with transaction.atomic():
        again = answer_batch(org, subscriber, "TEST-BATCH", sent, "NEW_CREDIT", now)
        for r in again.rows.select_related("enquiry").order_by("row_number"):
            single = enquire(
                org, subscriber, "CONSUMER_REPORT", "NEW_CREDIT", "TEST", r.identifier_type,
                r.identifier_value, r.subject_name, now,
            )  # fmt: skip
            assert single.outcome == r.enquiry.outcome
            assert single.customer_id == r.enquiry.customer_id
            assert single.report.get("accounts") == r.enquiry.report.get("accounts")
        assert again.records == len(sent) and again.hits == sum(
            r.enquiry.customer_id is not None for r in again.rows.select_related("enquiry")
        )
        transaction.set_rollback(True)

    # Billed per record at the batch price, then invoiced with the month's usage.
    usage = UsageRecord.objects.filter(organization=org, product__product_code=BATCH_ENQUIRY)
    assert usage.count() == records.count()
    assert {u.unit_price for u in usage} == {Decimal("13.50")}
    game = _next_month(game)
    lines = InvoiceLine.objects.filter(invoice__organization=org, product_code=BATCH_ENQUIRY)
    assert sum(x.quantity for x in lines) == records.count()
    assert sum(x.amount for x in lines) == Decimal("13.50") * records.count()

    copy = controls.replay(Game.objects.get(pk=game.pk), start_game(world, history_months=12))
    game = Game.objects.get(pk=game.pk)
    assert fingerprint(copy) == fingerprint(game), differences(copy, game)
