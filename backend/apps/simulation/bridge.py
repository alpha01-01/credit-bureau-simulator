"""Bridge between the world and the bureau.

Only this layer may read both. The bureau receives exactly what a real bureau
would: the provider's public details at onboarding, and file bytes on arrival.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction

from apps.bureau.providers.models import Institution, InstitutionBranch
from apps.bureau.submissions.intake import receive_file
from apps.bureau.submissions.models import Submission
from apps.org.models import Organization
from apps.world.generation.config import LENDER_SRN
from apps.world.models import Branch, Lender, ProviderSubmission, World
from apps.world.provider_files import play_start
from apps.world.provider_files.profiles import REPORTING_PROVIDERS

from .bookkeeping import open_game_books
from .enquiries import set_up_commercial
from .judgement import hire_starting_team
from .models import Delivery, Game

# Files are delivered at the start of the working day (Ghana is on UTC all year).
DELIVERY_TIME = time(9, 0)


@transaction.atomic
def start_game(
    world: World,
    owner: Any = None,
    bureau_name: str = "SimB Credit Bureau",
    history_months: int = 0,
) -> Game:
    """Create a bureau for a world, onboard the reporting providers, and set the clock.

    Play starts on the first day of the month after the world's history.
    ``history_months`` pre-loads that many months of provider files, so the
    bureau starts established (the Established scenario uses 12).
    """
    organization = Organization.objects.create(
        name=bureau_name, organization_code=f"BUREAU-{uuid.uuid4().hex[:10].upper()}"
    )
    start = play_start(world)
    game = Game.objects.create(
        world=world,
        organization=organization,
        owner=owner,
        clock_start=start.replace(day=1),
    )
    for code in REPORTING_PROVIDERS:
        onboard(game, Lender.objects.get(world=world, code=code), world.history_start)
    hire_starting_team(game, world.history_start)
    set_up_commercial(game, world.history_start)
    open_game_books(game)
    if history_months:
        from .history import preload_history  # history uses deliver(), defined below

        preload_history(game, history_months)
    return game


def onboard(game: Game, lender: Lender, onboarding_date: date) -> Institution:
    """Register a lender as a data provider, with the branch list it gives the bureau."""
    institution = Institution.objects.create(
        organization=game.organization,
        institution_code=lender.code,
        institution_name=lender.name,
        srn=LENDER_SRN[lender.code],
        institution_type=lender.lender_type,
        onboarding_date=onboarding_date,
    )
    InstitutionBranch.objects.bulk_create(
        InstitutionBranch(
            institution=institution, branch_code=b.code, branch_name=b.name, region=b.region
        )
        for b in Branch.objects.filter(lender=lender).order_by("code")
    )
    return institution


def deliver(
    game: Game, world_submission: ProviderSubmission, received_at: datetime | None = None
) -> Submission:
    """Hand a provider's files to the bureau, received at ``received_at``.

    Without a time (outside the clock, e.g. the process_month command), files
    arrive at 09:00 on the provider's arrival date.
    """
    institution = Institution.objects.get(
        organization=game.organization, institution_code=world_submission.lender.code
    )
    if received_at is None:
        received_at = datetime.combine(world_submission.arrival_date, DELIVERY_TIME, tzinfo=UTC)
    bureau_submission: Submission | None = None
    with transaction.atomic():
        for world_file in world_submission.files.order_by("kind"):
            data = (Path(settings.STORAGE_ROOT) / world_file.storage_path).read_bytes()
            bureau_file = receive_file(
                game.organization,
                institution,
                world_submission.period,
                world_file.file_name,
                data,
                received_at,
            )
            bureau_submission = bureau_file.submission
            Delivery.objects.create(
                game=game,
                world_submission=world_submission,
                world_file=world_file,
                bureau_submission=bureau_submission,
                bureau_file=bureau_file,
                delivered_at=received_at,
            )
    if bureau_submission is None:
        raise ValueError(f"{world_submission} has no files to deliver")
    return bureau_submission
