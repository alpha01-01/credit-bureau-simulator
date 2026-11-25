"""HR: hiring, training, salaries, morale and resignations (P2.9; Document 07, Section 6.7).

ASSUMPTION A-062 (until reference R13 gives real roles and salary bands):

* Each month three people look for work at the bureau, drawn from the world's
  seed: one each for junior, officer and senior Data Officer, with skills and
  asking salaries in the bands below. They are gone at the month's end if not hired.
* A training course (GHS 2,500) takes the employee away for one working day
  and adds 0.06 to their skill in one kind of work item (at most 0.95).
* Morale moves each month a third of the way towards a target: 0.7, up with pay
  above the market for the role (0.5 per 100% above), down with a heavy queue
  (more than 40 open items per active employee) and up a little after training.
  Below 0.4, an employee resigns with chance 0.25 that month.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from apps.bureau.quality.models import CaseType
from apps.finance.events import staff_training
from apps.org.models import Employee
from apps.workitems.models import ItemStatus, WorkItem
from apps.world.generation.identity import COMMON_FIRST_NAMES, FIRST_NAMES, SURNAMES
from apps.world.generation.rng import stream

from . import economy
from .clock import TICKS_PER_DAY
from .models import Candidate, Game

# Role: (skill range, asking salary range in GHS a month).
ROLES: dict[str, tuple[tuple[float, float], tuple[int, int]]] = {
    "Junior Data Officer": ((0.50, 0.62), (4500, 5200)),
    "Data Officer": ((0.68, 0.78), (6500, 7200)),
    "Senior Data Officer": ((0.84, 0.92), (9000, 10500)),
}
TRAINING_COST = Decimal("2500.00")
TRAINING_GAIN, SKILL_CAP = 0.06, 0.95
NEUTRAL_MORALE, MORALE_SPEED = 0.7, 1 / 3
HEAVY_QUEUE_PER_PERSON = 40
RESIGN_BELOW, RESIGN_CHANCE = 0.4, 0.25
MONTH_TICKS = 22 * TICKS_PER_DAY
WORK_TYPES = (CaseType.MATCH_REVIEW, CaseType.UNLOADABLE_TRIAGE, CaseType.DISPUTE)


class HRError(Exception):
    pass


def market_salary(job_title: str, wages: Decimal = Decimal("1")) -> Decimal:
    """The going rate for the role; ``wages`` is the wage index since play began (P3.12)."""
    low, high = ROLES.get(job_title, ROLES["Data Officer"])[1]
    return (Decimal((low + high) // 2) * wages).quantize(Decimal("1"))


def candidates_for(game: Game, period: date) -> list[Candidate]:
    """The month's candidates, made once and the same in every replay."""
    existing = list(Candidate.objects.filter(game=game, period=period).order_by("number"))
    if existing:
        return existing
    rng = stream(game.world.seed, f"candidates:{period:%Y%m}")
    wages = economy.wage_factor(game, period)  # candidates ask the going rate (P3.12)
    groups = list(SURNAMES)
    made = []
    for n, title in enumerate(ROLES, start=1):
        (s_low, s_high), (p_low, p_high) = ROLES[title]
        group = groups[int(rng.integers(len(groups)))]
        gender = "F" if rng.random() < 0.5 else "M"
        names = FIRST_NAMES[group][gender] + COMMON_FIRST_NAMES[gender]
        made.append(
            Candidate(
                game=game,
                period=period,
                number=n,
                first_name=names[int(rng.integers(len(names)))],
                last_name=SURNAMES[group][int(rng.integers(len(SURNAMES[group])))],
                job_title=title,
                skills={str(t): round(float(rng.uniform(s_low, s_high)), 3) for t in WORK_TYPES},
                asking_salary=(
                    Decimal(int(rng.integers(p_low, p_high + 1) // 100 * 100)) * wages
                ).quantize(Decimal("100")),
            )
        )
    return Candidate.objects.bulk_create(made)


def hire(game: Game, candidate: Candidate, on: date) -> Employee:
    if candidate.hired:
        raise HRError(f"{candidate} has already been hired")
    candidate.hired = True
    candidate.save(update_fields=["hired"])
    number = game.organization.allocate("last_employee_seq")
    return Employee.objects.create(
        organization=game.organization,
        employee_number=f"E{number:04d}",
        first_name=candidate.first_name,
        last_name=candidate.last_name,
        job_title=candidate.job_title,
        skills=dict(candidate.skills),
        morale=NEUTRAL_MORALE,
        monthly_salary=candidate.asking_salary,
        hired_on=on,
    )


def train(employee: Employee, work_type: str, tick: int, on: date, at: datetime) -> Employee:
    """Send an employee on a course: away for the next working day's worth of ticks."""
    if work_type not in WORK_TYPES:
        raise HRError(f"No training for {work_type}")
    if not employee.is_active:
        raise HRError(f"{employee.first_name} {employee.last_name} has left")
    if employee.away_until_tick > tick:
        raise HRError(f"{employee.first_name} is already away on training")
    staff_training(employee.organization, f"{employee.first_name} {employee.last_name}",
                   TRAINING_COST, on, at)  # fmt: skip
    skill = float(employee.skills.get(work_type, 0.5))
    employee.skills[work_type] = round(min(SKILL_CAP, skill + TRAINING_GAIN), 4)
    employee.away_until_tick = tick + TICKS_PER_DAY
    employee.save(update_fields=["skills", "away_until_tick"])
    return employee


def set_salary(employee: Employee, salary: Decimal) -> Employee:
    if salary <= 0:
        raise HRError("A salary must be more than zero")
    employee.monthly_salary = salary.quantize(Decimal("0.01"))
    employee.save(update_fields=["monthly_salary"])
    return employee


def month_update(game: Game, today: date, add: Any) -> None:
    """At a month start: morale moves, and unhappy people may leave."""
    staff = list(
        Employee.objects.filter(organization=game.organization, is_active=True).order_by(
            "employee_number"
        )
    )
    if not staff:
        return
    queue = WorkItem.objects.filter(
        organization=game.organization, status__in=[ItemStatus.OPEN, ItemStatus.IN_PROGRESS]
    ).count()
    heavy = queue / len(staff) > HEAVY_QUEUE_PER_PERSON
    rng = stream(game.world.seed, f"morale:{today:%Y%m}")
    recent = game.current_tick - MONTH_TICKS
    wages = economy.wage_factor(game, today)
    for person in staff:
        pay = float(person.monthly_salary / market_salary(person.job_title, wages)) - 1
        trained = person.away_until_tick > max(recent, 0)
        target = NEUTRAL_MORALE + 0.5 * pay - (0.25 if heavy else 0.0) + (0.05 if trained else 0.0)
        moved = person.morale + MORALE_SPEED * (target - person.morale)
        person.morale = round(max(0.0, min(1.0, moved)), 4)
        if person.morale < RESIGN_BELOW and rng.random() < RESIGN_CHANCE:
            person.is_active = False
            add(
                "RESIGNATION", "WARNING",
                f"{person.first_name} {person.last_name} has resigned",
                f"{person.job_title}; morale {person.morale:.2f}. Their work in progress goes back "
                "to the queue.",
                {"screen": "staff", "params": {}},
            )  # fmt: skip
            WorkItem.objects.filter(assignee=person, status=ItemStatus.IN_PROGRESS).update(
                status=ItemStatus.OPEN, assignee=None, minutes_remaining=None
            )
        person.save(update_fields=["morale", "is_active"])
