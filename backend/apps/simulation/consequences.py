# ruff: noqa: S608  (SQL is built from model table names only, never from input)
"""Consequence chains (P2.3; Document 07, Section 8.5).

When a report goes to a subscriber, the simulation compares it with the truth:

* a **mixed report** held accounts of someone other than the applicant: the
  provider customer behind them was linked to this bureau customer by mistake
  (a false merge);
* an **incomplete report** missed accounts of the applicant that the bureau
  holds under another customer (a false split).

Each wrong link is traced to what made it: a reviewer's decision on a work item
(matched as the same customer, or as a different one), or the automatic
matching rules. The links are recorded so the debrief can replay the chain.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from django.db import connection, models

from apps.bureau.core.models import CreditAccount, Enquiry
from apps.bureau.providers.models import Institution
from apps.bureau.quality.models import Decision
from apps.workitems.models import ItemStatus, ResolvedBy, WorkItem
from apps.world.models import Lender as WorldLender
from apps.world.models import LenderCustomer, Loan

from .models import Consequence, Game

MIXED, INCOMPLETE = "MIXED_REPORT", "INCOMPLETE_REPORT"
RESOLVERS: dict[str, str] = {
    ResolvedBy.PLAYER.value: "you",
    ResolvedBy.EMPLOYEE.value: "an employee",
    ResolvedBy.HISTORIC.value: "staff before the game began",
}


def _t(model: type[models.Model]) -> str:
    return model._meta.db_table


# The accounts on a bureau customer, with the provider customer behind each and whose it is.
_ON_CUSTOMER = f"""
SELECT 'on', i.institution_code, lc.customer_number, lc.person_id, lc.business_id
FROM {_t(CreditAccount)} ca
JOIN {_t(Institution)} i ON i.id = ca.institution_id
JOIN {_t(WorldLender)} wl ON wl.world_id = %(world)s AND wl.code = i.institution_code
JOIN {_t(Loan)} l ON l.lender_id = wl.id AND l.account_number = ca.facility_account_number
JOIN {_t(LenderCustomer)} lc ON lc.id = l.customer_id
WHERE ca.customer_id = %(customer)s
"""

# The applicant's accounts the bureau holds under other customers.
_ELSEWHERE = f"""
SELECT 'elsewhere', i.institution_code, lc.customer_number, NULL::bigint, NULL::bigint
FROM {_t(LenderCustomer)} lc
JOIN {_t(WorldLender)} wl ON wl.id = lc.lender_id
JOIN {_t(Loan)} l ON l.customer_id = lc.id
JOIN {_t(Institution)} i ON i.organization_id = %(org)s AND i.institution_code = wl.code
JOIN {_t(CreditAccount)} ca ON ca.institution_id = i.id
     AND ca.facility_account_number = l.account_number
WHERE wl.world_id = %(world)s AND lc.{{column}} = %(borrower)s AND ca.customer_id <> %(customer)s
"""


def trace(
    game: Game,
    enquiry: Enquiry,
    applicant: tuple[str, int],
    subscriber_code: str,
    tick: int,
    at: datetime,
) -> list[Consequence]:
    """Record what was wrong with the report delivered for ``enquiry``, and why."""
    if enquiry.customer_id is None:
        return []
    params = {
        "world": game.world_id,
        "org": game.organization_id,
        "customer": enquiry.customer_id,
        "borrower": applicant[1],
    }
    foreign: dict[tuple[str, str], int] = defaultdict(int)  # wrong link -> accounts shown
    missing: dict[tuple[str, str], int] = defaultdict(int)
    column = "person_id" if applicant[0] == "person" else "business_id"
    with connection.cursor() as cursor:  # both in one query (P4.0)
        cursor.execute(f"{_ON_CUSTOMER} UNION ALL {_ELSEWHERE.replace('{column}', column)}", params)
        for where, provider, number, person, business in cursor.fetchall():
            if where == "elsewhere":
                missing[(provider, number)] += 1
                continue
            who = ("person", person) if person is not None else ("business", business)
            if who != applicant:
                foreign[(provider, number)] += 1

    found = []
    for effect, links, decision in (
        (MIXED, foreign, Decision.SAME_CUSTOMER),
        (INCOMPLETE, missing, Decision.DIFFERENT_CUSTOMER),
    ):
        for (provider, number), accounts in sorted(links.items()):
            item = _decided(game, provider, number, decision)
            found.append(
                Consequence(
                    game=game,
                    tick=tick,
                    sim_time=at,
                    effect=effect,
                    enquiry=enquiry,
                    subscriber_code=subscriber_code,
                    accounts=accounts,
                    cause="DECISION" if item else "AUTOMATIC",
                    work_item=item,
                    provider=provider,
                    provider_customer=number,
                    detail=_detail(effect, accounts, provider, number, item),
                )
            )
    Consequence.objects.bulk_create(found)
    return found


def _decided(game: Game, provider: str, number: str, decision: str) -> WorkItem | None:
    """The work item whose decision made this provider customer's link, if one did."""
    return (
        WorkItem.objects.filter(
            organization=game.organization,
            status=ItemStatus.DONE,
            decision=decision,
            case__record__run__submission__institution__institution_code=provider,
            case__record__raw__CustomerID=number,
        )
        .order_by("resolved_tick", "item_number")
        .first()
    )


def _detail(effect: str, accounts: int, provider: str, number: str, item: WorkItem | None) -> str:
    what = (
        f"{accounts} account(s) of another person were shown"
        if effect == MIXED
        else f"{accounts} of the applicant's account(s) were left out"
    )
    if item is None:
        how = (
            "the matching rules linked the records automatically"
            if effect == MIXED
            else "no identifier matched, so the records became a separate customer"
        )
    else:
        who = RESOLVERS.get(str(item.resolved_by), "a reviewer")
        how = (
            f"work item {item.item_number} was decided "
            f"{'the same customer' if effect == MIXED else 'a different customer'} by {who}"
        )
    return f"{what}: {provider} customer {number}; {how}."
