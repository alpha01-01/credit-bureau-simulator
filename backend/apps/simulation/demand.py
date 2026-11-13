"""Whether a lender checks the bureau for an application (Document 07, Sections 6.3-6.4).

ASSUMPTION A-027: functional form and constants are gameplay placeholders.

    P(enquire) = logistic(1.2 + 3 (perceived value - 0.5)
                          - 2.5 (price / reference price - 1) + 0.5 relationship)

Perceived value is each subscriber's rolling view of the bureau, built from
its own enquiries: a correct hit adds value, "no record found" adds little,
and a report about the wrong person costs most.
"""

from __future__ import annotations

import math
from decimal import Decimal

# Reference consumer report price (ASSUMPTION A-028, until pricing reference R8 arrives).
REFERENCE_PRICE = Decimal("15.00")

OUTCOME_VALUE = {"CORRECT_HIT": 1.0, "NO_HIT": 0.2, "WRONG_PERSON": -1.0}
LEARNING = 0.08
WRONG_PERSON_WEIGHT = 3.0


def p_enquire(perceived: float, price: Decimal, relationship: float = 0.0) -> float:
    z = (
        1.2
        + 3.0 * (perceived - 0.5)
        - 2.5 * (float(price / REFERENCE_PRICE) - 1.0)
        + 0.5 * relationship
    )
    return 1 / (1 + math.exp(-z))


def update_perception(perceived: float, outcome: str) -> float:
    """Exponentially weighted, with wrong-person reports weighing most."""
    weight = LEARNING * (WRONG_PERSON_WEIGHT if outcome == "WRONG_PERSON" else 1.0)
    value = OUTCOME_VALUE[outcome]
    return max(0.0, min(1.0, (1 - weight) * perceived + weight * value))
