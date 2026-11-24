"""Batch enquiries from subscribers (P3.11).

ASSUMPTION A-081 (until real batch volumes and prices):

* Once Product Development has launched batch enquiries, at each month's start each
  active subscriber sends a batch file with chance 1 in 2: between 40 and 120 people
  from the world (a lender's list of applicants for a scheme), searched by Ghana Card
  for the purpose of new credit.
* Each record is priced at the detailed report's list price less 10% (GHS 13.50),
  billed with the month's usage. A bureau whose systems are down, or that the
  regulator has suspended, cannot take the files that month.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from apps.bureau.core.models import IdentifierType
from apps.bureau.reports.batch import BATCH_ENQUIRY, answer_batch
from apps.commercial.models import Subscriber, UsageRecord
from apps.world.generation.rng import stream
from apps.world.models import Person

from . import compliance, it, products, scoreproduct
from .models import Game

BATCH_CHANCE = 0.5
BATCH_SIZE = (40, 121)


def month_start(game: Game, today: date, tick: int, at: datetime, add: Any) -> int:
    """This month's batch files, answered as they arrive. Returns the records answered."""
    if not products.launched(game, BATCH_ENQUIRY):
        return 0
    if compliance.suspended(game) or it.systems_down(game, tick):
        return 0
    people = list(
        Person.objects.filter(world=game.world).order_by("pk").values_list("pk", flat=True)
    )
    if not people:
        return 0
    item = products.sale_item(game, BATCH_ENQUIRY)
    answered = 0
    for subscriber in Subscriber.objects.filter(
        organization=game.organization, is_active=True
    ).order_by("subscriber_code"):
        code = subscriber.subscriber_code
        rng = stream(game.world.seed, f"batch:{code}:{today:%Y%m}")
        if rng.random() >= BATCH_CHANCE:
            continue
        size = int(rng.integers(*BATCH_SIZE))
        chosen = sorted({people[int(i)] for i in rng.integers(len(people), size=size)})
        rows = [
            (IdentifierType.GHANA_CARD, p.ghana_card, f"{p.first_name} {p.last_name}")
            for p in Person.objects.filter(pk__in=chosen).order_by("pk")
        ]
        batch = answer_batch(
            game.organization, subscriber, f"BATCH-{code}-{today:%Y%m}", rows, "NEW_CREDIT", at
        )
        terms = scoreproduct.contract(subscriber, item, today)
        UsageRecord.objects.bulk_create(
            UsageRecord(
                organization=game.organization,
                subscriber=subscriber,
                contract=terms,
                enquiry=r.enquiry,
                product=item,
                quantity=1,
                unit_price=terms.unit_price,
                usage_at=at,
            )
            for r in batch.rows.select_related("enquiry").order_by("row_number")
        )
        answered += batch.records
        add(
            "BATCH_ANSWERED", "INFO",
            f"{subscriber.subscriber_name}'s batch of {batch.records} answered",
            f"{batch.hits} found, {batch.records - batch.hits} not on file.",
            {"screen": "batches", "params": {}},
        )  # fmt: skip
    return answered
