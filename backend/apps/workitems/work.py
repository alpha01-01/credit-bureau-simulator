"""Employees working through the queue, tick by tick, and the player deciding items.

Called by the simulation each tick. Items are taken oldest first. An employee
works 15 minutes per tick, may finish several quick items in one tick, and
carries a long item over to the next tick.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import numpy as np
from django.db import transaction

from apps.bureau.core.models import IndividualProfile
from apps.bureau.quality.models import ALLOWED_DECISIONS, CaseType, ReviewCase
from apps.bureau.submissions.review import apply_decision
from apps.org.models import Employee, Organization

from .models import ItemStatus, ResolvedBy, WorkItem
from .resolution import DECISION_WORDS, Judgement, fatigue, judge, learn, minutes_needed

RngFor = Callable[[int], np.random.Generator]


class WorkError(Exception):
    pass


def has_work(organization: Organization) -> bool:
    return (
        WorkItem.objects.filter(
            organization=organization, status__in=[ItemStatus.OPEN, ItemStatus.IN_PROGRESS]
        ).exists()
        and Employee.objects.filter(organization=organization, is_active=True).exists()
    )


def work_tick(
    organization: Organization,
    tick: int,
    day_index: int,
    at: datetime,
    rng_for: RngFor,
    minutes: float = 15.0,
) -> int:
    """Let every active employee work for one tick. Returns the number of items finished."""
    finished = 0
    for employee in Employee.objects.filter(organization=organization, is_active=True).order_by(
        "employee_number"
    ):
        if employee.work_day != day_index:
            employee.work_day, employee.done_today = day_index, 0
        budget = minutes
        while budget > 1e-9:
            item = _current_or_next(organization, employee, tick)
            if item is None:
                break
            used = min(budget, item.minutes_remaining or 0.0)
            budget -= used
            item.minutes_remaining = (item.minutes_remaining or 0.0) - used
            if item.minutes_remaining > 1e-9:
                item.save(update_fields=["minutes_remaining"])
                break
            _finish(item, employee, tick, at, rng_for(item.item_number))
            finished += 1
        employee.save(update_fields=["work_day", "done_today", "skills", "experience"])
    return finished


def _current_or_next(organization: Organization, employee: Employee, tick: int) -> WorkItem | None:
    item = WorkItem.objects.filter(assignee=employee, status=ItemStatus.IN_PROGRESS).first()
    if item is not None:
        return item
    item = (
        WorkItem.objects.select_for_update(skip_locked=True)
        .filter(organization=organization, status=ItemStatus.OPEN)
        .order_by("item_number")
        .first()
    )
    if item is None:
        return None
    skill = float(employee.skills.get(item.item_type, 0.5))
    item.status = ItemStatus.IN_PROGRESS
    item.assignee = employee
    item.started_tick = tick
    item.minutes_remaining = minutes_needed(
        item.item_type, item.difficulty, skill, employee.morale, fatigue(employee.done_today)
    )
    item.save(update_fields=["status", "assignee", "started_tick", "minutes_remaining"])
    return item


def _finish(
    item: WorkItem, employee: Employee, tick: int, at: datetime, rng: np.random.Generator
) -> None:
    skill = float(employee.skills.get(item.item_type, 0.5))
    result = judge(
        item.item_type,
        item.correct_decision,
        item.difficulty,
        skill,
        employee.morale,
        fatigue(employee.done_today),
        rng,
    )
    case = apply_decision(
        item.case, result.decision, f"{employee.first_name} {employee.last_name}", at
    )
    item.status = ItemStatus.DONE
    item.resolved_tick = tick
    item.resolved_by = ResolvedBy.EMPLOYEE
    item.decision = result.decision
    item.is_correct = result.decision == item.correct_decision
    item.confidence = result.confidence
    item.minutes_remaining = 0.0
    item.explanation = explain(case, result)
    item.save()

    employee.done_today += 1
    employee.experience[item.item_type] = int(employee.experience.get(item.item_type, 0)) + 1
    employee.skills[item.item_type] = round(learn(skill), 4)


def resolve_by_player(item: WorkItem, decision: str, tick: int, at: datetime) -> WorkItem:
    """The player decides an item. Their judgement is their own: no dice are rolled."""
    with transaction.atomic():
        item = WorkItem.objects.select_for_update().select_related("case").get(pk=item.pk)
        if item.status == ItemStatus.DONE:
            raise WorkError(f"Item {item.item_number} is already done")
        if decision not in ALLOWED_DECISIONS[item.item_type]:
            raise WorkError(f"{decision} is not a decision for this item")
        apply_decision(item.case, decision, "Player", at)
        item.status = ItemStatus.DONE
        item.assignee = None
        item.resolved_tick = tick
        item.resolved_by = ResolvedBy.PLAYER
        item.decision = decision
        item.is_correct = decision == item.correct_decision
        item.minutes_remaining = 0.0
        item.explanation = f"Decided by the player: {DECISION_WORDS[decision]}."
        item.save()
        return item


def explain(case: ReviewCase, result: Judgement) -> str:
    """The reasoning an employee records with a decision (Document 05: explainability)."""
    record = case.record.cleansed
    verdict = f"Decided: {DECISION_WORDS[result.decision]} (confidence {result.confidence:.2f})."
    if case.case_type == CaseType.MATCH_REVIEW:
        identifier = case.evidence.get("identifier", "")
        held_by = case.candidate_customer.customer_reference if case.candidate_customer else "?"
        profile = (
            IndividualProfile.objects.filter(customer_id=case.candidate_customer_id).first()
            if case.candidate_customer_id is not None
            else None
        )
        if profile is not None:
            born = f"{profile.date_of_birth:%d/%m/%Y}" if profile.date_of_birth else "unknown"
            known = f"{profile.first_name} {profile.last_name}, born {born}"
            submitted = f"{record.get('FIRST_NAME', '')} {record.get('SURNAME', '')}, born {record.get('DATE_OF_BIRTH', '')}"
        else:
            known = "a business"
            submitted = record.get("REGISTERED_NAME", "")
        reasons = "; ".join(case.evidence.get("reasons", []))
        return (
            f"Identifier {identifier} is held by {held_by} ({known}). The record is for "
            f"{submitted}. Comparison: {reasons} (score {case.score:.2f}). {verdict}"
        )
    errors = ", ".join(
        f"{e['rule']} {e['field']} '{e['value']}'" for e in case.evidence.get("errors", [])
    )
    fixes = ", ".join(f"{k} -> {v}" for k, v in case.proposal.items())
    return f"Errors: {errors}. Proposed: {fixes}. {verdict}"
