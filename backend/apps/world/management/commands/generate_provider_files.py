"""Produce provider submission files for a stored world.

python manage.py generate_provider_files --world 1
python manage.py generate_provider_files --world 1 --period 2026-11 --lender HZF
python manage.py generate_provider_files --world 1 --all-periods --replace
"""

from __future__ import annotations

import time
from collections import Counter
from datetime import date
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.world.models import Lender, World
from apps.world.provider_files import generate_submission, month_end, month_index
from apps.world.provider_files.profiles import PRESETS, REPORTING_PROVIDERS


def _period(text: str) -> date:
    try:
        year, month = (int(part) for part in text.split("-"))
        return month_end(year, month)
    except ValueError as exc:
        raise CommandError(f"Period must look like 2026-12, not {text!r}") from exc


class Command(BaseCommand):
    help = "Generate provider submission files (with their defect ledger) for a stored world."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--world", type=int, required=True, help="World id")
        parser.add_argument(
            "--period",
            action="append",
            type=_period,
            help="Reporting month as YYYY-MM (repeatable; default: the world's last month)",
        )
        parser.add_argument(
            "--all-periods", action="store_true", help="Every month of the world's history"
        )
        parser.add_argument(
            "--lender",
            action="append",
            help=f"Lender code (repeatable; default: {', '.join(REPORTING_PROVIDERS)})",
        )
        parser.add_argument(
            "--profile",
            choices=sorted(PRESETS),
            help="Override every lender's Data Quality Profile",
        )
        parser.add_argument("--replace", action="store_true", help="Regenerate existing months")

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            world = World.objects.get(pk=options["world"])
        except World.DoesNotExist as exc:
            raise CommandError(f"No world with id {options['world']}") from exc

        if options["all_periods"]:
            first, last = month_index(world.history_start), month_index(world.history_end)
            periods = [month_end(i // 12, i % 12 + 1) for i in range(first, last + 1)]
        else:
            periods = options["period"] or [world.history_end]

        codes = options["lender"] or list(REPORTING_PROVIDERS)
        lenders = {lender.code: lender for lender in Lender.objects.filter(world=world)}
        unknown = sorted(set(codes) - set(lenders))
        if unknown:
            raise CommandError(f"Unknown lender code(s): {', '.join(unknown)}")
        profile = PRESETS[options["profile"]] if options["profile"] else None

        for period in periods:
            for code in codes:
                started = time.perf_counter()
                try:
                    result = generate_submission(
                        world, lenders[code], period, profile, replace=options["replace"]
                    )
                except (FileExistsError, ValueError) as exc:
                    raise CommandError(str(exc)) from exc
                sub = result.submission
                rows = sum(len(r.rows) for r in result.rendered.values())
                defects = Counter(
                    d.defect_type for r in result.rendered.values() for d in r.defects
                )
                if result.schedule.is_late:
                    defects["LATE_SUBMISSION"] += 1
                lateness = (
                    f"LATE, arrives {sub.arrival_date}"
                    if result.schedule.is_late
                    else f"arrives {sub.arrival_date}"
                )
                self.stdout.write(
                    f"{code} {period:%Y-%m}  {sub.profile['name']:<8} {rows:>7,} rows  "
                    f"{sum(defects.values()):>6,} defects  {lateness}  "
                    f"({time.perf_counter() - started:.1f}s)"
                )
                for defect_type, count in sorted(defects.items()):
                    self.stdout.write(f"    {defect_type:<20} {count:,}")
