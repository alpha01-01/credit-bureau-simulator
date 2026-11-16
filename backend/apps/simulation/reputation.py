"""Reputation with three audiences, each from its own measured inputs (P2.8; Section 6.6).

ASSUMPTION A-061, scores out of 100:

* **Subscribers** (the last three months): 40% hit rate, 40% report accuracy (hits
  that were the right person), 20% disputes settled on time.
* **Providers**: their average goodwill towards the bureau, which feedback,
  training and fair enforcement raise and penalties lower.
* **Regulator**: 100, less 15 for each finding in the last six months and 10 for
  each step up the escalation ladder.

What drives each score is shown with it; reputation is what the market thinks, so
the player sees it, unlike the hidden views it is built from.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from apps.bureau.quality.models import Dispute, DisputeStatus

from .models import (
    EnquiryJudgement,
    Game,
    ProviderRelationship,
    RegulatorFinding,
    RegulatorStanding,
)

RECENT_DAYS = 91
NEUTRAL_GOODWILL = 0.7


def _clamp(score: float) -> int:
    return round(max(0.0, min(100.0, score)))


def reputation(game: Game, at: datetime) -> dict[str, Any]:
    since = at - timedelta(days=RECENT_DAYS)
    judged = EnquiryJudgement.objects.filter(game=game, enquiry__enquired_at__gte=since)
    enquiries = judged.count()
    hits = judged.filter(hit=True).count()
    wrong = judged.filter(outcome="WRONG_PERSON").count()
    settled = Dispute.objects.filter(
        organization=game.organization, status=DisputeStatus.RESOLVED, resolved_at__gte=since
    )
    on_time = sum(d.resolved_at is not None and d.resolved_at.date() <= d.due_date for d in settled)
    overdue_open = Dispute.objects.filter(
        organization=game.organization, status=DisputeStatus.OPEN, due_date__lt=at.date()
    ).count()
    disputes = settled.count() + overdue_open
    hit_rate = hits / enquiries if enquiries else 0.0
    accuracy = 1 - wrong / hits if hits else 1.0
    timely = on_time / disputes if disputes else 1.0
    subscribers = 100 * (0.4 * hit_rate + 0.4 * accuracy + 0.2 * timely)

    goodwill = list(
        ProviderRelationship.objects.filter(game=game).values_list("goodwill", flat=True)
    )
    providers = 100 * (sum(goodwill) / len(goodwill) if goodwill else NEUTRAL_GOODWILL)

    findings = RegulatorFinding.objects.filter(
        game=game, raised_at__gte=at - timedelta(days=183)
    ).count()
    level = RegulatorStanding.objects.filter(game=game).values_list("level", flat=True).first() or 0
    regulator = 100 - 15 * findings - 10 * level

    return {
        "as_of": at.date().isoformat(),
        "subscribers": {
            "score": _clamp(subscribers),
            "hit_rate": round(hit_rate, 4),
            "accuracy": round(accuracy, 4),
            "disputes_on_time": round(timely, 4),
            "enquiries": enquiries,
        },
        "providers": {"score": _clamp(providers), "providers": len(goodwill)},
        "regulator": {"score": _clamp(regulator), "findings": findings, "level": level},
    }
