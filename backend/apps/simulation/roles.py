"""Roles and workspaces (P3.1; Document 09; PRD criterion 13).

The player works as the chief executive or as the head of one department. Each
role has its own screens and its own actions; the API refuses an action that
belongs to another role (``require``). The simulation itself does not change
with the role: the departments' staff carry on whatever the player is doing,
replays act as the whole company, and so do the headless strategy runs.

The chief executive sees every screen and keeps the company's decisions: money
(funding, investment in tooling and IT capacity) and the departments that are
managed rather than played (Document 07, Section 9: HR, IT, Customer Support and
Product Development). Department heads
see their own screens and the shared ones.

Taking over a department is not instant: a role switch takes ``CHANGEOVER_TICKS``
of game time (A-072), during which the new role's actions wait.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from rest_framework.exceptions import PermissionDenied

from apps.bureau.quality.models import CaseType
from apps.workitems.models import WorkItem

from .models import Game

CHANGEOVER_TICKS = 2  # 30 minutes of game time (A-072)

CEO, DATA_OPERATIONS, COMPLIANCE, SALES, FINANCE, DATA_ANALYTICS = (
    "CEO", "DATA_OPERATIONS", "COMPLIANCE", "SALES", "FINANCE", "DATA_ANALYTICS",
)  # fmt: skip

# Screens every role sees (the game layout's navigation keys).
SHARED_SCREENS = ("", "office", "missions", "events", "handbook", "onboarding", "economy")


@dataclass(frozen=True)
class Role:
    code: str
    title: str
    description: str
    screens: tuple[str, ...]  # navigation keys, besides the shared ones
    actions: frozenset[str]  # player actions (``PlayerAction.action_type``) this role takes


ROLES: dict[str, Role] = {
    r.code: r
    for r in (
        Role(
            CEO,
            "Chief Executive",
            "Runs the company: sees every screen, decides funding and investment, and manages "
            "the managed departments (staff and IT). Department work is done by their heads.",
            (
                "dashboard",
                "health",
                "submissions",
                "providers",
                "queue",
                "rules",
                "disputes",
                "customers",
                "accounts",
                "enquiries",
                "subscribers",
                "sales",
                "staff",
                "it",
                "finance",
                "reviews",
                "analytics",
                "console",
                "scorecards",
                "compliance",
                "support",
                "products",
                "batches",
                "startup",
            ),
            frozenset(
                {
                    "REQUEST_FUNDING",
                    "RENT_OFFICE",
                    "SET_UP_IT",
                    "ONBOARD_PROVIDER",
                    "SET_SUPPORT_STAFF",
                    "DEVELOP_PRODUCT",
                    "SET_MATCHING_TOOLING",
                    "SET_IT_CAPACITY",
                    "RESPOND_TO_OUTAGE",
                    "HIRE",
                    "TRAIN_EMPLOYEE",
                    "SET_SALARY",
                }
            ),
        ),
        Role(
            DATA_OPERATIONS,
            "Head of Data Operations",
            "Receives and processes the providers' files: decides match reviews and unloadable "
            "records, writes rules, sets policies, maps drifted files and sends feedback.",
            ("submissions", "providers", "queue", "rules", "customers", "accounts", "reviews"),
            frozenset(
                {
                    "RESOLVE_ITEM",
                    "SET_REJECTION_POLICY",
                    "SET_MATCHING_THRESHOLDS",
                    "MAP_TEMPLATE",
                    "ADD_CLEANSING_RULE",
                    "SET_CLEANSING_RULE_ACTIVE",
                    "SET_RULE_OVERRIDE",
                    "SEND_FEEDBACK",
                    "TRAIN_PROVIDER",
                    "PENALISE_PROVIDER",
                }
            ),
        ),
        Role(
            COMPLIANCE,
            "Head of Compliance",
            "Answers disputes within their statutory deadline, files the monthly return, checks "
            "subscribers hold consent, keeps retention lawful, reviews staff access, and watches "
            "the bureau's standing with the regulator (P3.7).",
            ("compliance", "disputes", "customers", "accounts", "enquiries", "health"),
            frozenset(
                {
                    "RESOLVE_ITEM",
                    "SAMPLE_CONSENT",
                    "SANCTION_SUBSCRIBER",
                    "SET_RETENTION",
                    "ACCESS_REVIEW",
                    "DECIDE_SUBSCRIBER_CHECK",
                }
            ),
        ),
        Role(
            SALES,
            "Head of Sales",
            "Looks after subscribers and wins new ones: researches lenders, meets them and "
            "negotiates price, term, service level, minimums and discounts (P3.9).",
            ("subscribers", "sales", "enquiries", "batches"),
            frozenset({"SEND_PROPOSAL", "RESEARCH_LENDER", "MEET_LENDER", "ACCEPT_COUNTER"}),
        ),
        Role(
            DATA_ANALYTICS,
            "Head of Data Analytics",
            "Studies the bureau's data: portfolio analytics by lender, product, region and "
            "vintage, and a read-only SQL console over the bureau's own tables (P3.4).",
            ("analytics", "console", "scorecards", "customers", "accounts", "enquiries", "reviews"),
            frozenset(
                {"BUILD_SCORECARD", "BUILD_COMPOSITE", "DEPLOY_SCORECARD", "RETIRE_SCORECARD"}
            ),
        ),
        Role(
            FINANCE,
            "Head of Finance",
            "Keeps the books: approves and pays suppliers' bills, reconciles the bank, keeps "
            "costs to budget and closes each month (P3.8).",
            ("finance",),
            frozenset(
                {
                    "APPROVE_BILL",
                    "REJECT_BILL",
                    "SET_APPROVAL_LIMIT",
                    "POST_STATEMENT_LINE",
                    "QUERY_STATEMENT_LINE",
                    "COMPLETE_RECONCILIATION",
                    "SET_BUDGET",
                    "REVIEW_BUDGET",
                    "CLOSE_MONTH",
                    "SET_UP_BILLING",
                }
            ),
        ),
    )
}

# Actions any role takes: the clock, the campaign, settings, and switching role.
SHARED_ACTIONS = frozenset({
    "PAUSE", "RESUME", "SET_SPEED", "ADVANCE", "SET_PAUSE_RULES", "ANSWER_MISSION",
    "SET_CAMPAIGN", "SET_ASSISTANCE", "SWITCH_ROLE",
})  # fmt: skip

# Work items belong to the department that decides them.
ITEM_ROLES: dict[str, str] = {
    CaseType.MATCH_REVIEW: DATA_OPERATIONS,
    CaseType.UNLOADABLE_TRIAGE: DATA_OPERATIONS,
    CaseType.DISPUTE: COMPLIANCE,
    CaseType.REGULATORY_RETURN: COMPLIANCE,
}


class RoleError(PermissionDenied):
    """The player's current role may not do this (yet). The API answers 403 with the reason."""


