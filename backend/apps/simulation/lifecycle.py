# ruff: noqa: S608  (SQL is built from model table names only, never from input)
"""Deleting games (and worlds that have games).

Bureau records protect their lineage (an observation cannot lose its source
submission), so the ORM cascade refuses to delete them, by design. Deleting a
whole game is the one legitimate exception: everything belonging to its
organisation goes, children before parents, with set-based SQL.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Model

from apps.bureau.core.models import (
    AccountObservation,
    BusinessProfile,
    CourtJudgment,
    CreditAccount,
    Customer,
    CustomerContact,
    CustomerIdentifier,
    DishonouredCheque,
    Enquiry,
    IndividualProfile,
    ProviderCustomerLink,
)
from apps.bureau.providers.models import Institution, InstitutionBranch
from apps.bureau.quality.models import (
    CleansingRule,
    CorrectionRecord,
    Dispute,
    ReviewCase,
    TransformationLog,
    ValidationIssue,
)
from apps.bureau.submissions.models import (
    FeedbackReport,
    ProcessingRun,
    StagingRecord,
    Submission,
    SubmissionFile,
    TemplateMapping,
)
from apps.commercial.models import Contract, Product, Subscriber, UsageRecord
from apps.finance.models import Account, Invoice, InvoiceLine, JournalEntry, JournalLine, Payment
from apps.org.models import Employee, Organization
from apps.workitems.models import WorkItem
from apps.world.generation.persist import delete_world

from .models import (
    Checkpoint,
    Consequence,
    DataQualityReview,
    Delivery,
    EnquiryJudgement,
    Game,
    HistoryTemplate,
    Notice,
    PlayerAction,
    ProviderRelationship,
    RegulatorFinding,
    RegulatorStanding,
    ScheduledEvent,
    SubscriberView,
    TickLog,
)


def _table(model: type[Model]) -> str:
    return model._meta.db_table


# (table, SQL condition selecting the game's rows; %(org)s / %(game)s parameters)
_SUBMISSIONS = f"SELECT id FROM {_table(Submission)} WHERE organization_id = %(org)s"
# A game's processing runs and staging records sit two and three steps below its
# organisation. Their ids are gathered first into small temporary tables with exact
# statistics (``game_scope``): nested subqueries on stale statistics once made the
# planner take minutes over a delete (P2.1).
_RUNS = "SELECT id FROM scope_runs"
_RECORDS = "SELECT id FROM scope_records"
_CUSTOMERS = f"SELECT id FROM {_table(Customer)} WHERE organization_id = %(org)s"
_INSTITUTIONS = f"SELECT id FROM {_table(Institution)} WHERE organization_id = %(org)s"

_ENTRIES = f"SELECT id FROM {_table(JournalEntry)} WHERE organization_id = %(org)s"

_ORDER: tuple[tuple[type[Model], str], ...] = (
    (Consequence, "game_id = %(game)s"),
    (DataQualityReview, "game_id = %(game)s"),
    (Payment, "organization_id = %(org)s"),
    (
        InvoiceLine,
        f"invoice_id IN (SELECT id FROM {_table(Invoice)} WHERE organization_id = %(org)s)",
    ),
    (Invoice, "organization_id = %(org)s"),
    (JournalLine, f"entry_id IN ({_ENTRIES})"),
    (JournalEntry, "organization_id = %(org)s"),
    (Account, "organization_id = %(org)s"),
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
    (CorrectionRecord, "organization_id = %(org)s"),
    (Dispute, "organization_id = %(org)s"),
    (TransformationLog, f"record_id IN ({_RECORDS})"),
    (ValidationIssue, f"run_id IN ({_RUNS})"),
    (
        AccountObservation,
        f"credit_account_id IN (SELECT id FROM {_table(CreditAccount)} WHERE organization_id = %(org)s)",
    ),
    (CreditAccount, "organization_id = %(org)s"),
    (DishonouredCheque, "organization_id = %(org)s"),
    (CourtJudgment, "organization_id = %(org)s"),
    (ProviderCustomerLink, "organization_id = %(org)s"),
    (CustomerIdentifier, "organization_id = %(org)s"),
    (CustomerContact, f"customer_id IN ({_CUSTOMERS})"),
    (IndividualProfile, f"customer_id IN ({_CUSTOMERS})"),
    (BusinessProfile, f"customer_id IN ({_CUSTOMERS})"),
    (Customer, "organization_id = %(org)s"),
    (StagingRecord, f"run_id IN ({_RUNS})"),
    (ProcessingRun, f"submission_id IN ({_SUBMISSIONS})"),
    (Delivery, "game_id = %(game)s"),
    (FeedbackReport, "organization_id = %(org)s"),
    (SubmissionFile, f"submission_id IN ({_SUBMISSIONS})"),
    (TemplateMapping, "organization_id = %(org)s"),
    (CleansingRule, "organization_id = %(org)s"),
    (Submission, "organization_id = %(org)s"),
    (InstitutionBranch, f"institution_id IN ({_INSTITUTIONS})"),
    (Institution, "organization_id = %(org)s"),
    (ScheduledEvent, "game_id = %(game)s"),
    (TickLog, "game_id = %(game)s"),
    (PlayerAction, "game_id = %(game)s"),
    (Checkpoint, "game_id = %(game)s"),
    (ProviderRelationship, "game_id = %(game)s"),
    (RegulatorFinding, "game_id = %(game)s"),
    (RegulatorStanding, "game_id = %(game)s"),
    (Notice, "game_id = %(game)s"),
    (HistoryTemplate, "game_id = %(game)s"),
    (Game, "id = %(game)s"),
    (Employee, "organization_id = %(org)s"),
    (Organization, "id = %(org)s"),
)


def delete_game(game: Game) -> None:
    """Delete a game, its bureau and every record and file the bureau holds."""
    params = {"org": game.organization_id, "game": game.pk}
    folder = Path(settings.STORAGE_ROOT) / "bureau" / f"org_{game.organization_id}"
    with transaction.atomic(), connection.cursor() as cursor, game_scope(cursor, params):
        for model, condition in _ORDER:
            cursor.execute(f"DELETE FROM {_table(model)} WHERE {condition}", params)
        transaction.on_commit(lambda: shutil.rmtree(folder, ignore_errors=True))


@contextmanager
def game_scope(
    cursor: Any, params: dict[str, Any], *, records_view: bool = False
) -> Iterator[None]:
    """Gather the game's run and record ids for the ``_ORDER`` conditions to use.

    Deleting and copying go through every staging record, so their ids are stored.
    A reader that only counts (``records_view``) gets a view instead, which costs
    nothing to set up. Both are created in the caller's transaction, so an error
    that rolls it back removes them too.
    """
    cursor.execute(
        "CREATE TEMP TABLE scope_runs AS SELECT id FROM "
        + _table(ProcessingRun)
        + f" WHERE submission_id IN ({_SUBMISSIONS})",
        params,
    )
    cursor.execute("ANALYZE scope_runs")
    records = f"SELECT id FROM {_table(StagingRecord)} WHERE run_id IN (SELECT id FROM scope_runs)"
    if records_view:
        cursor.execute("CREATE TEMP VIEW scope_records AS " + records)
    else:
        cursor.execute("CREATE TEMP TABLE scope_records AS " + records)
        cursor.execute("ANALYZE scope_records")
    try:
        yield
    finally:
        # Dropped now, not at commit: a caller's transaction may handle several games.
        cursor.execute(f"DROP {'VIEW' if records_view else 'TABLE'} scope_records")
        cursor.execute("DROP TABLE scope_runs")


def delete_world_with_games(world_id: int) -> None:
    """Delete a world together with every game played in it."""
    with transaction.atomic():
        for game in Game.objects.filter(world_id=world_id):
            delete_game(game)
        delete_world(world_id)
