"""Providers respond to the bureau (P2.6; Document 07, Section 6.5).

Regulation obliges lenders to report, so the question is not whether they send
data but how good it is and how willingly they cooperate. Each provider has a
relationship with each game's bureau, updated at the start of every month from
what the bureau did in the month before (ASSUMPTION A-054):

* **feedback**: a feedback report sent on one of its submissions earns 1 point
  of progress, scaled by goodwill (a provider that resents the bureau ignores
  it below goodwill 0.3); it also adds 0.02 goodwill;
* **training**: a session (GHS 5,000; at most one a month) earns 2 points and
  adds 0.1 goodwill;
* **an SLA penalty**: earns 1 point (the provider tightens up) but costs 0.25
  goodwill.

Every 2 points the provider's data improves one step (a fifth fewer row defects;
at most four steps). Goodwill drifts back towards 0.7 by 0.05 a month. Below
0.5, the provider takes longer to send its files: up to 20 days at goodwill 0.

The improved files are a variant of the provider's files for that month (``q1``
to ``q4``), shared by every game at the same level.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from apps.bureau.submissions.models import FeedbackReport
from apps.finance.events import provider_training
from apps.world.models import Lender, ProviderSubmission
from apps.world.provider_files import generate_submission
from apps.world.provider_files.profiles import MAX_QUALITY, improved, profile_for

from .models import Game, ProviderRelationship

FEEDBACK_POINTS, TRAINING_POINTS, PENALTY_POINTS = 1.0, 2.0, 1.0
POINTS_PER_STEP = 2.0
FEEDBACK_GOODWILL, TRAINING_GOODWILL, PENALTY_GOODWILL = 0.02, 0.1, -0.25
NEUTRAL_GOODWILL, DRIFT = 0.7, 0.05
IGNORES_FEEDBACK_BELOW = 0.3
SLOW_BELOW, MAX_DELAY_DAYS = 0.5, 20
TRAINING_COST = Decimal("5000.00")


class RelationshipError(Exception):
    pass


def relationship(game: Game, code: str) -> ProviderRelationship:
    found, _ = ProviderRelationship.objects.get_or_create(game=game, provider_code=code)
    return found


def delay_days(goodwill: float) -> int:
    """How many days later than usual a provider sends its files."""
    if goodwill >= SLOW_BELOW:
        return 0
    return round((SLOW_BELOW - goodwill) / SLOW_BELOW * MAX_DELAY_DAYS)


def train(game: Game, code: str, on: date, at: datetime) -> ProviderRelationship:
    rel = relationship(game, code)
    if rel.trainings:
        raise RelationshipError(f"{code} already has a training session this month")
    provider_training(game.organization, code, TRAINING_COST, on, at)
    rel.trainings += 1
    rel.save(update_fields=["trainings"])
    return rel


def penalise(game: Game, code: str) -> ProviderRelationship:
    rel = relationship(game, code)
    rel.penalties += 1
    rel.save(update_fields=["penalties"])
    return rel


def month_update(game: Game, code: str, period: date, at: datetime) -> ProviderRelationship:
    """At a month start: the provider's response to the month just ended."""
    rel = relationship(game, code)
    since = rel.updated_at
    feedback = FeedbackReport.objects.filter(
        organization=game.organization,
        submission__institution__institution_code=code,
        sent_at__lt=at,
    )
    if since is not None:
        feedback = feedback.filter(sent_at__gte=since)
    sent = feedback.exists()
    listens = rel.goodwill >= IGNORES_FEEDBACK_BELOW
    points = (FEEDBACK_POINTS * rel.goodwill if sent and listens else 0.0) + (
        TRAINING_POINTS * rel.trainings + PENALTY_POINTS * rel.penalties
    )
    goodwill = rel.goodwill + (FEEDBACK_GOODWILL if sent else 0.0)
    goodwill += TRAINING_GOODWILL * rel.trainings + PENALTY_GOODWILL * rel.penalties
    if not (rel.trainings or rel.penalties or sent):  # left alone, it settles back
        goodwill += max(-DRIFT, min(DRIFT, NEUTRAL_GOODWILL - goodwill))
    rel.progress += points
    while rel.progress >= POINTS_PER_STEP and rel.quality < MAX_QUALITY:
        rel.progress -= POINTS_PER_STEP
        rel.quality += 1
    if rel.quality >= MAX_QUALITY:
        rel.progress = min(rel.progress, POINTS_PER_STEP)
    why = [w for w, on in (("feedback", sent), ("training", rel.trainings),
                           ("penalty", rel.penalties)) if on]  # fmt: skip
    rel.goodwill = round(max(0.0, min(1.0, goodwill)), 4)
    rel.progress = round(rel.progress, 4)
    rel.history = [
        *rel.history,
        {
            "period": period.isoformat(),
            "quality": rel.quality,
            "goodwill": rel.goodwill,
            "why": why,
            "ignored_feedback": sent and not listens,
        },
    ]
    rel.trainings = rel.penalties = 0
    rel.updated_at = at
    rel.save()
    return rel


def submission_for(game: Game, lender: Lender, period: date, quality: int) -> ProviderSubmission:
    """The provider's files for ``period`` as this game's provider writes them."""
    variant = f"q{min(quality, MAX_QUALITY)}" if quality > 0 else ""
    found = ProviderSubmission.objects.filter(lender=lender, period=period, variant=variant).first()
    if found is not None:
        return found
    base = profile_for(
        lender.code, lender.lender_type, float(lender.profile.get("sophistication", 0.5))
    )
    return generate_submission(
        game.world, lender, period, improved(base, quality), variant=variant
    ).submission


def arrival(submission: ProviderSubmission, goodwill: float) -> date:
    return submission.arrival_date + timedelta(days=delay_days(goodwill))
