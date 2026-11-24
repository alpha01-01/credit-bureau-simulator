"""The credit score as a product, and the mobile loan report (P3.6; Document 09).

**The score.** A subscriber may buy the score with a report (a separate line, GHS 5;
R8 placeholder, A-076). How many of its enquiries come with the score depends on how
well the score has been predicting: lenders back-test it on the loans they make. Each
month a subscriber's uptake moves halfway towards what the score's quality warrants
(its AUC against the world's true defaults, as its debrief measures it): nothing below
0.65, everything from 0.80. A poor score is soon dropped.

**The mobile loan report.** Mobile lenders check the bureau for their mobile loans in
bulk, too many and too small for a full enquiry each (P3.3). Each working night the
bureau bills a subscriber for the mobile loans it made since the last batch that it
checked, at GHS 2 each (R8 placeholder), with the same willingness to check as for
reports, at the mobile report's price.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db.models import Count

from apps.commercial.models import Contract, Product, Subscriber, UsageRecord
from apps.commercial.usage import NoContract, active_contract
from apps.world.generation.mobile import PRODUCT as MOBILE_LOAN
from apps.world.generation.rng import stream
from apps.world.models import Loan

from .demand import p_enquire
from .models import Game, ScoreModel, SubscriberView

SCORE, MOBILE_REPORT = "CREDIT_SCORE", "MOBILE_REPORT"
PRODUCTS = {
    SCORE: ("Credit score, with a report", Decimal("5.00")),
    MOBILE_REPORT: ("Mobile loan report", Decimal("2.00")),
}
UPTAKE_FLOOR, UPTAKE_FULL = 0.65, 0.80  # the score's AUC against the truth
UPTAKE_SPEED = 0.5  # share of the way to the warranted uptake each month


def product(game: Game, code: str) -> Product:
    """The bureau's product, created on first use (games made before P3.6 lack it)."""
    name, price = PRODUCTS[code]
    found, _ = Product.objects.get_or_create(
        organization=game.organization,
        product_code=code,
        defaults={"product_name": name, "list_price": price},
    )
    return found


def contract(subscriber: Subscriber, item: Product, on: date) -> Contract:
    """The subscriber's contract for a product: at list price from the first use."""
    try:
        return active_contract(subscriber.pk, item, on)
    except NoContract:
        return Contract.objects.create(
            subscriber=subscriber, product=item, unit_price=item.list_price, start_date=on
        )


def scoring_model(game: Game) -> ScoreModel | None:
    """The scorecard behind most reports' scores: the composite, else the longest term."""
    deployed = {
        m.term: m for m in ScoreModel.objects.filter(game=game, status=ScoreModel.Status.DEPLOYED)
    }
    for term in ("COMPOSITE", "LONG", "MID", "SHORT"):
        if term in deployed:
            return deployed[term]
    return None


def warranted_uptake(game: Game) -> float:
    model = scoring_model(game)
    if model is None:
        return 0.0
    auc = (model.results.get("truth") or {}).get("auc_against_truth")
    if auc is None:
        return 0.0
    return max(0.0, min(1.0, (float(auc) - UPTAKE_FLOOR) / (UPTAKE_FULL - UPTAKE_FLOOR)))


def update_uptake(game: Game) -> None:
    """At the month's end: each subscriber moves towards the uptake the score warrants."""
    target = warranted_uptake(game)
    for view in SubscriberView.objects.filter(game=game).order_by("subscriber_code"):
        view.score_uptake = round(
            view.score_uptake + UPTAKE_SPEED * (target - view.score_uptake), 6
        )
        view.save(update_fields=["score_uptake"])


def buys_score(game: Game, view: SubscriberView, code: str, period: date, seq: int) -> bool:
    if view.score_uptake <= 0:
        return False
    return bool(
        stream(game.world.seed, f"score:{code}:{period:%Y%m}:{seq}").random() < view.score_uptake
    )


def bill_mobile_checks(game: Game, day: date, since: date, at: datetime) -> int:
    """Bill each subscriber's mobile-loan checks for loans made after ``since`` up to ``day``."""
    subscribers = {
        s.subscriber_code: s
        for s in Subscriber.objects.filter(organization=game.organization, is_active=True)
    }
    if not subscribers:
        return 0
    counts = dict(
        Loan.objects.filter(
            world=game.world, product=MOBILE_LOAN, lender__code__in=list(subscribers),
            disbursement_date__gt=since, disbursement_date__lte=day,
        )
        .values_list("lender__code")
        .annotate(n=Count("pk"))
        .values_list("lender__code", "n")
    )  # fmt: skip
    if not counts:
        return 0
    item = product(game, MOBILE_REPORT)
    views = {v.subscriber_code: v for v in SubscriberView.objects.filter(game=game)}
    billed = 0
    for code in sorted(counts):
        view = views.get(code)
        if view is None:
            continue
        terms = contract(subscribers[code], item, day)
        p = p_enquire(view.perceived_value, terms.unit_price)
        checked = int(
            stream(game.world.seed, f"mobile-checks:{code}:{day:%Y%m%d}").binomial(counts[code], p)
        )
        if checked:
            UsageRecord.objects.create(
                organization=game.organization, subscriber=subscribers[code], contract=terms,
                enquiry=None, product=item, quantity=checked, unit_price=terms.unit_price,
                usage_at=at,
            )  # fmt: skip
            billed += checked
    return billed


def previous_day(day: date) -> date:
    return day - timedelta(days=1)