def owner_of(action: str, item: WorkItem | None = None) -> str | None:
    """The role an action belongs to; None for the shared ones."""
    if action in SHARED_ACTIONS:
        return None
    if action == "RESOLVE_ITEM" and item is not None:
        return ITEM_ROLES.get(str(item.item_type), DATA_OPERATIONS)
    for role in ROLES.values():
        if action in role.actions:
            return role.code
    raise ValueError(f"No role takes the action {action}")


def ready(game: Game) -> bool:
    return game.current_tick >= game.role_ready_tick


def require(game: Game, action: str, item: WorkItem | None = None) -> None:
    """Refuse an action the player's current role does not take, or takes over later."""
    owner = owner_of(action, item)
    if owner is None:
        return
    if owner != game.role:
        raise RoleError(
            f"That is for the {ROLES[owner].title}. You are working as the "
            f"{ROLES[game.role].title}; switch role to do it."
        )
    if not ready(game):
        raise RoleError(
            f"You are still taking over as {ROLES[game.role].title}. "
            "Let the clock run on a little (half an hour of game time)."
        )


def as_dict(game: Game, ready_at: datetime | None = None) -> dict[str, Any]:
    role = ROLES[game.role]
    return {
        "code": role.code,
        "title": role.title,
        "screens": list(SHARED_SCREENS + role.screens),
        "ready": ready(game),
        "ready_at": ready_at.isoformat() if ready_at and not ready(game) else None,
    }


def catalogue() -> list[dict[str, Any]]:
    return [
        {
            "code": r.code,
            "title": r.title,
            "description": r.description,
            "screens": list(SHARED_SCREENS + r.screens),
            "actions": sorted(r.actions),
        }
        for r in ROLES.values()
    ]
