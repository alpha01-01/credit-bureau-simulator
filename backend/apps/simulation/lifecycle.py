# ruff: noqa: S608  (SQL is built from model table names only, never from input)
"""Deleting games (and worlds that have games).

Bureau records protect their lineage (an observation cannot lose its source
submission), so the ORM cascade refuses to delete them, by design. Deleting a
whole game is the one legitimate exception: everything belonging to its
organisation goes, children before parents, with set-based SQL.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Model

from apps.bureau.core.models import (
    AccountObservation,
    BusinessProfile,
    CreditAccount,
    Customer,
    CustomerContact,
    CustomerIdentifier,
    Enquiry,
    IndividualProfile,
    ProviderCustomerLink,
)
from apps.bureau.providers.models import Institution, InstitutionBranch
from apps.bureau.quality.models import ReviewCase, TransformationLog, ValidationIssue
from apps.bureau.submissions.models import ProcessingRun, StagingRecord, Submission, SubmissionFile
from apps.commercial.models import Contract, Product, Subscriber, UsageRecord
from apps.org.models import Employee, Organization
from apps.workitems.models import WorkItem
from apps.world.generation.persist import delete_world

from .models import (
    Delivery,
    EnquiryJudgement,
    Game,
    PlayerAction,
    ScheduledEvent,
    SubscriberView,
    TickLog,
)


def _table(model: type[Model]) -> str:
    return model._meta.db_table


# (table, SQL condition selecting the game's rows; %(org)s / %(game)s parameters)
_SUBMISSIONS = f"SELECT id FROM {_table(Submission)} WHERE organization_id = %(org)s"
_RUNS = f"SELECT id FROM {_table(ProcessingRun)} WHERE submission_id IN ({_SUBMISSIONS})"
_RECORDS = f"SELECT id FROM {_table(StagingRecord)} WHERE run_id IN ({_RUNS})"
_CUSTOMERS = f"SELECT id FROM {_table(Customer)} WHERE organization_id = %(org)s"
_INSTITUTIONS = f"SELECT id FROM {_table(Institution)} WHERE organization_id = %(org)s"

_ORDER: tuple[tuple[type[Model], str], ...] = (
    (EnquiryJudgement, "game_id = %(game)s"),
    (SubscriberView, "game_id = %(game)s"),
    (UsageRecord, "organization_id = %(org)s"),
    (Enquiry, "organization_id = %(org)s"),
    (
        Contract,
        f"subscriber_id IN (SELECT id FROM {_table(Subscriber)} WHERE organization_id = %(org)s)",
    ),
    (Subscriber, "organization_id = %(org)s"),
    (Product, "organization_id = %(org)s"),
    (WorkItem, "organization_id = %(org)s"),
    (ReviewCase, "organization_id = %(org)s"),
    (TransformationLog, f"record_id IN ({_RECORDS})"),
    (ValidationIssue, f"run_id IN ({_RUNS})"),
    (
        AccountObservation,
        f"credit_account_id IN (SELECT id FROM {_table(CreditAccount)} WHERE organization_id = %(org)s)",
    ),
    (CreditAccount, "organization_id = %(org)s"),
    (ProviderCustomerLink, "organization_id = %(org)s"),
    (CustomerIdentifier, "organization_id = %(org)s"),
    (CustomerContact, f"customer_id IN ({_CUSTOMERS})"),
    (IndividualProfile, f"customer_id IN ({_CUSTOMERS})"),
    (BusinessProfile, f"customer_id IN ({_CUSTOMERS})"),
    (Customer, "organization_id = %(org)s"),
    (StagingRecord, f"run_id IN ({_RUNS})"),
    (ProcessingRun, f"submission_id IN ({_SUBMISSIONS})"),
    (Delivery, "game_id = %(game)s"),
    (SubmissionFile, f"submission_id IN ({_SUBMISSIONS})"),
    (Submission, "organization_id = %(org)s"),
    (InstitutionBranch, f"institution_id IN ({_INSTITUTIONS})"),
    (Institution, "organization_id = %(org)s"),
    (ScheduledEvent, "game_id = %(game)s"),
    (TickLog, "game_id = %(game)s"),
    (PlayerAction, "game_id = %(game)s"),
    (Game, "id = %(game)s"),
    (Employee, "organization_id = %(org)s"),
    (Organization, "id = %(org)s"),
)


def delete_game(game: Game) -> None:
    """Delete a game, its bureau and every record and file the bureau holds."""
    params = {"org": game.organization_id, "game": game.pk}
    folder = Path(settings.STORAGE_ROOT) / "bureau" / f"org_{game.organization_id}"
    with transaction.atomic(), connection.cursor() as cursor:
        for model, condition in _ORDER:
            cursor.execute(f"DELETE FROM {_table(model)} WHERE {condition}", params)
        transaction.on_commit(lambda: shutil.rmtree(folder, ignore_errors=True))


def delete_world_with_games(world_id: int) -> None:
    """Delete a world together with every game played in it."""
    with transaction.atomic():
        for game in Game.objects.filter(world_id=world_id):
            delete_game(game)
        delete_world(world_id)
