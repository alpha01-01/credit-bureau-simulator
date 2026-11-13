"""How employees resolve work items (Document 07, Section 8.3).

ASSUMPTION A-023: the functional forms and constants below are gameplay
placeholders, to be balanced in playtesting.

    P(correct)      = logistic(4 (skill - 0.5) + 2.2 - 3 difficulty
                               - 1.5 fatigue + (morale - 0.7))
    minutes needed  = base(type) (0.6 + difficulty) (1.4 - 0.6 skill)
                      / (0.8 + 0.4 morale) (1 + 0.5 fatigue)

Fatigue is the share of a day's comfortable load already done today. Skill
grows a little with every item of that type (experience).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from apps.bureau.quality.models import ALLOWED_DECISIONS, CaseType, Decision

BASE_MINUTES: dict[str, float] = {CaseType.MATCH_REVIEW: 12.0, CaseType.UNLOADABLE_TRIAGE: 6.0}
COMFORTABLE_ITEMS_PER_DAY = 40
LEARNING_RATE = 0.003

DECISION_WORDS: dict[str, str] = {
    Decision.SAME_CUSTOMER: "same customer",
    Decision.DIFFERENT_CUSTOMER: "different customer",
    Decision.CORRECT_AND_LOAD: "correct and load",
    Decision.RETURN_TO_PROVIDER: "return to provider",
}


def p_correct(skill: float, difficulty: float, morale: float = 0.7, fatigue: float = 0.0) -> float:
    z = 4 * (skill - 0.5) + 2.2 - 3 * difficulty - 1.5 * fatigue + (morale - 0.7)
    return 1 / (1 + math.exp(-z))


def minutes_needed(
    item_type: str, difficulty: float, skill: float, morale: float = 0.7, fatigue: float = 0.0
) -> float:
    return (
        BASE_MINUTES[item_type]
        * (0.6 + difficulty)
        * (1.4 - 0.6 * skill)
        / (0.8 + 0.4 * morale)
        * (1 + 0.5 * fatigue)
    )


def fatigue(done_today: int) -> float:
    return min(1.0, done_today / COMFORTABLE_ITEMS_PER_DAY)


def learn(skill: float) -> float:
    return min(0.99, skill + LEARNING_RATE * (1 - skill))


@dataclass(frozen=True)
class Judgement:
    decision: str
    correct: bool
    confidence: float
    probability: float


def judge(
    item_type: str,
    correct_decision: str,
    difficulty: float,
    skill: float,
    morale: float,
    tiredness: float,
    rng: np.random.Generator,
) -> Judgement:
    """An employee's decision on one item, drawn from the seeded stream."""
    p = p_correct(skill, difficulty, morale, tiredness)
    correct = bool(rng.random() < p)
    if correct:
        decision = correct_decision
    else:
        wrong = [d for d in ALLOWED_DECISIONS[item_type] if d != correct_decision]
        # The likely mistake is the opposite call; returning to the provider is the cautious one.
        weights = np.array([0.25 if d == Decision.RETURN_TO_PROVIDER else 1.0 for d in wrong])
        decision = wrong[int(rng.choice(len(wrong), p=weights / weights.sum()))]
    # Employees are a little over- or under-confident; confidence is what they report.
    confidence = float(np.clip(p + rng.normal(0, 0.08), 0.5, 0.99))
    return Judgement(str(decision), correct, round(confidence, 2), p)
