"""How alike a submitted record and a bureau customer are.

ASSUMPTION A-021: the scoring and the auto-link threshold are placeholders
until real matching practice (reference R4) is available. When an identifier
matches but the score is below AUTO_LINK, the match is held for review
rather than linked blindly.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import date

AUTO_LINK = 0.92


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(text.upper().replace("-", " ").replace(".", " ").split())


def jaro_winkler(a: str, b: str) -> float:
    """Jaro-Winkler similarity in [0, 1]."""
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    window = max(max(len(a), len(b)) // 2 - 1, 0)
    a_hits = [False] * len(a)
    b_hits = [False] * len(b)
    matches = 0
    for i, ch in enumerate(a):
        for j in range(max(0, i - window), min(i + window + 1, len(b))):
            if not b_hits[j] and b[j] == ch:
                a_hits[i] = b_hits[j] = True
                matches += 1
                break
    if not matches:
        return 0.0
    a_chars = [ch for ch, hit in zip(a, a_hits, strict=True) if hit]
    b_chars = [ch for ch, hit in zip(b, b_hits, strict=True) if hit]
    transpositions = sum(x != y for x, y in zip(a_chars, b_chars, strict=True)) / 2
    jaro = (matches / len(a) + matches / len(b) + (matches - transpositions) / matches) / 3
    prefix = 0
    for x, y in zip(a[:4], b[:4], strict=False):
        if x != y:
            break
        prefix += 1
    return jaro + prefix * 0.1 * (1 - jaro)


def name_similarity(first_a: str, last_a: str, first_b: str, last_b: str) -> float:
    """Full-name similarity, tolerant of first and last names given the wrong way round."""
    a = _normalise(f"{first_a} {last_a}")
    b = _normalise(f"{first_b} {last_b}")
    swapped = _normalise(f"{last_b} {first_b}")
    return max(jaro_winkler(a, b), jaro_winkler(a, swapped))


def date_similarity(a: date | None, b: date | None) -> float:
    if a is None or b is None:
        return 0.5  # unknown: neither for nor against
    if a == b:
        return 1.0
    if a.year == b.year and a.month == b.day and a.day == b.month:
        return 0.7  # day and month swapped: a classic data entry error
    if a.year == b.year:
        return 0.3
    return 0.0


@dataclass(frozen=True)
class Comparison:
    score: float
    reasons: list[str] = field(default_factory=list)

    @property
    def auto_link(self) -> bool:
        return self.score >= AUTO_LINK


def compare_individuals(
    record: tuple[str, str, date | None], customer: tuple[str, str, date | None]
) -> Comparison:
    """(first name, surname, date of birth) of the record and of the bureau customer."""
    names = name_similarity(record[0], record[1], customer[0], customer[1])
    birth = date_similarity(record[2], customer[2])
    reasons = [f"name similarity {names:.2f}"]
    reasons.append(
        {1.0: "same date of birth", 0.7: "date of birth has day and month swapped",
         0.3: "same year of birth, different date", 0.5: "date of birth missing"}.get(
            birth, "different date of birth"
        )
    )  # fmt: skip
    return Comparison(round(0.6 * names + 0.4 * birth, 3), reasons)


def compare_businesses(
    record: tuple[str, date | None], customer: tuple[str, date | None]
) -> Comparison:
    """(registered name, registration date) of the record and of the bureau customer."""
    a, b = _normalise(record[0]), _normalise(customer[0])
    names = jaro_winkler(a, b)
    registered = date_similarity(record[1], customer[1])
    reasons = [
        f"name similarity {names:.2f}",
        "same registration date" if registered == 1.0 else "registration date differs",
    ]
    return Comparison(round(0.7 * names + 0.3 * registered, 3), reasons)
