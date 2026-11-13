"""Ghana working-day calendar.

ASSUMPTION A-019: the public holiday list and observance rules below are
placeholders until confirmed from the official list (reference R17). They
follow the Public Holidays and Commemorative Days Act as amended, to the best
of current knowledge:

  Fixed dates: New Year's Day (1 Jan), Constitution Day (7 Jan), Independence
  Day (6 Mar), May Day (1 May), National Day of Prayer and Thanksgiving
  (1 Jul), Founders' Day (4 Aug), Kwame Nkrumah Memorial Day (21 Sep),
  Christmas Day (25 Dec), Boxing Day (26 Dec).
  Moveable: Good Friday, Easter Monday, Eid al-Fitr, Eid al-Adha, Farmers'
  Day (first Friday in December).
  A fixed-date holiday falling on a weekend is observed on the next working day.

Eid dates depend on the sighting of the moon and are announced each year;
the table holds expected dates.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import cache

FIXED_HOLIDAYS: tuple[tuple[int, int, str], ...] = (
    (1, 1, "New Year's Day"),
    (1, 7, "Constitution Day"),
    (3, 6, "Independence Day"),
    (5, 1, "May Day"),
    (7, 1, "National Day of Prayer and Thanksgiving"),
    (8, 4, "Founders' Day"),
    (9, 21, "Kwame Nkrumah Memorial Day"),
    (12, 25, "Christmas Day"),
    (12, 26, "Boxing Day"),
)

# Expected dates (ASSUMPTION A-019).
EID_AL_FITR = {
    2023: date(2023, 4, 21), 2024: date(2024, 4, 10), 2025: date(2025, 3, 31),
    2026: date(2026, 3, 20), 2027: date(2027, 3, 10), 2028: date(2028, 2, 27),
    2029: date(2029, 2, 14), 2030: date(2030, 2, 4),
}  # fmt: skip
EID_AL_ADHA = {
    2023: date(2023, 6, 28), 2024: date(2024, 6, 16), 2025: date(2025, 6, 6),
    2026: date(2026, 5, 27), 2027: date(2027, 5, 16), 2028: date(2028, 5, 5),
    2029: date(2029, 4, 24), 2030: date(2030, 4, 13),
}  # fmt: skip


def easter_sunday(year: int) -> date:
    """Gregorian Easter (anonymous Gregorian algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    j = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * j) // 451
    month, day = divmod(h + j - 7 * m + 114, 31)
    return date(year, month, day + 1)


@cache
def public_holidays(year: int) -> dict[date, str]:
    """Days on which the public holiday is observed in a year."""
    observed: dict[date, str] = {}

    def add(day: date, name: str, move_off_weekend: bool) -> None:
        if move_off_weekend:
            while day.weekday() >= 5 or day in observed:
                day += timedelta(days=1)
        observed.setdefault(day, name)

    easter = easter_sunday(year)
    add(easter - timedelta(days=2), "Good Friday", False)
    add(easter + timedelta(days=1), "Easter Monday", False)
    first_december = date(year, 12, 1)
    add(first_december + timedelta(days=(4 - first_december.weekday()) % 7), "Farmers' Day", False)
    for month, day, name in FIXED_HOLIDAYS:
        add(date(year, month, day), name, True)
    for table, name in ((EID_AL_FITR, "Eid al-Fitr"), (EID_AL_ADHA, "Eid al-Adha")):
        if year in table:
            add(table[year], name, True)
    return dict(sorted(observed.items()))


def is_working_day(day: date) -> bool:
    return day.weekday() < 5 and day not in public_holidays(day.year)


def next_working_day(day: date) -> date:
    """The given day if it is a working day, otherwise the next one."""
    while not is_working_day(day):
        day += timedelta(days=1)
    return day
